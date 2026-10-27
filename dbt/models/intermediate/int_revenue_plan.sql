-- Plan and forecast revenue per company and quarter, built only from data that was public at
-- the freeze date (point-in-time):
--   PLAN: frozen on 1 January of the period's calendar year (the controller's budget view)
--   FC:   frozen on the first day of the quarter (rolling forecast)
-- Method: same quarter of the previous year x (1 + TTM revenue growth known at the freeze
-- date), growth capped to +-50 %. A simple, explainable seasonal naive forecast.
with q as (
    select company_id, company_key, period_key, period_end, currency_code,
        amount_local, amount_ttm_local, fx_rate, available_at
    from {{ ref('int_period_values_golden') }}
    where version = '{{ var("version_first_reported") }}'
        and line_item_code = 'REV'
        and amount_local is not null
),

targets as (
    select
        q.*,
        'PLAN' as scenario_code,
        cast({{ dbt.concat(["cast(year(q.period_end) as " ~ bw_string(4) ~ ")", "'-01-01'"]) }} as {{ bw_timestamp() }}) as freeze_at
    from q
    union all
    select
        q.*,
        'FC',
        cast({{ dbt.dateadd('day', 1, bw_month_end(dbt.dateadd('month', -3, 'q.period_end'))) }} as {{ bw_timestamp() }})
    from q
),

base as (
    select
        t.*,
        prev.amount_local as base_amount,
        prev.available_at as base_available_at
    from targets as t
    left join q as prev
        on t.company_id = prev.company_id
        and prev.period_end = {{ bw_month_end(dbt.dateadd('month', -12, 't.period_end')) }}
        and prev.available_at < t.freeze_at
),

growth as (
    -- latest TTM growth known at the freeze date
    select company_id, scenario_code, period_end, growth
    from (
        select
            t.company_id,
            t.scenario_code,
            t.period_end,
            {{ bw_div('g.amount_ttm_local', 'g_prev.amount_ttm_local') }} - 1 as growth,
            row_number() over (
                partition by t.company_id, t.scenario_code, t.period_end order by g.period_end desc
            ) as rn
        from targets as t
        inner join q as g
            on t.company_id = g.company_id
            and g.available_at < t.freeze_at
        inner join q as g_prev
            on g.company_id = g_prev.company_id
            and g_prev.period_end = {{ bw_month_end(dbt.dateadd('month', -12, 'g.period_end')) }}
        where g.amount_ttm_local is not null and g_prev.amount_ttm_local > 0
    ) as ranked
    where rn = 1
)

select
    b.company_id,
    b.company_key,
    b.period_key,
    b.period_end,
    b.scenario_code,
    b.currency_code,
    b.freeze_at,
    cast(b.base_amount as {{ bw_float() }})
        * (1 + case when g.growth > 0.5 then 0.5 when g.growth < -0.5 then -0.5 else coalesce(g.growth, 0) end)
        as amount_local,
    b.fx_rate
from base as b
left join growth as g
    on b.company_id = g.company_id
    and b.scenario_code = g.scenario_code
    and b.period_end = g.period_end
where b.base_amount is not null
