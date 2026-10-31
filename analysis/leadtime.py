"""Lead time (H1): months between the first quarter a flag turned red and stayed red, and the event."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ccc_flag(frame: pd.DataFrame, percentile: float = 0.80) -> pd.Series:
    """CCC above the sector's 80th percentile and rising over four quarters."""
    return (frame["CCC__pct"] > percentile) & (frame["CCC__chg4q"] > 0)


def z_flag(frame: pd.DataFrame, threshold: float = 1.1) -> pd.Series:
    return frame["ZPP__value"] < threshold


def first_sustained_red(as_of: pd.Series, flag: pd.Series) -> pd.Timestamp | None:
    """The as-of date from which the flag is red at every later observation (before the event)."""
    order = np.argsort(as_of.to_numpy())
    dates = as_of.to_numpy()[order]
    red = flag.fillna(False).to_numpy(bool)[order]
    if len(red) == 0 or not red[-1]:
        return None
    i = len(red) - 1
    while i > 0 and red[i - 1]:
        i -= 1
    return pd.Timestamp(dates[i])


def lead_times(frame: pd.DataFrame, event_col: str, flags: dict[str, pd.Series]) -> pd.DataFrame:
    """One row per company with an event: lead time in months for each flag (NaN = never red)."""
    rows = []
    with_event = frame[frame[event_col].notna() & (pd.to_datetime(frame["as_of"]) < pd.to_datetime(frame[event_col]))]
    for company_id, g in with_event.groupby("company_id"):
        event = pd.Timestamp(g[event_col].iloc[0])
        row = {"company_id": company_id, "event_date": event, "n_observations": len(g)}
        for name, flag in flags.items():
            start = first_sustained_red(pd.to_datetime(g["as_of"]), flag.loc[g.index])
            row[f"lead_months_{name}"] = (event - start).days / 30.4375 if start is not None else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
