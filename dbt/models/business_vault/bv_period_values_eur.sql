-- Currency conversion to EUR (ADR-008): closing rate at period end for balance sheet items
-- (instants), average rate over the period for income and cash flow items (durations).
-- The local amount is kept next to the EUR amount.
with v as (
    select * from {{ ref('bv_period_values') }}
),

fx as (
    select * from {{ ref('bv_fx_daily') }}
)

select
    v.version,
    v.hk_company,
    v.line_item_code,
    v.period_type,
    v.period_end,
    v.unit as currency_code,
    v.amount as amount_local,
    v.amount_ttm as amount_ttm_local,
    case
        when v.unit = 'shares' then cast(1 as {{ bw_float() }})
        when v.period_type = 'instant' then close_fx.closing_rate_per_eur
        else {{ bw_div('q_end.cum_rate_sum - q_start.cum_rate_sum', 'q_end.cum_published_days - q_start.cum_published_days') }}
    end as fx_rate,
    case
        when v.unit = 'shares' then cast(1 as {{ bw_float() }})
        when v.period_type = 'instant' then close_fx.closing_rate_per_eur
        else {{ bw_div('q_end.cum_rate_sum - y_start.cum_rate_sum', 'q_end.cum_published_days - y_start.cum_published_days') }}
    end as fx_rate_ttm,
    v.derivation,
    v.source_filing,
    v.available_at
from v
left join fx as close_fx
    on
        v.unit = close_fx.currency_code
        and v.period_end = close_fx.date_day
left join fx as q_end
    on
        v.unit = q_end.currency_code
        and v.period_end = q_end.date_day
left join fx as q_start
    on
        v.unit = q_start.currency_code
        and q_start.date_day = {{ bw_month_end(dbt.dateadd('month', -3, 'v.period_end')) }}
left join fx as y_start
    on
        v.unit = y_start.currency_code
        and y_start.date_day = {{ bw_month_end(dbt.dateadd('month', -12, 'v.period_end')) }}
