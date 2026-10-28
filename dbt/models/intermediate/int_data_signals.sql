-- Data signals per company and period: filing lag, late-filing notices and restatements in
-- the twelve months before the statement was accepted (only what was public by then).
with periods as (
    select
        company_id,
        period_key,
        period_end_date,
        first_accepted_at,
        filing_lag_days
    from {{ ref('dim_period') }}
    where is_filed_period = 1
),

nt as (
    select
        company_id,
        event_date
    from {{ ref('fact_event') }}
    where event_type = 'LATE_FILING_NOTICE'
),

restated as (
    select
        g.golden_company_id as company_id,
        r.restated_at
    from {{ ref('bv_restatements') }} as r
    inner join {{ ref('bv_company_golden') }} as g
        on r.hk_company = g.hk_company
)

select
    p.company_id,
    p.period_key,
    p.period_end_date,
    p.first_accepted_at,
    -- negative lags or lags over ten years are period-end errors in the filing, not signals
    cast(case when p.filing_lag_days between 0 and 3650 then p.filing_lag_days end as {{ bw_float() }}) as filing_lag_d,
    cast((
        select count(*) from nt
        where
            nt.company_id = p.company_id
            and nt.event_date <= cast(p.first_accepted_at as date)
            and nt.event_date > {{ dbt.dateadd('month', -12, 'cast(p.first_accepted_at as date)') }}
    ) as {{ bw_float() }}) as late_filing,
    cast((
        select count(*) from restated as r
        where
            r.company_id = p.company_id
            and r.restated_at <= p.first_accepted_at
            and r.restated_at > {{ dbt.dateadd('month', -12, 'p.first_accepted_at') }}
    ) as {{ bw_float() }}) as restatement_count
from periods as p
