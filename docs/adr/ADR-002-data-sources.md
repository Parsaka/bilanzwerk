# ADR-002: Data sources and file formats

- Status: accepted
- Date: 2026-10-27

## Context

The project needs real, official, large and free financial statement data that a recruiter or
a bank's credit team recognises, with a legal basis for use.

## Options

AdventureWorks, SQLBI Contoso generator, Kaggle (Olist, Rossmann), SEC filings plus ESEF plus GLEIF.
For the SEC: FSDS quarterly zips, companyfacts.zip, the Frames API.

## Decision

- **SEC Financial Statement Data Sets** (FSDS) are the backbone: every amount from the primary
  statements of every XBRL filing since 2009q2, with presentation info (statement, line,
  negating flag). Bulk, about 70 downloads in total, no rate-limit problems.
- **SEC submissions.zip** for 8-K items (event label), Form 15/25 and NT filings, and the name
  history (SCD Type 2).
- **ESEF from filings.xbrl.org** (xBRL-JSON, open use) as a second scope: a European peer group
  in IFRS and EUR, and the US-GAAP to IFRS mapping. Not used for the bankruptcy model (too few
  years and events). German filings are not reliably included.
- **GLEIF golden copy** for master data (LEI, names, addresses, parents).
- **ECB EXR** daily reference rates for currency conversion.
- Contoso stays an optional later add-on for sales controlling.

## Consequences

- Every loader declares a User-Agent and stays below 10 requests per second (SEC fair access).
- The SEC may block cloud networks: history is downloaded once from a PC if needed, the
  pipeline only fetches new quarters (runbook).
- Custom (company-specific) XBRL tags are kept in the raw vault but never mapped; mapping
  coverage is reported (`bv_mapping_coverage`).
