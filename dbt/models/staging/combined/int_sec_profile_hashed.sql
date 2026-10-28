-- Submissions profile with its hash diff (kept apart so stg_ stays a 1:1 view of the source).
select
    p.*,
    {{ bw_hash_diff(['company_name', 'entity_type', 'sic', 'sic_description', 'tickers', 'exchanges',
                     'fiscal_year_end_mmdd', 'state_of_incorporation', 'business_city',
                     'business_state', 'business_zip', 'lei']) }} as hd_company_sec_profile
from {{ ref('stg_sec_submissions__companies') }} as p
