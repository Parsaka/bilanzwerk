-- Period values in local currency and EUR, attached to the golden company and the company
-- version (SCD2) that was valid at the period end.
-- Survivorship: a golden company can hold several source keys with values for the same period
-- (an SEC filer and its ESEF reports under the same LEI, or two CIKs that state one LEI). One
-- value per line item and period: SEC before ESEF (quarterly detail), reported before derived,
-- then the most recent source.
with values_golden as (
    select * from (
        select
            v.*,
            g.golden_company_id,
            row_number() over (
                partition by v.version, g.golden_company_id, v.line_item_code, v.period_end
                order by
                    case when g.company_bk_type = 'CIK' then 0 else 1 end asc,
                    case when v.derivation = 'reported' then 0 else 1 end asc,
                    v.available_at desc,
                    v.hk_company asc
            ) as source_rn
        from {{ ref('bv_period_values_eur') }} as v
        inner join {{ ref('bv_company_golden') }} as g
            on v.hk_company = g.hk_company
    ) as ranked
    where source_rn = 1
)

select
    v.version,
    v.golden_company_id as company_id,
    c.company_key,
    c.sector_key,
    c.is_financial,
    {{ bw_hash_key(['v.golden_company_id', 'v.period_end']) }} as period_key,
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
from values_golden as v
inner join {{ ref('dim_company') }} as c
    on
        v.golden_company_id = c.company_id
        and v.period_end >= c.valid_from
        and v.period_end < c.valid_to
