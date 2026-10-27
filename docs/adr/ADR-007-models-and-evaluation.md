# ADR-007: Early-warning models and how they are evaluated

- Status: accepted
- Date: 2026-10-27

## Models

| | Model | Why |
|---|---|---|
| M0 | Z'' rule (red below 1.1) | The textbook baseline |
| M1 | Logistic regression on the four Z'' ratios | Baseline with learned weights |
| M2 | Logistic regression on Z'' ratios plus working-capital level, 1q and 4q change, CCC sector percentile | Tests H1/H2 in an explainable way; champion candidate |
| M2r | M2 with sector percentiles instead of absolute values | Tests H3 |
| M3 | LightGBM, all features, monotone constraints where the direction is known | Best achievable accuracy; challenger |
| S1 | Discrete-time hazard (quarterly, logistic link); 12-month probability = 1 - (1 - h)^4 | Lead-time view |

Altman Z'' (1995, non-manufacturers) because the filings contain no share prices:
Z'' = 6.56 WC/TA + 3.26 RE/TA + 6.72 EBIT/TA + 1.05 Equity/TL.

## Evaluation

- Rolling yearly splits: train on years up to t - 1, calibrate on year t, test on t + 1, for
  t = 2013 ... 2024. Never random. The code asserts time order for every split.
- Class weights, no synthetic oversampling.
- Isotonic calibration on the last training year.
- Main metric PR-AUC (events are rare; accuracy and ROC flatter weak models); also recall in
  the riskiest 5 % and the Brier score.
- Bootstrap 1,000 times over companies (all observations of a company stay together) for the
  PR-AUC differences and the lead-time difference.
- Lead time: a flag that never turned red before the event counts as 0 months, so a flag that
  rarely fires cannot look early by ignoring the companies it missed. The median over flagged
  companies only is reported next to it.
- Every run is logged in MLflow with the data version, the configuration and the metrics.

## Leakage protection

- Features come only from `version = first_reported`.
- A KPI is used at an as-of date only if its `available_at` (latest acceptance time of any
  input) is on or before that date; otherwise it is missing.
- `assert_no_leakage` fails the run; a pytest and a dbt singular test check the same rule.

## Which score the reports show

Both M2 and M3 write their scores to `fact_risk_score`; the column `is_champion` marks the model
the reports and the Excel cockpit show (dbt var `risk_champion_model`, default M2 because a
controller can follow its drivers). Switching to M3 is a one-line change in a pull request, and
only when the pooled backtest shows a PR-AUC gain whose bootstrap interval excludes zero. The
decision and the numbers behind it go into this ADR when it happens.
