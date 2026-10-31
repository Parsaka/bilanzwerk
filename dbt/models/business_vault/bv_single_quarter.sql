-- Single quarters: reported (qtrs = 1) or derived from year-to-date values by subtraction
-- (Q2 = H1 - Q1, Q3 = 9M - H1, Q4 = FY - 9M). FSDS rounds period ends to month ends (ESEF is
-- rounded the same way in staging), so the previous YTD period ends exactly three month ends
-- earlier. A table of its own: bv_period_values joins it several times, which on the full SEC
-- history does not fit in memory as a CTE.
with items as (
    select * from {{ ref('bv_line_item_values') }}
),

durations as (
    select * from items
    where period_type = 'duration'
),

direct_quarter as (
    select
        version,
        hk_company,
        line_item_code,
        period_end,
        unit,
        value,
        source_filing,
        available_at,
        1 as derivation_rank,
        'reported' as derivation
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
        on
            cur.version = prev.version
            and cur.hk_company = prev.hk_company
            and cur.line_item_code = prev.line_item_code
            and cur.unit = prev.unit
            and prev.qtrs = cur.qtrs - 1
            and prev.period_end = {{ bw_month_end(dbt.dateadd('month', -3, 'cur.period_end')) }}
    where cur.qtrs between 2 and 4
),

single_quarter as (
    select
        version,
        hk_company,
        line_item_code,
        period_end,
        unit,
        value,
        source_filing,
        available_at,
        derivation
    from (
        select
            q.*,
            row_number() over (
                partition by q.version, q.hk_company, q.line_item_code, q.period_end
                order by q.derivation_rank
            ) as rn
        from (
            select * from direct_quarter
            union all
            select * from derived_quarter
        ) as q
    ) as ranked
    where rn = 1
)

select * from single_quarter
