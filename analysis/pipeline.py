"""End-to-end analysis run: labels -> backtest -> statistics -> explanations -> write-back.

Outputs (under <data_root>/analysis/):
  results/*.csv, results/answer.json   the numbers behind the answer page and the summary
  risk_scores.parquet                  read by dbt (source analysis.risk_scores, BW_HAS_RISK_SCORES=true)
Every run is logged to MLflow with the data version, the configuration and the metrics.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from analysis import answer, backtest, data, leadtime, metrics
from analysis.config import AnalysisConfig, m2_features, m3_features
from analysis.models import GBM, Logit, calibrate

log = logging.getLogger(__name__)


def data_version(con: duckdb.DuckDBPyConnection) -> str:
    """Fingerprint of what the warehouse was built from: the latest data quality run id plus row counts."""
    run = con.execute("select max(run_id) from marts.fact_data_quality").fetchone()[0]
    counts = con.execute("""
        select (select count(*) from marts.fact_financial_line), (select count(*) from marts.fact_kpi),
               (select count(*) from marts.fact_event)
    """).fetchone()
    return hashlib.sha256(f"{run}|{counts}".encode()).hexdigest()[:16]


def lead_time_analysis(frame: pd.DataFrame, label: str, cfg: AnalysisConfig) -> tuple[pd.DataFrame, dict]:
    event_col = "main_event_date" if label == "label_main" else "distress_event_date"
    flags = {
        "ccc": leadtime.ccc_flag(frame, cfg.ccc_flag_percentile),
        "z": leadtime.z_flag(frame, cfg.z_flag_threshold),
    }
    per_company = leadtime.lead_times(frame, event_col, flags)
    if per_company.empty:
        nan = float("nan")
        return per_company, {
            "estimate": nan,
            "ci_low": nan,
            "ci_high": nan,
            "median_ccc": nan,
            "median_z": nan,
            "n_companies": 0,
        }
    # A flag that never turned red warned 0 months ahead; this keeps rarely-firing flags honest.
    pc = per_company.fillna({"lead_months_ccc": 0.0, "lead_months_z": 0.0})

    def stat(d: pd.DataFrame) -> float:
        return float(d["lead_months_ccc"].median() - d["lead_months_z"].median())

    boot = metrics.bootstrap_by_company(pc, stat, iterations=cfg.bootstrap_iterations, seed=cfg.seed)
    summary = {
        **boot,
        "median_ccc": float(pc["lead_months_ccc"].median()),
        "median_z": float(pc["lead_months_z"].median()),
        "median_ccc_flagged_only": float(per_company["lead_months_ccc"].median()),
        "median_z_flagged_only": float(per_company["lead_months_z"].median()),
        "share_never_red_ccc": float(per_company["lead_months_ccc"].isna().mean()),
        "share_never_red_z": float(per_company["lead_months_z"].isna().mean()),
        "n_companies": len(pc),
    }
    return per_company, summary


def fit_final(frame: pd.DataFrame, label: str, cfg: AnalysisConfig) -> dict[str, object]:
    """Champion (M2) and challenger (M3) on all labelled years, calibrated on the last one."""
    labelled = frame[frame[label].notna()]
    last = labelled["as_of_year"].max()
    train, calib = labelled[labelled["as_of_year"] < last], labelled[labelled["as_of_year"] == last]
    out = {}
    for model in (Logit("M2_logit_z_wc", m2_features()), GBM("M3_lightgbm_all", m3_features(), cfg.seed)):
        model.fit(train, train[label].to_numpy(int))
        calibrate(model, calib, calib[label].to_numpy(int))
        out[model.name] = model
    return out


def top_drivers_logit(model: Logit, X: pd.DataFrame, k: int = 3) -> list[str]:
    contrib = model.contributions(X)
    return [
        ", ".join(row.sort_values(ascending=False).index[:k].str.replace("__", " ")) for _, row in contrib.iterrows()
    ]


def shap_explain(model: GBM, X: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    import shap

    explainer = shap.TreeExplainer(model.booster)
    values = explainer.shap_values(X[model.features].astype(float))
    values = values[1] if isinstance(values, list) else values
    sv = pd.DataFrame(values, columns=model.features, index=X.index)
    importance = sv.abs().mean().sort_values(ascending=False).rename("mean_abs_shap").reset_index()
    importance.columns = ["feature", "mean_abs_shap"]
    drivers = [", ".join(row.sort_values(ascending=False).index[:3].str.replace("__", " ")) for _, row in sv.iterrows()]
    return importance, drivers


def risk_band(p: np.ndarray, cfg: AnalysisConfig) -> list[str]:
    return ["red" if v >= cfg.red_band else "yellow" if v >= cfg.yellow_band else "green" for v in p]


def wc_opportunity(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    latest = con.execute("""
        with ranked as (
            select w.*, row_number() over (partition by company_id order by fiscal_year desc) as rn
            from marts.fact_wc_opportunity as w
        )
        select r.*, c.company_name, s.sector_de
        from ranked as r
        join marts.dim_company as c on r.company_key = c.company_key
        join marts.dim_sector as s on r.sector_key = s.sector_key
        where rn = 1
    """).df()
    by_sector = (
        latest.groupby("sector_de")
        .agg(
            cash_opportunity_eur_bn=("cash_opportunity_eur", lambda s: s.sum() / 1e9),
            stretch_eur_bn=("cash_opportunity_stretch_eur", lambda s: s.sum() / 1e9),
            companies=("company_id", "nunique"),
        )
        .sort_values("cash_opportunity_eur_bn", ascending=False)
        .reset_index()
    )
    top20 = latest.nlargest(20, "cash_opportunity_eur")[
        [
            "company_name",
            "sector_de",
            "fiscal_year",
            "dso",
            "dio",
            "dpo",
            "cash_opportunity_eur",
            "cash_opportunity_stretch_eur",
        ]
    ]
    return by_sector, top20


def run(cfg: AnalysisConfig | None = None, log_mlflow: bool = True) -> dict:
    cfg = cfg or AnalysisConfig()
    out = cfg.out_dir
    results_dir = out / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(cfg.warehouse), read_only=True)

    md = data.build(cfg, con)
    frame, label = md.frame, md.label_column
    data.positives_per_year(frame).to_csv(results_dir / "event_counts_per_year.csv")

    split_metrics, preds = backtest.run_backtest(frame, label, cfg)
    split_metrics.to_csv(results_dir / "backtest_by_year.csv", index=False)
    pooled = backtest.pooled_summary(preds, cfg) if len(preds) else pd.DataFrame()
    pooled.to_csv(results_dir / "backtest_pooled.csv", index=False)

    nan_diff = {"estimate": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
    diff_h2 = backtest.paired_difference(preds, "M2_logit_z_wc", "M1_logit_z", cfg) if len(preds) else nan_diff
    diff_h3 = (
        backtest.paired_difference(preds, "M2r_logit_z_wc_relative", "M2_logit_z_wc", cfg) if len(preds) else nan_diff
    )
    # ADR-007: the reports switch from M2 to M3 only when M3's PR-AUC gain excludes zero.
    diff_champion = (
        backtest.paired_difference(preds, "M3_lightgbm_all", "M2_logit_z_wc", cfg) if len(preds) else nan_diff
    )
    per_company_lead, lead = lead_time_analysis(frame, label, cfg)
    per_company_lead.to_csv(results_dir / "lead_times_per_company.csv", index=False)
    by_sector, top20 = wc_opportunity(con)
    by_sector.to_csv(results_dir / "wc_opportunity_by_sector.csv", index=False)
    top20.to_csv(results_dir / "wc_opportunity_top20.csv", index=False)

    final = fit_final(frame, label, cfg)
    latest = frame.sort_values("as_of").groupby("company_id").tail(1)
    m2, m3 = final["M2_logit_z_wc"], final["M3_lightgbm_all"]
    m2.odds_ratios().to_csv(results_dir / "m2_odds_ratios.csv", index=False)
    importance, m3_drivers = shap_explain(m3, latest)
    importance.to_csv(results_dir / "m3_shap_importance.csv", index=False)
    scores = []
    for model, drivers in ((m2, top_drivers_logit(m2, latest)), (m3, m3_drivers)):
        p = model.predict_proba(latest)
        scores.append(
            pd.DataFrame(
                {
                    "cik": latest["cik"].to_numpy(),
                    "as_of_date": pd.to_datetime(latest["as_of"]).dt.date.to_numpy(),
                    "model_name": model.name,
                    "probability_12m": p,
                    "risk_band": risk_band(p, cfg),
                    "top_3_drivers": drivers,
                }
            )
        )
    risk = pd.concat(scores, ignore_index=True)

    answer_doc = {
        "label": label,
        "label_note": md.label_note,
        "data_version": data_version(con),
        "n_observations": len(frame),
        "n_labelled": int(frame[label].notna().sum()),
        "n_positive": int(frame[label].sum()),
        "H1": answer.h1(lead),
        "H2": answer.h2(diff_h2),
        "H3": answer.h3(diff_h3),
        "H4": answer.h4(by_sector),
        "champion_check": {
            "comparison": "PR-AUC M3_lightgbm_all minus M2_logit_z_wc",
            **{k: diff_champion[k] for k in ("estimate", "ci_low", "ci_high")},
            "m3_gain_excludes_zero": bool(diff_champion["ci_low"] > 0),
        },
        "pooled": pooled.to_dict(orient="records"),
        "config": {k: str(v) for k, v in dataclasses.asdict(cfg).items()},
    }
    run_id = "local"
    if log_mlflow:
        run_id = log_run(cfg, answer_doc, pooled, results_dir)
    risk["run_id"] = run_id
    risk.to_parquet(out / "risk_scores.parquet", index=False)
    (results_dir / "answer.json").write_text(json.dumps(answer_doc, indent=2, default=str, ensure_ascii=False))
    return answer_doc


def log_run(cfg: AnalysisConfig, doc: dict, pooled: pd.DataFrame, results_dir: Path) -> str:
    import os

    import mlflow

    # A tracking server (Fabric ML experiment, Azure ML, Databricks) wins when configured;
    # otherwise runs go to a local folder next to the results.
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        mlflow.set_tracking_uri(f"file:{(cfg.out_dir / 'mlruns').as_posix()}")
    mlflow.set_experiment("bilanzwerk-early-warning")
    with mlflow.start_run() as r:
        mlflow.log_params({**doc["config"], "label": doc["label"], "data_version": doc["data_version"]})
        for row in doc["pooled"]:
            for metric in ("pr_auc", "recall_top5", "brier"):
                v = row.get(metric)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    mlflow.log_metric(f"{row['model']}.{metric}", float(v))
        for h in ("H1", "H2", "H3"):
            v = doc[h].get("estimate")
            if v is not None and not np.isnan(v):
                mlflow.log_metric(f"{h}.estimate", float(v))
        mlflow.log_artifacts(str(results_dir))
        return r.info.run_id


def case_timeline(con: duckdb.DuckDBPyConnection, cik: int) -> pd.DataFrame:
    """KPIs, red flags and events for one company (the three case studies are chosen after the run)."""
    return con.execute(
        """
        select c.company_name, k.period_end_date, k.kpi_key, k.value, k.sector_percentile, k.red_flag,
               k.available_at
        from marts.fact_kpi as k
        join marts.dim_company as c on k.company_key = c.company_key
        where c.cik = ? and k.version = 'first_reported' and k.kpi_key in ('ZPP', 'CCC', 'DSO', 'DIO', 'DPO',
              'CASH_RUNWAY_M', 'INTEREST_COVERAGE', 'FILING_LAG_D')
        order by k.period_end_date, k.kpi_key
    """,
        [cik],
    ).df()
