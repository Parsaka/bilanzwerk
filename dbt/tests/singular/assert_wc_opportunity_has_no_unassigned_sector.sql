-- H4 benchmarks companies against their sector; companies without a sector have none.
select
    company_id,
    period_key,
    sector_key
from {{ ref('fact_wc_opportunity') }}
where sector_key = '{{ var("unassigned_sector_code") }}'
