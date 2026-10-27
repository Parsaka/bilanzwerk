-- Grain: company, fiscal period, line item, scenario, version (first reported or latest).
-- Ist values from the filings; Plan and Forecast revenue from int_revenue_plan.
select
    company_key,
    company_id,
    period_key,
    period_end as period_end_date,
    line_item_code as line_item_key,
    'IST' as scenario_key,
    version,
    currency_code as currency_key,
    cast(amount_local as {{ bw_float() }}) as amount_local,
    amount_eur,
    cast(amount_ttm_local as {{ bw_float() }}) as amount_ttm_local,
    amount_ttm_eur,
    fx_rate,
    derivation,
    source_filing,
    available_at
from {{ ref('int_period_values_golden') }}

union all

select
    company_key,
    company_id,
    period_key,
    period_end,
    'REV',
    scenario_code,
    '{{ var("version_first_reported") }}',
    currency_code,
    amount_local,
    amount_local / nullif(fx_rate, 0),
    cast(null as {{ bw_float() }}),
    cast(null as {{ bw_float() }}),
    fx_rate,
    'forecast',
    cast(null as {{ bw_string(100) }}),
    freeze_at
from {{ ref('int_revenue_plan') }}
