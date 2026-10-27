-- Period values in local currency and EUR, attached to the golden company and the company
-- version (SCD2) that was valid at the period end.
select
    v.version,
    g.golden_company_id as company_id,
    c.company_key,
    c.sector_key,
    c.is_financial,
    {{ bw_hash_key(['g.golden_company_id', 'v.period_end']) }} as period_key,
    v.period_end,
    v.line_item_code,
    v.period_type,
    v.currency_code,
    v.amount_local,
    v.amount_ttm_local,
    v.fx_rate,
    v.fx_rate_ttm,
    cast(v.amount_local as {{ bw_float() }}) / nullif(v.fx_rate, 0) as amount_eur,
    cast(v.amount_ttm_local as {{ bw_float() }}) / nullif(v.fx_rate_ttm, 0) as amount_ttm_eur,
    v.derivation,
    v.source_filing,
    v.available_at
from {{ ref('bv_period_values_eur') }} as v
inner join {{ ref('bv_company_golden') }} as g
    on v.hk_company = g.hk_company
inner join {{ ref('dim_company') }} as c
    on
        g.golden_company_id = c.company_id
        and v.period_end >= c.valid_from
        and v.period_end < c.valid_to
