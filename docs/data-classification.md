# Data classification and data protection (DSGVO)

| Source | Content | Personal data? | Classification |
|---|---|---|---|
| SEC FSDS | Amounts from company financial statements | No | Public |
| SEC submissions | Company names, addresses, filings | Business addresses only | Public |
| ESEF | Company financial statements (IFRS) | No | Public |
| GLEIF | Legal entity records | Can contain names of contact persons in address and mail-routing fields | Public, privacy-filtered at ingestion |
| ECB | Exchange rates | No | Public |

## Privacy by design

GLEIF records can carry names of natural persons in `MailRouting`, `AdditionalAddressLine` and
"c/o" or "Attn" parts of address lines. The GLEIF loader (`ingestion/gleif.py`):

1. keeps only an allowlist of columns (`LEI_COLUMNS`); mail-routing and additional address lines
   are never read;
2. removes "c/o …", "Attn …", "attention …" and "z. Hd. …" fragments from the first address line
   before anything is written;
3. is covered by a test that asserts no contact person name reaches the landed table
   (`test_land_keeps_allowlist_only_and_is_idempotent`).

No personal data is stored downstream, so no deletion process for data subjects is needed.
Purpose: analysis of public company data. Retention: as long as the project exists.

## Access

| Role | Can see | Mechanism |
|---|---|---|
| Engineering | All layers | Workspace Admin / Contributor (dev), Contributor (prod) |
| Analyst | Marts, Business Vault read | Warehouse `db_datareader` on `marts`, `business_vault` |
| Reporting | Semantic model only; model-driver columns hidden | Power BI Viewer, OLS role "Reporting" |
| Sector team | Only their sectors | RLS role "Sektor-Team" (seed `sector_team_users`) |
