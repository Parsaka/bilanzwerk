"""Rolling yearly out-of-time backtest (never a random split).

For t in 2013 ... 2024: train on observations with as-of year <= t - 1, calibrate on year t
(the last training year), test on year t + 1. Each split's test predictions are pooled into one
out-of-time set for the overall comparison and the bootstrap.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis import metrics
from analysis.config import AnalysisConfig, m1_features, m2_features, m3_features
from analysis.models import GBM, Logit, Model, SurvivalHazard, ZRule, calibrate, hazard_frame


@dataclass(frozen=True)
class Split:
    train_years: tuple[int, ...]
    calib_year: int
    test_year: int


def rolling_splits(years: list[int], first_test_year: int, last_test_year: int) -> Iterator[Split]:
    years = sorted(set(years))
    for test_year in range(first_test_year, last_test_year + 1):
        calib = test_year - 1
        train = tuple(y for y in years if y < calib)
        if train and calib in years and test_year in years:
            yield Split(train, calib, test_year)


def model_factories(cfg: AnalysisConfig) -> dict[str, Callable[[], Model]]:
    return {
        "M0_zscore_rule": lambda: ZRule(cfg.z_flag_threshold),
        "M1_logit_z": lambda: Logit("M1_logit_z", m1_features()),
        "M2_logit_z_wc": lambda: Logit("M2_logit_z_wc", m2_features()),
        "M2r_logit_z_wc_relative": lambda: Logit("M2r_logit_z_wc_relative", m2_features(relative=True)),
        "M3_lightgbm_all": lambda: GBM("M3_lightgbm_all", m3_features(), cfg.seed),
    }


def run_backtest(frame: pd.DataFrame, label: str, cfg: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per split metrics, pooled out-of-time predictions)."""
    data = frame[frame[label].notna()].copy()
    for col in m3_features():
        if col not in data.columns:
            data[col] = np.nan
    results, preds = [], []
    for split in rolling_splits(data["as_of_year"].tolist(), cfg.first_test_year, cfg.last_test_year):
        train = data[data["as_of_year"].isin(split.train_years)]
        calib = data[data["as_of_year"] == split.calib_year]
        test = data[data["as_of_year"] == split.test_year]
        y_tr, y_ca, y_te = (d[label].to_numpy(int) for d in (train, calib, test))
        assert train["as_of"].max() < test["as_of"].min(), "time order violated"
        if y_tr.sum() == 0:
            continue
        for name, make in model_factories(cfg).items():
            model = make().fit(train, y_tr)
            calibrate(model, calib, y_ca)
            score = model.raw_score(test)
            prob = model.predict_proba(test)
            results.append(
                {
                    "model": name,
                    "train_through": split.calib_year,
                    "test_year": split.test_year,
                    "n_test": len(test),
                    "n_pos_test": int(y_te.sum()),
                    "pr_auc": metrics.pr_auc(y_te, score),
                    "recall_top5": metrics.recall_at_top(y_te, score, cfg.top_share),
                    "brier": metrics.brier(y_te, prob),
                }
            )
            preds.append(
                pd.DataFrame(
                    {
                        "model": name,
                        "test_year": split.test_year,
                        "company_id": test["company_id"].to_numpy(),
                        "cik": test["cik"].to_numpy(),
                        "as_of": test["as_of"].to_numpy(),
                        "y": y_te,
                        "score": score,
                        "prob": prob,
                    }
                )
            )
        # S1: hazard model trained on quarterly targets, evaluated on the 12-month label
        hz = hazard_frame(pd.concat([train, calib]), label)
        hz = hz[hz["hazard_target"].notna()]
        if hz["hazard_target"].sum() > 0:
            s1 = SurvivalHazard(m2_features()).fit(hz, hz["hazard_target"].to_numpy(int))
            p12 = s1.prob_12m(test)
            results.append(
                {
                    "model": s1.name,
                    "train_through": split.calib_year,
                    "test_year": split.test_year,
                    "n_test": len(test),
                    "n_pos_test": int(y_te.sum()),
                    "pr_auc": metrics.pr_auc(y_te, p12),
                    "recall_top5": metrics.recall_at_top(y_te, p12, cfg.top_share),
                    "brier": metrics.brier(y_te, p12),
                }
            )
            preds.append(
                pd.DataFrame(
                    {
                        "model": s1.name,
                        "test_year": split.test_year,
                        "company_id": test["company_id"].to_numpy(),
                        "cik": test["cik"].to_numpy(),
                        "as_of": test["as_of"].to_numpy(),
                        "y": y_te,
                        "score": p12,
                        "prob": p12,
                    }
                )
            )
    return pd.DataFrame(results), (pd.concat(preds, ignore_index=True) if preds else pd.DataFrame())


def pooled_summary(preds: pd.DataFrame, cfg: AnalysisConfig) -> pd.DataFrame:
    rows = []
    for name, g in preds.groupby("model"):
        y, s, p = g["y"].to_numpy(), g["score"].to_numpy(), g["prob"].to_numpy()
        rows.append(
            {
                "model": name,
                "n": len(g),
                "n_pos": int(y.sum()),
                "pr_auc": metrics.pr_auc(y, s),
                "recall_top5": metrics.recall_at_top(y, s, cfg.top_share),
                "brier": metrics.brier(y, p),
            }
        )
    return pd.DataFrame(rows).sort_values("pr_auc", ascending=False)


def paired_difference(preds: pd.DataFrame, model_a: str, model_b: str, cfg: AnalysisConfig) -> dict[str, float]:
    """Bootstrap over companies: PR-AUC(model_a) - PR-AUC(model_b) on the pooled out-of-time set."""
    a = preds[preds["model"] == model_a].reset_index(drop=True)
    b = preds[preds["model"] == model_b].reset_index(drop=True)
    paired = a[["company_id", "as_of", "y"]].assign(score_a=a["score"], score_b=b["score"])

    def stat(d: pd.DataFrame) -> float:
        y = d["y"].to_numpy()
        return metrics.pr_auc(y, d["score_a"].to_numpy()) - metrics.pr_auc(y, d["score_b"].to_numpy())

    return metrics.bootstrap_by_company(paired, stat, iterations=cfg.bootstrap_iterations, seed=cfg.seed)
