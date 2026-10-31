# ADR-006: Company matching to GLEIF with Splink

- Status: accepted
- Date: 2026-10-27

## Options

Exact name match; fuzzy string match; Splink probabilistic record linkage.

## Decision

Splink 4 on DuckDB (`mdm/`), link-only between SEC filers and GLEIF records.

- Standardisation: upper case, ASCII, punctuation removed, legal suffixes dropped (Inc, Corp,
  AG, SE, GmbH, GmbH & Co. KG, Ltd, ...), abbreviations expanded; originals kept.
- Blocking: same country and first three letters of the standardised name, or same postal code.
- Comparisons: Jaro-Winkler on the name (0.97 / 0.92 / 0.85), Jaro-Winkler on the city, postal
  code exact on 5 then 3 characters, country exact, ticker found in GLEIF other names.
- Training: probability two random records match, u by random sampling, m by EM twice (blocked
  on name prefix and on postal code).
- Thresholds: match probability >= 0.90 is a match; 0.50 to 0.90 goes to the stewardship queue;
  below 0.50 is dropped. To be confirmed with the hand-checked pairs.
- Precedence in the golden record bridge: steward decision > LEI stated in the SEC profile >
  Splink match.
- Survivorship: legal name from GLEIF, SIC from SEC, address from GLEIF headquarters, status
  inactive when GLEIF says lapsed and SEC filings stopped for 18 months.

## Evaluation

About 300 pairs sampled across six probability bands (`mdm sample`), checked by hand, stored
in `mdm/labelled_pairs.csv`; precision and recall at the chosen threshold reported by
`mdm score`. Labels are never generated automatically.
