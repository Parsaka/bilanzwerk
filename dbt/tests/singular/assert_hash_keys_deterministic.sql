-- Same input gives the same hash: recomputing the hub key from its business key matches.
select hk_company, company_bk_type, company_bk
from {{ ref('hub_company') }}
where hk_company <> {{ bw_hash_key(['company_bk_type', 'company_bk']) }}
