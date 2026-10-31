from pathlib import Path

import numpy as np
import pandas as pd

from analysis import backtest, leadtime, metrics
from analysis.config import AnalysisConfig, m3_features


def test_rolling_splits_are_strictly_out_of_time():
    splits = list(backtest.rolling_splits(list(range(2009, 2026)), 2014, 2025))
    assert splits[0].test_year == 2014 and splits[0].calib_year == 2013
    assert splits[-1].test_year == 2025
    for s in splits:
        assert max(s.train_years) < s.calib_year < s.test_year


def test_recall_at_top_and_pr_auc():
    y = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 1] * 2)
    s = np.arange(20)[::-1].astype(float)  # first observations riskiest
    assert metrics.recall_at_top(y, s, 0.05) == 0.25  # the single riskiest of 20 finds 1 of 4 positives
    assert 0 < metrics.pr_auc(y, s) <= 1


def test_bootstrap_is_deterministic():
    df = pd.DataFrame({"company_id": np.repeat(np.arange(30), 3), "v": np.arange(90, dtype=float)})
    a = metrics.bootstrap_by_company(df, lambda d: d["v"].mean(), iterations=200, seed=1)
    b = metrics.bootstrap_by_company(df, lambda d: d["v"].mean(), iterations=200, seed=1)
    assert a == b and a["ci_low"] < a["estimate"] < a["ci_high"]


def test_first_sustained_red():
    dates = pd.Series(pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"]))
    assert leadtime.first_sustained_red(dates, pd.Series([True, False, True, True])) == pd.Timestamp("2020-07-01")
    assert leadtime.first_sustained_red(dates, pd.Series([True, True, True, False])) is None


def synthetic_frame(seed: int = 0) -> pd.DataFrame:
    """Test data only: a planted signal so the backtest code path can be exercised."""
    rng = np.random.default_rng(seed)
    n = 3000
    df = pd.DataFrame({"company_id": rng.integers(0, 600, n).astype(str), "cik": rng.integers(1, 9999, n)})
    df["as_of_year"] = rng.integers(2011, 2018, n)
    df["as_of"] = pd.to_datetime(df["as_of_year"].astype(str) + "-03-01") + pd.to_timedelta(
        rng.integers(0, 300, n), "D"
    )
    for col in m3_features():
        df[col] = rng.normal(size=n)
    risk = -1.5 * df["WC_TA__value"] + 1.0 * df["CCC__chg4q"] - 4
    df["label_main"] = (rng.random(n) < 1 / (1 + np.exp(-risk))).astype(float)
    df["main_event_date"] = pd.NaT
    df.loc[df["label_main"] == 1, "main_event_date"] = df["as_of"] + pd.Timedelta(days=200)
    return df


def test_backtest_runs_and_beats_random_on_planted_signal():
    cfg = AnalysisConfig(data_root=Path("/tmp"), first_test_year=2014, last_test_year=2017, bootstrap_iterations=50)
    frame = synthetic_frame()
    per_split, preds = backtest.run_backtest(frame, "label_main", cfg)
    assert set(per_split["test_year"]) == {2014, 2015, 2016, 2017}
    pooled = backtest.pooled_summary(preds, cfg).set_index("model")
    base_rate = frame["label_main"].mean()
    assert pooled.loc["M1_logit_z", "pr_auc"] > base_rate
    assert pooled.loc["M2_logit_z_wc", "pr_auc"] > base_rate
    diff = backtest.paired_difference(preds, "M2_logit_z_wc", "M1_logit_z", cfg)
    assert diff["ci_low"] <= diff["estimate"] <= diff["ci_high"]


def test_lead_time_sensitivity_skips_quarters_without_the_signal():
    """A missing last quarter ends the red streak in the H1 measure, not in the sensitivity."""
    frame = pd.DataFrame(
        {
            "company_id": ["a"] * 4,
            "as_of": pd.to_datetime(["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01"]),
            "event": pd.to_datetime(["2021-01-01"] * 4),
            "ZPP__value": [0.5, 0.4, 0.3, None],
        }
    )
    out = leadtime.lead_times(frame, "event", {"z": leadtime.z_flag(frame)}, inputs={"z": "ZPP__value"})
    row = out.iloc[0]
    assert pd.isna(row["lead_months_z"]) and not row["z_available_last"]
    assert round(row["lead_months_z_valid_obs"], 1) == round(
        (pd.Timestamp("2021-01-01") - pd.Timestamp("2020-01-01")).days / 30.4375, 1
    )
