-- Point-in-time view: for each company, concept, period and duration the value from the
-- earliest accepted filing. This is the only version the early-warning model may use.
-- Every 10-K repeats prior-year numbers; those repeats never replace the first value.
select
    hk_company,
    company_bk_type,
    company_bk,
    taxonomy,
    tag,
    period_end,
    qtrs,
    unit,
    value,
    filing_bk as source_filing,
    form as source_form,
    accepted_at as available_at,
    filing_period_end,
    filing_fiscal_year,
    filing_fiscal_period
from (
    select
        v.*,
        row_number() over (
            partition by v.hk_company, v.taxonomy, v.tag, v.period_end, v.qtrs, v.unit
            order by v.accepted_at, v.filing_bk
        ) as rn
    from {{ ref('bv_fact_versions') }} as v
) as ranked
where rn = 1
