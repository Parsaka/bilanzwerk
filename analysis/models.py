"""The four models compared in the backtest plus the survival model.

M0  Z'' rule: red below 1.1; score = -Z'' (lower Z'' = riskier)
M1  logistic regression on the four Z'' ratios
M2  logistic regression on the Z'' ratios plus working-capital features (H1, H2)
M3  LightGBM with all features, monotone constraints where the direction is known
S1  discrete-time survival model: quarterly hazard, logistic link (lead-time view)

Shared rules: class weights instead of oversampling; winsorising and imputation are fitted on
the training years only; isotonic calibration on the last training year.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from analysis.config import MONOTONE


@dataclass
class Preprocessor:
    """Winsorise at the 1st/99th percentile, impute the median, add missing indicators."""

    columns: list[str]
    scale: bool = True
    lower: dict[str, float] = field(default_factory=dict)
    upper: dict[str, float] = field(default_factory=dict)
    median: dict[str, float] = field(default_factory=dict)
    scaler: StandardScaler | None = None
    indicator_columns: list[str] = field(default_factory=list)

    def fit(self, X: pd.DataFrame) -> Preprocessor:
        for c in self.columns:
            col = X[c].astype(float)
            self.lower[c] = float(np.nanpercentile(col, 1)) if col.notna().any() else 0.0
            self.upper[c] = float(np.nanpercentile(col, 99)) if col.notna().any() else 0.0
            clipped = col.clip(self.lower[c], self.upper[c])
            self.median[c] = float(clipped.median()) if clipped.notna().any() else 0.0
        self.indicator_columns = [c for c in self.columns if X[c].isna().any()]
        if self.scale:
            self.scaler = StandardScaler().fit(self._base(X))
        return self

    def _base(self, X: pd.DataFrame) -> np.ndarray:
        cols = [X[c].astype(float).clip(self.lower[c], self.upper[c]).fillna(self.median[c]) for c in self.columns]
        return np.column_stack(cols) if cols else np.empty((len(X), 0))

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        base = self._base(X)
        if self.scaler is not None:
            base = self.scaler.transform(base)
        ind = (
            np.column_stack([X[c].isna().to_numpy(float) for c in self.indicator_columns])
            if self.indicator_columns
            else np.empty((len(X), 0))
        )
        return np.hstack([base, ind])

    @property
    def output_names(self) -> list[str]:
        return self.columns + [f"{c}__missing" for c in self.indicator_columns]


class Model:
    name: str
    features: list[str]

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> Model:
        raise NotImplementedError

    def raw_score(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


class ZRule(Model):
    """M0. No training; the score is -Z''. Probability: calibrated on the last training year."""

    def __init__(self, threshold: float = 1.1):
        self.name, self.features, self.threshold = "M0_zscore_rule", ["ZPP__value"], threshold
        self.calibrator: IsotonicRegression | None = None

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> ZRule:
        return self

    def raw_score(self, X: pd.DataFrame) -> np.ndarray:
        z = X["ZPP__value"].astype(float)
        return (-z.fillna(z.median() if z.notna().any() else 0)).to_numpy()

    def red_flag(self, X: pd.DataFrame) -> np.ndarray:
        return (X["ZPP__value"].astype(float) < self.threshold).to_numpy()

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        s = self.raw_score(X)
        return self.calibrator.predict(s) if self.calibrator is not None else 1 / (1 + np.exp(-s))


class Logit(Model):
    def __init__(self, name: str, features: list[str], C: float = 1.0):
        self.name, self.features, self.C = name, features, C
        self.prep: Preprocessor | None = None
        self.clf: LogisticRegression | None = None
        self.calibrator: IsotonicRegression | None = None

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> Logit:
        self.prep = Preprocessor(self.features).fit(train)
        self.clf = LogisticRegression(C=self.C, class_weight="balanced", max_iter=2000)
        self.clf.fit(self.prep.transform(train), y)
        return self

    def raw_score(self, X: pd.DataFrame) -> np.ndarray:
        return self.clf.decision_function(self.prep.transform(X))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        s = self.raw_score(X)
        return self.calibrator.predict(s) if self.calibrator is not None else 1 / (1 + np.exp(-s))

    def odds_ratios(self) -> pd.DataFrame:
        """Odds ratio per one standard deviation of each (winsorised) feature."""
        coef = self.clf.coef_[0]
        return pd.DataFrame(
            {"feature": self.prep.output_names, "coefficient": coef, "odds_ratio_per_sd": np.exp(coef)}
        ).sort_values("coefficient", key=np.abs, ascending=False)

    def contributions(self, X: pd.DataFrame) -> pd.DataFrame:
        Z = self.prep.transform(X)
        return pd.DataFrame(Z * self.clf.coef_[0], columns=self.prep.output_names, index=X.index)


class GBM(Model):
    def __init__(self, name: str, features: list[str], seed: int = 42):
        self.name, self.features, self.seed = name, features, seed
        self.booster: lgb.LGBMClassifier | None = None
        self.calibrator: IsotonicRegression | None = None

    def _monotone(self) -> list[int]:
        out = []
        for f in self.features:
            kpi, stat = f.split("__")
            out.append(MONOTONE.get(kpi, 0) if stat in ("value", "pct") else 0)
        return out

    def fit(self, train: pd.DataFrame, y: np.ndarray) -> GBM:
        pos = max(int(y.sum()), 1)
        self.booster = lgb.LGBMClassifier(
            n_estimators=400,
            learning_rate=0.03,
            num_leaves=15,
            min_child_samples=50,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            scale_pos_weight=(len(y) - pos) / pos,
            monotone_constraints=self._monotone(),
            monotone_constraints_method="advanced",
            random_state=self.seed,
            verbose=-1,
        )
        self.booster.fit(train[self.features].astype(float), y)
        return self

    def raw_score(self, X: pd.DataFrame) -> np.ndarray:
        return self.booster.predict_proba(X[self.features].astype(float))[:, 1]

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        s = self.raw_score(X)
        return self.calibrator.predict(s) if self.calibrator is not None else s


def calibrate(model: Model, calib: pd.DataFrame, y: np.ndarray) -> None:
    """Isotonic calibration on the last training year, so 10 % means about 10 %."""
    if len(np.unique(y)) < 2:
        model.calibrator = None
        return
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(model.raw_score(calib), y)
    model.calibrator = iso


def hazard_frame(frame: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """S1 data: one row per company-quarter; target = event within the next three months."""
    df = frame.copy()
    event_col = "main_event_date" if label_col == "label_main" else "distress_event_date"
    ev = pd.to_datetime(df[event_col])
    df["hazard_target"] = ((ev > df["as_of"]) & (ev <= df["as_of"] + pd.DateOffset(months=3))).astype(float)
    df.loc[df[label_col].isna() & (df["hazard_target"] == 0), "hazard_target"] = np.nan
    return df


class SurvivalHazard(Logit):
    """S1: quarterly hazard h; 12-month probability = 1 - (1 - h)^4."""

    def __init__(self, features: list[str]):
        super().__init__("S1_discrete_time_hazard", features)

    def prob_12m(self, X: pd.DataFrame) -> np.ndarray:
        h = 1 / (1 + np.exp(-self.raw_score(X)))
        return 1 - (1 - h) ** 4
