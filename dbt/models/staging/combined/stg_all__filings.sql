-- All filings (SEC FSDS and ESEF) in one shape, the input for hub_filing and sat_filing.
select
    hk_filing,
    hk_company,
    hk_filing_company,
    filing_bk,
    company_bk_type,
    company_bk,
    form,
    period_end,
    fiscal_year,
    fiscal_period,
    filed_date,
    accepted_at,
    is_amended_later,
    hd_filing,
    effective_from,
    load_datetime,
    record_source
from {{ ref('stg_sec_fsds__sub') }}

union all

select
    hk_filing,
    hk_company,
    hk_filing_company,
    filing_bk,
    company_bk_type,
    company_bk,
    form,
    period_end,
    fiscal_year,
    fiscal_period,
    filed_date,
    accepted_at,
    is_amended_later,
    hd_filing,
    effective_from,
    load_datetime,
    record_source
from {{ ref('stg_esef__filings') }}
