-- Every company business key we know: SEC CIKs (filings and profiles), LEIs (GLEIF and ESEF).
select distinct hk_company, company_bk_type, company_bk, load_datetime, record_source
from {{ ref('stg_sec_fsds__sub') }}

union all

select hk_company, company_bk_type, company_bk, load_datetime, record_source
from {{ ref('stg_sec_submissions__companies') }}

union all

select hk_company, company_bk_type, company_bk, load_datetime, record_source
from {{ ref('stg_gleif__entities') }}

union all

select distinct hk_company, company_bk_type, company_bk, load_datetime, record_source
from {{ ref('stg_esef__filings') }}
