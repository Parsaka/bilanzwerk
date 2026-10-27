-- Leakage guard in the warehouse: a first-reported value can never be available before its
-- period ended, and a filed period's KPIs never before the statement was accepted.
select k.company_id, k.period_key, k.kpi_key, k.available_at, p.first_accepted_at
from {{ ref('fact_kpi') }} as k
inner join {{ ref('dim_period') }} as p
    on k.period_key = p.period_key
where k.version = '{{ var("version_first_reported") }}'
    and (
        cast(k.available_at as date) < k.period_end_date
        or (p.first_accepted_at is not null and k.available_at < p.first_accepted_at)
    )
