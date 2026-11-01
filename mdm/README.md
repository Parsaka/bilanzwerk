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

### Model v2 and v3

v2 added two name levels after reading the v1 errors; v3 (`MODEL_VERSION = "splink4-v3"`, in
use) keeps them and changes how the model is trained and when it may auto-match.

* **Name levels** (both versions): exact (also with spaces ignored, "AMAZONCOM" = "AMAZON COM")
  first; then **series or vehicle marks differ** (roman numerals, tokens with digits, single
  letters and words such as US, UK, NA, PE, TE, SPV, FEEDER, MASTER; REVIEW.md rule N1); then
  **one name is the other plus words** (a subsidiary, fund or unit of it, rule N2); then
  Jaro-Winkler 0.97 / 0.92 / 0.85.
* **Standardisation:** letters spelled one by one are joined ("L P" = "LP"), apostrophes
  dropped, SEC tags such as "/CAN/", "/ Delaware" and "\ CA" stripped, "Company" = "Co".
* **Legal form** (v3): a new comparison on the legal-form family (Corp, LLC, LP, Ltd, plc, AG,
  SE, N.V., B.V., S.A.), read from the original name before the suffix is dropped.
* **Training** (v3): the m values of every comparison come from the hand-checked match pairs
  (`estimate_m_from_pairwise_labels`, Laplace-smoothed for the name levels with few pairs), u
  from random sampling, then one EM pass blocked on the name trains city, postal code and legal
  form. v2 had fixed the m of the two rule levels by hand; with labels that is no longer needed.
* **When a pair may auto-match** (v3): probability ≥ 0.90 **and** the name agrees exactly or
  with Jaro-Winkler ≥ 0.97 **and** the legal forms do not contradict each other **and** no
  other GLEIF record scores the same for this filer. Everything else above 0.50 goes to the
  stewardship queue. Ties are broken by LEI so that a rerun gives the same golden records.

### Results ([real-data run 41282080293](https://github.com/Parsaka/bilanzwerk/actions/runs/41282080293))

| Pairs | Labelled | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|---|
| The 300 pairs above (in-sample: the v2/v3 rules were written after reading them) | 297 | 78 | 4 | 7 | 0.95 | 0.92 |
| 150 fresh pairs from the v2 run, labelled blind ([labelled_pairs_holdout.csv](labelled_pairs_holdout.csv)) | 149 | 47 | 0 | 0 | 1.00 | 1.00 |

The holdout pairs were drawn by `sample --exclude` from the v2 candidate pairs, before v3 was
written, and labelled by REVIEW.md without the score; 1 pair stays unclear. Both samples are
stratified by score, so recall is not the population recall. Files of the run:
`results/mdm_evaluation_rescored.json` and `results/mdm_evaluation_holdout.json`.

## Match weights: why each one makes sense

From `results/mdm_reports/splink_model.json` of the same run (match weight = log2 m/u).

| Comparison | Level | Weight | Why it makes sense |
|---|---|---|---|
| prior | probability two random records match | −19.36 | One SEC filer among millions of GLEIF records. |
| name_std | exact (spaces ignored) | +19.64 | Same standardised name: the strongest single sign. |
| name_std | series or vehicle marks differ | −5.10 | Fund VII vs Fund IX, US unit vs parent: negative as REVIEW.md rule N1 asks. |
| name_std | one name is the other plus words | +11.61 | Positive but well below exact: often a subsidiary or fund (rule N2); legal form and the review rule decide the rest. |
| name_std | Jaro-Winkler >= 0.97 | +20.01 | Typos and small spelling differences of one name; as strong as exact in the labels. |
| name_std | Jaro-Winkler >= 0.92 | +12.59 | Clearly weaker than 0.97; pairs here go to review, not to auto-match. |
| name_std | Jaro-Winkler >= 0.85 | +7.64 | Weak evidence; never a match on its own against the prior. |
| name_std | All other comparisons | −5.85 | Different names: evidence against. |
| city_std | Exact match on city_std | +6.31 | Same city supports a match. |
| city_std | Jaro-Winkler distance of city_std >= 0.92 | +5.83 | Spelling variants of one city, a little weaker than exact. |
| city_std | All other comparisons | −3.83 | Different city: against, but mild, because GLEIF holds the legal seat and SEC the business address. |
| postal_code | Exact match on zip5 | +9.60 | Same five-digit code is strong; it is also what fooled v1 on fund families. |
| postal_code | Exact match on zip3 | +3.57 | Same area only: weak. |
| postal_code | All other comparisons | −5.12 | Different code: against. |
| country | Exact match on country | +0.01 | About zero: blocking already requires the same country in one rule. |
| country | All other comparisons | −68.39 | A different country practically rules a pair out. |
| legal_form | Exact match on legal_form | +2.38 | Same legal-form family (Corp, LLC, LP, ...) adds a little. |
| legal_form | All other comparisons | −3.45 | Inc vs LP or Corp vs Trust: against, and the pair goes to review. |
| ticker | ticker found in GLEIF other names | – | Never seen in training (GLEIF other names rarely carry tickers), so no weight is learned. |
| ticker | All other comparisons | +0.00 | Neutral. |

## Metrics (data quality page)

| Metric | Value |
|---|---|
| SEC filers considered | 16,891 |
| Auto-matched to an LEI | 3,758 (22.2 %) |
| Open stewardship cases | 1,626 |
| Golden records with an LEI | 6,857 |
| Duplicate golden records found | 0 |
| Precision / recall at 0.90, holdout pairs | 1.00 / 1.00 |
