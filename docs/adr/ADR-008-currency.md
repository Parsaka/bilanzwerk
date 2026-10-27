# ADR-008: Report in EUR with ECB reference rates

- Status: accepted
- Date: 2026-10-27

## Decision

Convert every monetary amount to EUR with ECB reference rates and keep the local amount.

- Balance sheet items (instants): closing rate on the period end (last published rate on or
  before that day).
- Income statement and cash flow items (durations): average of the published daily rates over
  the period (the quarter for single-quarter values, twelve months for TTM values).
- `bv_fx_daily` holds, per currency and calendar day, the closing rate and cumulative sums of
  published rates, so any period average is two equality lookups instead of a range join.
- Ratios (DSO, Z'', margins) are computed in local currency, so FX never changes a KPI.

## Consequences

Before 1999 there is no EUR reference rate; such amounts stay in local currency only (the data
starts 2009, so this matters only for edge cases in comparatives).
