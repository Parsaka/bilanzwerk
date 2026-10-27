## What and why

<!-- One paragraph: what changes and which question, hypothesis or ADR it serves. -->

## Checklist

- [ ] Tests added or updated (pytest, dbt unit/singular tests) and green in `ci`
- [ ] No feature uses data accepted after its as-of date (leakage test green)
- [ ] Data contracts updated for changed mart columns (`docs/data-contracts/`), breaking changes have an ADR
- [ ] Power BI model regenerated (`powerbi/tools/generate_tmdl.py`) if marts or measures changed
- [ ] New decision written as an ADR; CHANGELOG entry added
- [ ] No invented numbers: results in README/docs come from a logged run (MLflow run id or job summary)
- [ ] No personal data added (see `docs/data-classification.md`)
