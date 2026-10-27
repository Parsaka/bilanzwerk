"""Evaluation metrics and the company-level bootstrap."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss


def pr_auc(y: np.ndarray, score: np.ndarray) -> float:
    if y.sum() == 0:
        return float("nan")
    return float(average_precision_score(y, score))


def recall_at_top(y: np.ndarray, score: np.ndarray, share: float = 0.05) -> float:
    """Share of all positives found among the `share` riskiest observations."""
    if y.sum() == 0:
        return float("nan")
    k = max(1, int(np.ceil(share * len(score))))
    top = np.argsort(-score, kind="stable")[:k]
    return float(y[top].sum() / y.sum())


def brier(y: np.ndarray, prob: np.ndarray) -> float:
    return float(brier_score_loss(y, np.clip(prob, 0, 1)))


def calibration_table(y: np.ndarray, prob: np.ndarray, bins: int = 10) -> pd.DataFrame:
    df = pd.DataFrame({"y": y, "p": prob})
    df["bin"] = pd.qcut(df["p"].rank(method="first"), q=min(bins, len(df)), labels=False)
    return df.groupby("bin").agg(mean_predicted=("p", "mean"), observed_rate=("y", "mean"), n=("y", "size"))


def bootstrap_by_company(
    df: pd.DataFrame,
    statistic: Callable[[pd.DataFrame], float],
    company_col: str = "company_id",
    iterations: int = 1000,
    seed: int = 42,
) -> dict[str, float]:
    """Resample companies with replacement (all observations of a company stay together).

    Returns the point estimate, the 2.5 / 97.5 percentiles and the share of resamples <= 0.
    """
    rng = np.random.default_rng(seed)
    companies = df[company_col].unique()
    groups = {c: idx for c, idx in df.groupby(company_col).indices.items()}
    point = statistic(df)
    values = []
    for _ in range(iterations):
        pick = rng.choice(companies, size=len(companies), replace=True)
        idx = np.concatenate([groups[c] for c in pick])
        v = statistic(df.iloc[idx])
        if not np.isnan(v):
            values.append(v)
    arr = np.asarray(values)
    return {
        "estimate": float(point),
        "ci_low": float(np.percentile(arr, 2.5)) if len(arr) else float("nan"),
        "ci_high": float(np.percentile(arr, 97.5)) if len(arr) else float("nan"),
        "p_le_zero": float((arr <= 0).mean()) if len(arr) else float("nan"),
        "n_resamples": len(arr),
    }
