# ADR-004: Data Vault 2.0 raw layer with own dbt macros

- Status: accepted
- Date: 2026-10-27

## Context

Restatements, amended filings (10-K/A), name changes and two sources for the same company need
full, insert-only history. Job ads ask for Data Vault by name.

## Options

Plain staging; Data Vault 2.0; Inmon 3NF. Tooling: AutomateDV, datavault4dbt, own macros.

## Decision

Data Vault 2.0 with a small own macro set in `dbt/macros/datavault/`:
`bw_hash_key`, `bw_hash_diff`, `bw_hub`, `bw_link`, `bw_sat`, `bw_pit`, `bw_sat_current`.

Conventions:

- Hash key = SHA-256 over the upper-cased, trimmed business key parts joined by `||`,
  64 lower-case hex characters. NULL parts become the empty string.
- Hash diff = the same, without upper-casing (case changes are real changes).
- Every row carries `load_datetime` and `record_source`; satellites also carry
  `effective_from`, the business time the source states the values (SEC acceptance time).
- A satellite row is written only when the hash diff differs from the previous row of the same
  key, ordered by `effective_from`, both inside a batch and against the table.
- Company business key = (`CIK`, cik) or (`LEI`, lei); the prefix prevents collisions.
- `link_filing_registrant` (whose statements are in a filing) is separate from
  `link_filing_company` (every association from the submissions file, incl. co-registrants), so
  amounts are never attributed to a co-registrant.

Why not AutomateDV: its Fabric adapter support was not certain at decision time, and writing
the five macros shows the pattern is understood. AutomateDV would replace `bw_hub`, `bw_link`
and `bw_sat` one to one (`automate_dv.hub`, `.link`, `.sat`) with the same staged columns; the
hash convention would need its `hash: SHA` and `concat_string: '||'` settings.

## Consequences

- Satellites accept new data in time order. A historic backfill out of order needs a
  `--full-refresh` of the raw vault (documented in the runbook).
- Macro behaviour is pinned by dbt unit tests (`models/raw_vault/_unit_tests.yml`).
