-- One row per filing: SEC accession number (adsh) or ESEF filing id.
{{ config(unique_key='hk_filing') }}
{{ bw_hub(['stg_all__filings', 'stg_sec_submissions__filings'], 'hk_filing', ['filing_bk']) }}
