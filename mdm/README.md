# Master data: matching SEC filers to GLEIF

```bash
uv run python -m mdm.cli match        # train Splink, predict, write data/mdm/company_matches.parquet
uv run python -m mdm.cli sample       # write mdm/labelled_pairs.csv (300 pairs, empty labels)
# ... check each pair by hand, fill is_match with 1 or 0 ...
uv run python -m mdm.cli score        # precision and recall at the chosen threshold
uv run python -m mdm.cli rescore      # the same hand labels against the current model's probabilities
uv run python -m mdm.cli sample --exclude mdm/labelled_pairs.csv --out new.csv --n 150   # fresh pairs
```

Design: [ADR-006](../docs/adr/ADR-006-master-data-matching.md).

## Hand-checked pairs

[`labelled_pairs.csv`](labelled_pairs.csv) holds the 300 pairs that `sample` drew from the
candidate pairs of real-data run 41209125535 (model v1), spread over the probability bands.
Each pair was labelled by the rules in [REVIEW.md](REVIEW.md), written before the first pair was
read, without looking at `match_probability`; `checked_by` is `claude` and `note` carries the
rule and the reason. A person who disagrees changes `is_match` and `checked_by`, then reruns
`score` and `rescore`.

Result of the review: 85 pairs are the same legal entity, 212 are not, 3 stay unclear
(LookSmart Ltd vs LookSmart Group Inc, Franklin Solana ETF vs Trust, Cascade B.V. vs Cascade
Corp) and are left out of the metrics.

### Model v1 on these pairs ([reports/evaluation_v1.json](reports/evaluation_v1.json))

| Threshold | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| 0.70 | 85 | 137 | 0 | 0.38 | 1.00 |
| 0.90 (chosen in ADR-006) | 30 | 118 | 55 | 0.20 | 0.35 |
| 0.95 | 15 | 58 | 70 | 0.21 | 0.18 |

The sample is stratified by score, so recall here is not the population recall; precision
inside the band at or above 0.90 is a fair estimate for that band, because the pairs in a band
are drawn at random. Two patterns explain the v1 errors:

* 101 of the 118 false matches at 0.90 are series, vehicles or country units of one sponsor at
  the same address: "Venture Lending & Leasing VII" vs "IX", "Atlas Resources Public #18-2009 (B)"
  vs "(C)", "Waste Connections US" vs "Waste Connections". Jaro-Winkler puts them above 0.97,
  and the shared ZIP code did the rest.
* All 55 missed matches carry the same standardised name (54) or a near-identical one, but a
  different ZIP code: v1 had no level for an exact name above Jaro-Winkler 0.97, so the postal
  code decided.

### Model v2

* Name: exact (also with spaces ignored, "AMAZONCOM" = "AMAZON COM") first; then **series or
  vehicle marks differ** (roman numerals, tokens with digits, single letters and words such as
  US, UK, NA, PE, TE, SPV, FEEDER, MASTER; REVIEW.md rule N1); then **one name is the other
  plus words** (a subsidiary, fund or unit of it, rule N2); then Jaro-Winkler 0.97 / 0.92 / 0.85.
* The two rule levels have fixed m probabilities (0.005 and 0.02, `M_MARKS_DIFFER`,
  `M_NAME_EXTENDS`): they are judgements, not fitted, so that EM cannot learn from fund
  families at one address that "Fund VII" and "Fund IX" are one entity. Their u values and all
  other parameters are estimated as before.
* Standardisation joins letters spelled one by one ("L P" = "LP"), drops apostrophes and strips
  SEC tags such as "/CAN/", "/ Delaware" and "\ CA".

The v2 rules were written after reading the v1 errors on these same 300 pairs, so the v2 score
on them is in-sample. The out-of-sample check is a fresh sample of 150 pairs from the v2 run that
excludes these pairs (`sample --exclude`), labelled by the same rules.

## Match weights: why each one makes sense

Filled in after training on the real data from `reports/match_weights_chart.html`. For every
comparison level: the learned match weight, and whether its sign and size are plausible.

| Comparison | Level | Weight | Why it makes sense |
|---|---|---|---|
| name | Jaro-Winkler >= 0.97 | – | |
| name | >= 0.92 | – | |
| name | >= 0.85 | – | |
| city | Jaro-Winkler >= 0.92 | – | |
| postal code | exact 5 | – | |
| postal code | first 3 | – | |
| country | exact | – | |
| ticker | in GLEIF other names | – | |

## Metrics (data quality page)

| Metric | Value |
|---|---|
| Share of SEC filers matched to an LEI | – |
| Precision / recall at 0.90 (hand-checked pairs) | – |
| Open stewardship cases | – |
| Duplicate golden records found | – |
