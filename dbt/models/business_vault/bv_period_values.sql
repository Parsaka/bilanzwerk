-- Quarter derivation. Many cash-flow and income lines are reported year-to-date. Single
-- quarters are derived by subtraction (Q2 = H1 - Q1, Q3 = 9M - H1, Q4 = FY - 9M), and
-- trailing-twelve-month (TTM) values come from the annual figure or the sum of four quarters.
-- FSDS rounds period ends to month ends (ESEF is rounded the same way in staging), so the
-- previous YTD period ends exactly three month ends earlier.
with items as (
    select * from {{ ref('bv_line_item_values') }}
),

durations as (
    select * from items where period_type = 'duration'
),

direct_quarter as (
    select version, hk_company, line_item_code, period_end, unit, value, source_filing, available_at,
        1 as derivation_rank, 'reported' as derivation
    from durations
    where qtrs = 1
),

derived_quarter as (
    select
        cur.version,
        cur.hk_company,
        cur.line_item_code,
        cur.period_end,
        cur.unit,
        cur.value - prev.value as value,
        cur.source_filing,
        case when prev.available_at > cur.available_at then prev.available_at else cur.available_at end as available_at,
        2 as derivation_rank,
        'derived_ytd' as derivation
    from durations as cur
    inner join durations as prev
        on cur.version = prev.version
        and cur.hk_company = prev.hk_company
        and cur.line_item_code = prev.line_item_code
        and cur.unit = prev.unit
        and prev.qtrs = cur.qtrs - 1
        and prev.period_end = {{ bw_month_end(dbt.dateadd('month', -3, 'cur.period_end')) }}
    where cur.qtrs between 2 and 4
),

single_quarter as (
    select * from (
        select
            q.*,
            row_number() over (
                partition by version, hk_company, line_item_code, period_end
                order by derivation_rank
            ) as rn
        from (
            select * from direct_quarter
            union all
            select * from derived_quarter
        ) as q
    ) as ranked
    where rn = 1
),

annual as (
    select version, hk_company, line_item_code, period_end, unit, value, available_at
    from durations
    where qtrs = 4
),

ttm_from_quarters as (
    select
        q0.version,
        q0.hk_company,
        q0.line_item_code,
        q0.period_end,
        q0.value + q1.value + q2.value + q3.value as value,
        q0.available_at
    from single_quarter as q0
    inner join single_quarter as q1
        on q0.version = q1.version and q0.hk_company = q1.hk_company
        and q0.line_item_code = q1.line_item_code and q0.unit = q1.unit
        and q1.period_end = {{ bw_month_end(dbt.dateadd('month', -3, 'q0.period_end')) }}
    inner join single_quarter as q2
        on q0.version = q2.version and q0.hk_company = q2.hk_company
        and q0.line_item_code = q2.line_item_code and q0.unit = q2.unit
        and q2.period_end = {{ bw_month_end(dbt.dateadd('month', -6, 'q0.period_end')) }}
    inner join single_quarter as q3
        on q0.version = q3.version and q0.hk_company = q3.hk_company
        and q0.line_item_code = q3.line_item_code and q0.unit = q3.unit
        and q3.period_end = {{ bw_month_end(dbt.dateadd('month', -9, 'q0.period_end')) }}
),

duration_values as (
    select
        q.version,
        q.hk_company,
        q.line_item_code,
        'duration' as period_type,
        q.period_end,
        q.unit,
        q.value as amount,
        coalesce(a.value, t.value) as amount_ttm,
        q.derivation,
        q.source_filing,
        q.available_at
    from single_quarter as q
    left join annual as a
        on q.version = a.version and q.hk_company = a.hk_company
        and q.line_item_code = a.line_item_code and q.period_end = a.period_end and q.unit = a.unit
    left join ttm_from_quarters as t
        on q.version = t.version and q.hk_company = t.hk_company
        and q.line_item_code = t.line_item_code and q.period_end = t.period_end

    union all

    -- annual-only reporters (20-F, 40-F, ESEF): the year is known, the quarter is not
    select
        a.version, a.hk_company, a.line_item_code, 'duration', a.period_end, a.unit,
        cast(null as decimal(38, 6)), a.value, 'annual_only', cast(null as {{ bw_string(100) }}), a.available_at
    from annual as a
    where not exists (
        select 1 from single_quarter as q
        where q.version = a.version and q.hk_company = a.hk_company
            and q.line_item_code = a.line_item_code and q.period_end = a.period_end
    )
)

select * from duration_values

union all

select
    version,
    hk_company,
    line_item_code,
    'instant' as period_type,
    period_end,
    unit,
    value as amount,
    cast(null as decimal(38, 6)) as amount_ttm,
    'reported' as derivation,
    source_filing,
    available_at
from items
where period_type = 'instant'
