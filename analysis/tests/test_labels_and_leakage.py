import numpy as np
import pandas as pd
import pytest

from analysis import data
from analysis.config import AnalysisConfig

CFG = AnalysisConfig(data_root=__import__("pathlib").Path("/tmp"))


def _frame():
    return pd.DataFrame(
        {
            "company_id": ["a", "a", "a", "b", "b", "c"],
            "as_of": pd.to_datetime(
                ["2020-02-01", "2021-02-01", "2022-02-01", "2020-02-01", "2023-11-01", "2020-02-01"]
            ),
            "period_key": ["a1", "a2", "a3", "b1", "b2", "c1"],
        }
    )


def _events():
    return pd.DataFrame(
        {
            "company_id": ["a", "c"],
            "event_date": pd.to_datetime(["2022-06-01", "2020-04-01"]),
            "event_type": ["BANKRUPTCY_8K_103", "DELISTING_FORM_25"],
            "is_main_label": [1, 0],
            "is_distress_label": [1, 1],
        }
    )


def _activity():
    return pd.DataFrame(
        {
            "company_id": ["a", "a", "a", "b", "b", "c"],
            "accepted_at": pd.to_datetime(
                ["2020-02-01", "2021-02-01", "2022-02-01", "2020-02-01", "2023-11-01", "2020-02-01"]
            ),
        }
    )


def test_labels_positive_negative_and_censoring():
    out = data.attach_labels(_frame(), _events(), _activity(), pd.Timestamp("2024-03-31"), CFG).set_index("period_key")
    assert out.loc["a3", "label_main"] == 1  # event 4 months later
    assert out.loc["a2", "label_main"] == 0  # event 16 months later, company still filing
    assert np.isnan(out.loc["a1", "label_main"]) or out.loc["a1", "label_main"] == 0
    # b2: the 12-month window runs past the data end -> censored, never a negative
    assert np.isnan(out.loc["b2", "label_main"])
    # b1: b kept filing (2023) -> negative
    assert out.loc["b1", "label_main"] == 0
    # c: Form 25 counts only for the distress label
    assert out.loc["c1", "label_distress"] == 1
    assert np.isnan(out.loc["c1", "label_main"])  # stopped filing without a main event -> censored


def test_observations_after_the_event_are_dropped():
    frame = pd.concat(
        [_frame(), pd.DataFrame({"company_id": ["a"], "as_of": pd.to_datetime(["2022-08-01"]), "period_key": ["a4"]})]
    )
    out = data.attach_labels(frame, _events(), _activity(), pd.Timestamp("2024-03-31"), CFG)
    assert "a4" not in set(out["period_key"])


def test_pivot_hides_values_published_after_the_as_of_date():
    obs = pd.DataFrame({"company_id": ["a"], "period_key": ["p1"], "as_of": pd.to_datetime(["2021-02-01"])})
    kpis = pd.DataFrame(
        {
            "period_key": ["p1", "p1"],
            "kpi_key": ["ZPP", "DSO"],
            "value": [2.0, 50.0],
            "change_1q": [0.1, 1.0],
            "change_4q": [0.2, 2.0],
            "sector_percentile": [0.5, 0.6],
            "available_at": pd.to_datetime(["2021-02-01", "2021-05-01"]),  # DSO came from a later amendment
        }
    )
    wide = data.pivot_features(obs, kpis)
    assert wide.loc[0, "ZPP__value"] == 2.0
    assert np.isnan(wide.loc[0, "DSO__value"])
    data.assert_no_leakage(wide)


def test_leakage_guard_fails_the_build():
    bad = pd.DataFrame(
        {"as_of": pd.to_datetime(["2021-01-01"]), "features_available_at": pd.to_datetime(["2021-03-01"])}
    )
    with pytest.raises(data.LeakageError):
        data.assert_no_leakage(bad)


def test_unfinished_window_censors_positives_too():
    """An unfinished window can only show positives; keeping them would inflate the last year's
    event rate (first real-data run: every labelled 2026 observation was positive)."""
    frame = pd.DataFrame(
        {"company_id": ["a", "b"], "as_of": pd.to_datetime(["2022-02-01", "2022-02-01"]), "period_key": ["a3", "b3"]}
    )
    out = data.attach_labels(frame, _events(), _activity(), pd.Timestamp("2022-07-01"), CFG).set_index("period_key")
    assert np.isnan(out.loc["a3", "label_main"])  # event within the window, but the window is not over
    assert np.isnan(out.loc["b3", "label_main"])


def test_s1_hazard_is_not_shifted_to_a_balanced_base_rate():
    from analysis.models import SurvivalHazard

    rng = np.random.default_rng(0)
    x = rng.normal(size=4000)
    y = (rng.random(4000) < 0.01 * np.exp(x) / np.exp(0.5)).astype(int)
    df = pd.DataFrame({"f__value": x})
    model = SurvivalHazard(["f__value"]).fit(df, y)
    p12 = model.prob_12m(df)
    # four quarters of a ~1 % hazard: about 4 %, not the ~90 % a balanced fit gives
    assert 0.01 < p12.mean() < 0.10
