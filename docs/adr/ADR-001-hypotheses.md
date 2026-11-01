# ADR-001: Hypotheses, event definition and success criteria

- Status: accepted
- Date: 2026-10-27
- Decided before any model was trained and before any test data was looked at. Later changes
  need a new ADR that references this one; this file is not edited after merge.

## Question

Which published financial KPIs warn earliest and most reliably that a listed company will go
bankrupt within 12 months, and does a worsening of working capital warn earlier than the
classic Altman Z-score?

Business question: how much cash could each sector free up if its companies brought their cash
conversion cycle down to the sector median, and where is the biggest opportunity?

## Hypotheses

| | Hypothesis | Measure | Held when |
|---|---|---|---|
| H1 | Lead time: a rising CCC relative to the sector shows up earlier before bankruptcy than a falling Altman Z''. | Median months between the first quarter a flag turned red and stayed red, and the event. CCC flag: CCC above the sector's 80th percentile and rising over 4 quarters. Z'' flag: Z'' < 1.1. | Median lead time CCC minus Z'' > 0 and the 95 % bootstrap interval (1,000 resamples over companies) lies above 0. |
| H2 | Accuracy: a model with working-capital trends plus Z'' ratios (M2) predicts bankruptcy within 12 months better than Z'' ratios alone (M1). | PR-AUC on the pooled yearly out-of-time test sets. | PR-AUC(M2) minus PR-AUC(M1) has a 95 % bootstrap interval above 0. |
| H3 | Sector view: KPIs as percentile within sector and year beat the same KPIs as absolute values. | PR-AUC of M2 with relative features minus M2 with absolute features. | Interval above 0. |
| H4 | Euro value: the excess working capital above the sector median is large enough to matter. | Sum of cash opportunity per sector, latest fiscal year, EUR. | The largest sector holds at least EUR 1 bn. |

## Event

- Main label: an 8-K with Item 1.03 (Bankruptcy or Receivership) filed within 12 months after
  the as-of date. Event date = filing date.
- Sensitivity label ("distress"): Item 1.03 or Form 15 (deregistration) or Form 25 (delisting).
- If fewer than about 100 main-label positives exist in total, the distress label becomes the
  main label and the report says so (spec, week 5 check). The code applies this rule
  automatically (`analysis/data.py`).

## Rules that protect the answer

- The as-of date is the acceptance date of the financial statement, never the period end.
- Only first-reported values are used (point-in-time); restatements never leak backwards.
- A company that stops filing without an event, or whose 12-month window runs past the data
  end, is censored (left out of that window), not labelled negative.
- Splits are rolling and yearly; never random.
- A negative result is a valid result and is reported as such.

## Note (01.11.2026): how H1 was measured on the real data

The measurement above is unchanged. Two things were found while reading the first real result
and are reported next to it, not instead of it:

- **Availability.** The CCC needs DSO, DIO and DPO at once. In the last quarter before the
  event it could be computed for 40 % of the companies, Z'' for 75 %. A sensitivity
  analysis that counts only quarters in which the input could be computed gives a difference of
  −21.1 months (95 % CI −25.5 to −17.9); `answer.json`, `H1.sensitivity_valid_obs`.
- **Point-in-time per KPI.** Until run 41272420173 a KPI carried the latest acceptance time
  of all line items of the period, so a KPI whose own inputs were known earlier was held back
  to the later date. Since run 41282080293 every KPI carries the latest acceptance time of its own
  inputs (`fact_kpi.available_at`), and the first-reported version keeps the tag known first
  (a tag switch such as ASC 606 had dated two prior years of revenue to the later 10-K). The
  leakage rule is unchanged and still tested.
- **Label quality.** `bw-analysis label-audit` read the 3,609 8-Ks behind the main label on EDGAR:
  250 name only a subsidiary as debtor (wording heuristic), 124 show no Item 1.03 in the
  text read. The label stays as defined above; the audit is published next to the result
  ([docs/case-studies.md](../case-studies.md)).
