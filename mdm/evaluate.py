"""Hand-checked evaluation of the matching (spec: about 300 pairs across the score range).

1. `sample` writes mdm/labelled_pairs.csv with candidate pairs stratified by match probability
   and an empty `is_match` column. A person checks each pair (SEC name/address vs GLEIF record,
   EDGAR and the GLEIF search) and writes 1 or 0. Labels are never generated automatically.
2. `score` reads the labelled file and reports precision and recall at the chosen threshold,
   plus the precision/recall at other thresholds to justify the choice.
3. `rescore` keeps the hand labels and swaps in the match probabilities of a newer model run, so
   two model versions are compared on the same pairs. A labelled pair the newer model no longer
   proposes (below LOWER or outside its blocking) counts as predicted non-match.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

CURVE = [float(t) for t in np.round(np.arange(0.5, 1.0, 0.05), 2)]
BANDS = [(0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 0.95), (0.95, 0.99), (0.99, 1.0001)]


def _pair_key(df: pd.DataFrame) -> pd.Series:
    """Order-free key of a pair (Splink may put either source on the left)."""
    lo = df[["unique_id_l", "unique_id_r"]].min(axis=1)
    hi = df[["unique_id_l", "unique_id_r"]].max(axis=1)
    return lo + "~" + hi


def rescore(labelled: pd.DataFrame, candidate_pairs: pd.DataFrame) -> pd.DataFrame:
    """The labelled pairs with match_probability from `candidate_pairs` (0 where it is absent)."""
    from mdm.matching import needs_review, tied_best

    ruled = [r or t for r, t in zip(needs_review(candidate_pairs), tied_best(candidate_pairs), strict=True)]
    newer = candidate_pairs.assign(_key=_pair_key(candidate_pairs), _ruled=ruled)
    newer = newer.drop_duplicates("_key").set_index("_key")
    out = labelled.copy()
    key = _pair_key(out)
    out["match_probability_before"] = out["match_probability"]
    out["match_probability"] = key.map(newer["match_probability"]).fillna(0.0).to_numpy()
    out["needs_review"] = key.map(newer["_ruled"]).fillna(False).astype(bool).to_numpy()
    return out


def sample(
    candidate_pairs: pd.DataFrame, n_total: int = 300, seed: int = 42, exclude: pd.DataFrame | None = None
) -> pd.DataFrame:
    """About n_total pairs spread over the probability bands.

    `exclude` (pairs already labelled) keeps a fresh sample out-of-sample.

    A band with fewer pairs than its share gives all it has; the shortfall goes to the other
    bands in turn, so the sample still reaches n_total when the candidates allow it.
    """
    if exclude is not None and len(exclude):
        candidate_pairs = candidate_pairs[~_pair_key(candidate_pairs).isin(set(_pair_key(exclude)))]
    bands = [
        candidate_pairs[(candidate_pairs["match_probability"] >= lo) & (candidate_pairs["match_probability"] < hi)]
        for lo, hi in BANDS
    ]
    quota = [0] * len(bands)
    left = min(n_total, sum(len(b) for b in bands))
    while left > 0:
        open_bands = [i for i, b in enumerate(bands) if quota[i] < len(b)]
        share = max(1, left // len(open_bands))
        for i in open_bands:
            take = min(share, len(bands[i]) - quota[i], left)
            quota[i] += take
            left -= take
            if left == 0:
                break
    parts = [b.sample(n=q, random_state=seed) for b, q in zip(bands, quota, strict=True) if q]
    out = pd.concat(parts) if parts else candidate_pairs.head(0)
    cols = [
        c
        for c in [
            "unique_id_l",
            "unique_id_r",
            "name_orig_l",
            "name_orig_r",
            "name_std_l",
            "name_std_r",
            "tickers_l",
            "other_names_r",
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
    known = labelled["is_match"].astype(str).str.replace(r"\.0$", "", regex=True).isin(["0", "1"])
    df = labelled[known]
    y = df["is_match"].astype(int).to_numpy()
    pred = df["match_probability"].to_numpy() >= threshold
    if "needs_review" in df.columns:  # such pairs never become "match" (matching.to_matches)
        pred &= ~df["needs_review"].astype(bool).to_numpy()
    pred = pred.astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return {
        "threshold": threshold,
        "n_labelled": len(df),
        "n_unclear": int((~known).sum()),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / (tp + fn) if tp + fn else float("nan"),
    }


def score(labelled_path: Path, threshold: float, out: Path | None = None) -> dict:
    labelled = pd.read_csv(labelled_path, dtype={"is_match": str})
    report = {
        "chosen": precision_recall(labelled, threshold),
        "curve": [precision_recall(labelled, t) for t in CURVE],
    }
    if out:
        out.write_text(json.dumps(report, indent=2, default=float))
    return report
