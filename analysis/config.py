"""Analysis settings. Everything that defines the experiment is here and logged to MLflow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

Z_RATIOS = ["WC_TA", "RE_TA", "EBIT_TA", "EQ_TL"]
WC_KPIS = ["DSO", "DIO", "DPO", "CCC"]
OTHER_KPIS = [
    "NI_TA",
    "CL_CA",
    "FFO_TL",
    "CURRENT_RATIO",
    "QUICK_RATIO",
    "CASH_RUNWAY_M",
    "DEBT_EBITDA",
    "INTEREST_COVERAGE",
    "EQUITY_RATIO",
    "REV_GROWTH",
    "EBIT_MARGIN",
    "GROSS_MARGIN",
    "CFO_MARGIN",
]
SIGNALS = ["FILING_LAG_D", "LATE_FILING", "RESTATEMENT_COUNT"]
ALL_KPIS = ["ZPP", *Z_RATIOS, *WC_KPIS, *OTHER_KPIS, *SIGNALS]

# Direction of the effect on bankruptcy risk where it is known (LightGBM monotone constraints):
# +1 = higher value -> higher risk, -1 = higher value -> lower risk.
MONOTONE = {
    "ZPP": -1,
    "WC_TA": -1,
    "RE_TA": -1,
    "EBIT_TA": -1,
    "EQ_TL": -1,
    "NI_TA": -1,
    "CL_CA": 1,
    "FFO_TL": -1,
    "CURRENT_RATIO": -1,
    "QUICK_RATIO": -1,
    "EQUITY_RATIO": -1,
    "INTEREST_COVERAGE": -1,
    "FILING_LAG_D": 1,
    "LATE_FILING": 1,
    "RESTATEMENT_COUNT": 1,
}


def m1_features() -> list[str]:
    return [f"{k}__value" for k in Z_RATIOS]


def m2_features(relative: bool = False) -> list[str]:
    base = m1_features()
    if relative:  # H3: the same KPIs as percentile within sector and year
        base = [f"{k}__pct" for k in Z_RATIOS]
        return base + [f"{k}__pct" for k in WC_KPIS] + [f"{k}__chg4q" for k in WC_KPIS]
    return (
        base
        + [f"{k}__value" for k in WC_KPIS]
        + [f"{k}__chg1q" for k in WC_KPIS]
        + [f"{k}__chg4q" for k in WC_KPIS]
        + ["CCC__pct"]
    )


def m3_features() -> list[str]:
    feats = []
    for k in ALL_KPIS:
        feats.append(f"{k}__value")
        if k not in SIGNALS:
            feats += [f"{k}__chg1q", f"{k}__chg4q", f"{k}__pct"]
    return feats


@dataclass(frozen=True)
class AnalysisConfig:
    data_root: Path = field(default_factory=lambda: Path(os.environ.get("BW_DATA_ROOT", "data")).resolve())
    first_test_year: int = 2014  # train up to t, test on t + 1, t = 2013 ... 2024
    last_test_year: int = 2025
    horizon_months: int = 12
    # negatives need evidence the company was still filing near the end of the window
    alive_evidence_months: int = 9
    min_events_for_main_label: int = 100
    bootstrap_iterations: int = 1000
    top_share: float = 0.05
    seed: int = 42
    # Lead-time flags (spec): CCC above the sector's 80th percentile and rising; Z'' below 1.1
    ccc_flag_percentile: float = 0.80
    z_flag_threshold: float = 1.1
    # Risk bands on calibrated 12-month probability
    red_band: float = 0.10
    yellow_band: float = 0.03

    @property
    def warehouse(self) -> Path:
        return self.data_root / "bilanzwerk.duckdb"

    @property
    def out_dir(self) -> Path:
        return self.data_root / "analysis"
