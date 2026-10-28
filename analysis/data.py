"""Read the marts and build the modelling table: one row per company and as-of date.

The as-of date is the acceptance time of a first-reported financial statement, never the
period end. Every feature must have been public at the as-of date (point-in-time); features
that became available later are set to missing, and `assert_no_leakage` fails the run if any
slipped through.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from analysis.config import ALL_KPIS, SIGNALS, AnalysisConfig


class LeakageError(AssertionError):
    """A feature uses data accepted after the as-of date."""


@dataclass
class ModelData:
    frame: pd.DataFrame  # observations with features and labels
    label_column: str
    label_note: str


def load_observations(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Filed statement periods of non-financial companies: the as-of grid."""
    return con.execute("""
        select
            p.company_id,
            c.cik,
            c.company_name,
            c.sector_key,
            p.period_key,
            p.period_end_date,
            p.first_accepted_at as as_of
        from marts.dim_period as p
        inner join marts.dim_company as c
            on p.company_id = c.company_id
            and p.period_end_date >= c.valid_from
            and p.period_end_date < c.valid_to
        where p.is_filed_period = 1
            and c.is_financial = 0
            and c.cik is not null
            and p.first_accepted_at is not null
    """).df()


def load_kpis(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    kpis = ", ".join(f"'{k}'" for k in ALL_KPIS)
    return con.execute(f"""
        select period_key, kpi_key, value, change_1q, change_4q, sector_percentile, available_at
        from marts.fact_kpi
        where version = 'first_reported' and kpi_key in ({kpis})
    """).df()


def load_events(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        select company_id, event_date, event_type, is_main_label, is_distress_label
        from marts.fact_event
    """).df()


def load_last_activity(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Each company's acceptance times of statements, for the censoring rule."""
    return con.execute("""
        select company_id, first_accepted_at as accepted_at
        from marts.dim_period
        where is_filed_period = 1 and first_accepted_at is not null
    """).df()


def pivot_features(obs: pd.DataFrame, kpis: pd.DataFrame) -> pd.DataFrame:
    """Wide feature table. A KPI value is only used if it was available at the as-of date."""
    k = kpis.merge(obs[["period_key", "as_of"]], on="period_key", how="inner")
    late = k["available_at"] > k["as_of"]
    k.loc[late, ["value", "change_1q", "change_4q", "sector_percentile"]] = np.nan
    k = k.rename(columns={"value": "value", "change_1q": "chg1q", "change_4q": "chg4q", "sector_percentile": "pct"})
    wide = k.pivot_table(
        index="period_key", columns="kpi_key", values=["value", "chg1q", "chg4q", "pct"], aggfunc="first", dropna=False
    )
    wide.columns = [f"{kpi}__{stat}" for stat, kpi in wide.columns]
    expected = [f"{kpi}__{stat}" for kpi in ALL_KPIS for stat in ("value", "chg1q", "chg4q", "pct")]
    wide = wide.reindex(columns=expected)
    avail = k[~late].groupby("period_key")["available_at"].max().rename("features_available_at")
    out = obs.merge(wide, left_on="period_key", right_index=True, how="left")
    out = out.merge(avail, left_on="period_key", right_index=True, how="left")
    for s in SIGNALS:  # signals have no trend or percentile columns in the spec
        for stat in ("chg1q", "chg4q", "pct"):
            out = out.drop(columns=[f"{s}__{stat}"], errors="ignore")
    return out


def attach_labels(
    frame: pd.DataFrame, events: pd.DataFrame, activity: pd.DataFrame, data_end: pd.Timestamp, cfg: AnalysisConfig
) -> pd.DataFrame:
    """Label each observation and apply censoring (spec, Labels).

    label_main     = 1 if an 8-K Item 1.03 is filed within 12 months after the as-of date
    label_distress = 1 if Item 1.03, Form 15 or Form 25 within 12 months
    Censored (NaN): the window runs past the data end (positives too), or the company stopped
    filing without an event (no statement accepted after as_of + alive_evidence_months).
    Observations after a company's first event are dropped.
    """
    df = frame.copy()
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["window_end"] = df["as_of"] + pd.DateOffset(months=cfg.horizon_months)
    ev = events.copy()
    ev["event_date"] = pd.to_datetime(ev["event_date"])

    def first_event(mask: pd.Series) -> pd.Series:
        return ev[mask].groupby("company_id")["event_date"].min()

    first_main = first_event(ev["is_main_label"] == 1)
    first_distress = first_event(ev["is_distress_label"] == 1)
    df["main_event_date"] = df["company_id"].map(first_main)
    df["distress_event_date"] = df["company_id"].map(first_distress)

    act = activity.copy()
    act["accepted_at"] = pd.to_datetime(act["accepted_at"])
    last_accept = act.groupby("company_id")["accepted_at"].max()
    df["last_accepted_at"] = df["company_id"].map(last_accept)

    for name, event_col in (("label_main", "main_event_date"), ("label_distress", "distress_event_date")):
        ev_date = df[event_col]
        after_event = ev_date.notna() & (df["as_of"] >= ev_date)
        positive = ev_date.notna() & (ev_date > df["as_of"]) & (ev_date <= df["window_end"])
        # Censored for both classes alike: an unfinished window can show a positive but never a
        # negative, so keeping its positives would inflate the event rate of the last year
        # (seen in the first real-data run: 2026 had only positives).
        past_end = (df["window_end"] > data_end) | (
            df["as_of"] + pd.DateOffset(months=cfg.alive_evidence_months) > data_end
        )
        alive = df["last_accepted_at"] > df["as_of"] + pd.DateOffset(months=cfg.alive_evidence_months)
        label = pd.Series(np.nan, index=df.index)
        label[~positive & alive & ~past_end] = 0
        label[positive & ~past_end] = 1
        label[after_event] = np.nan
        df[name] = label
        df[f"{name}_after_event"] = after_event
    df = df[~df["label_main_after_event"] & ~df["label_distress_after_event"]].drop(
        columns=["label_main_after_event", "label_distress_after_event"]
    )
    df["as_of_year"] = df["as_of"].dt.year
    return df


def assert_no_leakage(frame: pd.DataFrame) -> None:
    bad = frame["features_available_at"].notna() & (pd.to_datetime(frame["features_available_at"]) > frame["as_of"])
    if bad.any():
        raise LeakageError(f"{int(bad.sum())} observations use data accepted after their as-of date")


def build(cfg: AnalysisConfig, con: duckdb.DuckDBPyConnection | None = None) -> ModelData:
    con = con or duckdb.connect(str(cfg.warehouse), read_only=True)
    obs = load_observations(con)
    frame = pivot_features(obs, load_kpis(con))
    events = load_events(con)
    data_end = pd.to_datetime(obs["as_of"]).max()
    frame = attach_labels(frame, events, load_last_activity(con), data_end, cfg)
    assert_no_leakage(frame)
    n_main = int(frame["label_main"].sum())
    if n_main < cfg.min_events_for_main_label:
        note = (
            f"Only {n_main} bankruptcy (8-K Item 1.03) positives; the broader distress label "
            f"(Item 1.03, Form 15, Form 25) is the main label, as planned in the spec."
        )
        return ModelData(frame, "label_distress", note)
    return ModelData(frame, "label_main", f"{n_main} bankruptcy positives; 8-K Item 1.03 is the main label.")


def positives_per_year(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.groupby("as_of_year")[["label_main", "label_distress"]].agg(["sum", "count"])
