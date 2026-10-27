-- Quarter and trailing-twelve-month (TTM) values per line item. Single quarters come from
-- bv_single_quarter (reported or derived from year-to-date values); TTM comes from the annual
-- figure or the sum of four consecutive quarters.
with items as (
    select * from {{ ref('bv_line_item_values') }}
),

single_quarter as (
    select * from {{ ref('bv_single_quarter') }}
),

annual as (
    select
        version,
        hk_company,
        line_item_code,
        period_end,
        unit,
        value,
        available_at
    from items
    where period_type = 'duration' and qtrs = 4
),

-- four consecutive quarters: the three previous rows end exactly 3, 6 and 9 month ends earlier
quarter_windows as (
    select
        version,
        hk_company,
        line_item_code,
        unit,
        period_end,
        sum(value) over (
            partition by version, hk_company, line_item_code, unit order by period_end
            rows between 3 preceding and current row
        ) as value_4q,
        lag(period_end, 1) over (partition by version, hk_company, line_item_code, unit order by period_end) as period_end_1,
        lag(period_end, 2) over (partition by version, hk_company, line_item_code, unit order by period_end) as period_end_2,
        lag(period_end, 3) over (partition by version, hk_company, line_item_code, unit order by period_end) as period_end_3
    from single_quarter
),

ttm_from_quarters as (
    select
        version,
        hk_company,
        line_item_code,
        period_end,
        value_4q as value
    from quarter_windows
    where
        period_end_1 = {{ bw_month_end(dbt.dateadd('month', -3, 'period_end')) }}
        and period_end_2 = {{ bw_month_end(dbt.dateadd('month', -6, 'period_end')) }}
        and period_end_3 = {{ bw_month_end(dbt.dateadd('month', -9, 'period_end')) }}
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
        on
            q.version = a.version and q.hk_company = a.hk_company
            and q.line_item_code = a.line_item_code and q.period_end = a.period_end and q.unit = a.unit
    left join ttm_from_quarters as t
        on
            q.version = t.version and q.hk_company = t.hk_company
            and q.line_item_code = t.line_item_code and q.period_end = t.period_end

    union all

    -- annual-only reporters (20-F, 40-F, ESEF): the year is known, the quarter is not
    select
        a.version,
        a.hk_company,
        a.line_item_code,
        'duration',
        a.period_end,
        a.unit,
        cast(null as decimal(38, 6)),
        a.value,
        'annual_only',
        cast(null as {{ bw_string(100) }}),
        a.available_at
    from annual as a
    where not exists (
        select 1 from single_quarter as q
        where
            q.version = a.version and q.hk_company = a.hk_company
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
