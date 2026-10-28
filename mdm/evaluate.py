"""Hand-checked evaluation of the matching (spec: about 300 pairs across the score range).

1. `sample` writes mdm/labelled_pairs.csv with candidate pairs stratified by match probability
   and an empty `is_match` column. A person checks each pair (SEC name/address vs GLEIF record,
   EDGAR and the GLEIF search) and writes 1 or 0. Labels are never generated automatically.
2. `score` reads the labelled file and reports precision and recall at the chosen threshold,
   plus the precision/recall at other thresholds to justify the choice.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

BANDS = [(0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 0.99), (0.99, 1.0001)]


def sample(candidate_pairs: pd.DataFrame, n_total: int = 300, seed: int = 42) -> pd.DataFrame:
    per_band = n_total // len(BANDS)
    parts = []
    for lo, hi in BANDS:
        band = candidate_pairs[
            (candidate_pairs["match_probability"] >= lo) & (candidate_pairs["match_probability"] < hi)
        ]
        parts.append(band.sample(n=min(per_band, len(band)), random_state=seed))
    out = pd.concat(parts)
    cols = [
        c
        for c in [
            "unique_id_l",
            "unique_id_r",
            "name_orig_l",
            "name_orig_r",
            "city_std_l",
            "city_std_r",
            "zip5_l",
            "zip5_r",
            "country_l",
            "country_r",
            "match_probability",
        ]
        if c in out.columns
    ]
    out = out[cols].copy()
    out["is_match"] = ""
    out["checked_by"] = ""
    out["note"] = ""
    return out


def precision_recall(labelled: pd.DataFrame, threshold: float) -> dict[str, float]:
    df = labelled.dropna(subset=["is_match"])
    df = df[df["is_match"].astype(str).isin(["0", "1"])]
    y = df["is_match"].astype(int).to_numpy()
    pred = (df["match_probability"].to_numpy() >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return {
        "threshold": threshold,
        "n_labelled": len(df),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / (tp + fn) if tp + fn else float("nan"),
    }


def score(labelled_path: Path, threshold: float, out: Path | None = None) -> dict:
    labelled = pd.read_csv(labelled_path)
    report = {
        "chosen": precision_recall(labelled, threshold),
        "curve": [precision_recall(labelled, t) for t in np.round(np.arange(0.5, 1.0, 0.05), 2)],
    }
    if out:
        out.write_text(json.dumps(report, indent=2, default=float))
    return report
