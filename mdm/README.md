# Master data: matching SEC filers to GLEIF

```bash
uv run python -m mdm.cli match        # train Splink, predict, write data/mdm/company_matches.parquet
uv run python -m mdm.cli sample       # write mdm/labelled_pairs.csv (300 pairs, empty labels)
# ... check each pair by hand, fill is_match with 1 or 0 ...
uv run python -m mdm.cli score        # precision and recall at the chosen threshold
```

Design: [ADR-006](../docs/adr/ADR-006-master-data-matching.md).

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
