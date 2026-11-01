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
  below 0.50 is dropped. Checked with the hand-checked pairs: see the amendment below.
- Precedence in the golden record bridge: steward decision > LEI stated in the SEC profile >
  Splink match.
- Survivorship: legal name from GLEIF, SIC from SEC, address from GLEIF headquarters, status
  inactive when GLEIF says lapsed and SEC filings stopped for 18 months.

## Evaluation

About 300 pairs sampled across six probability bands (`mdm sample`), checked by hand, stored
in `mdm/labelled_pairs.csv`; precision and recall at the chosen threshold reported by
`mdm score`. Labels are never generated automatically.

## Amendment (01.11.2026): model v3

The hand-checked pairs showed that the decision above did not hold: at 0.90, model v1 reached
precision 0.20 and recall 0.35 on 297 labelled pairs ([mdm/README.md](../../mdm/README.md)).
Fund series and country units of one sponsor at one address scored above 0.97 on the name, and
filers with the same name but another postal code were missed.

Changes, in use since real-data run [41282080293](https://github.com/Parsaka/bilanzwerk/actions/runs/41282080293):

- **Name comparison:** exact name (spaces ignored) first, then two rule levels (series or
  vehicle marks differ; one name is the other plus words), then Jaro-Winkler 0.97 / 0.92 / 0.85.
- **Legal-form comparison:** the legal-form family read from the original name.
- **Training:** m from the hand-checked match pairs instead of EM on the name; u by random
  sampling as before; one EM pass blocked on the name for city, postal code and legal form.
- **Auto-match rule:** probability ≥ 0.90 and name exact or Jaro-Winkler ≥ 0.97 and no
  contradicting legal form and no tie with another LEI; everything else from 0.50 goes to the
  stewardship queue. The thresholds 0.90 / 0.50 stay.
- **Reproducibility:** ties are ordered by LEI; two runs on the same inputs give the same golden
  records (checked: 0 differences).

Result: precision 1.00 and recall 1.00 on 149 fresh pairs labelled blind, drawn before v3
was written (in-sample on the 297 older pairs: 0.95 / 0.92). 3,758 of 16,891 SEC
filers auto-match (22.2 %); 1,626 pairs wait for a steward. The labels were set by
Claude by the rules in `mdm/REVIEW.md`; a person should spot-check them and change any label they
disagree with (`checked_by`), then rerun `mdm.cli rescore`.
