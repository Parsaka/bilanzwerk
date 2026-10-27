-- Every reported amount with the registrant and the filing's acceptance time: the input for
-- both point-in-time views. Only financial statement filings feed the facts.
select
    reg.hk_company,
    hc.company_bk_type,
    hc.company_bk,
    lf.hk_filing,
    hf.filing_bk,
    f.form,
    f.accepted_at,
    f.filed_date,
    f.period_end as filing_period_end,
    f.fiscal_year as filing_fiscal_year,
    f.fiscal_period as filing_fiscal_period,
    con.taxonomy,
    con.tag,
    lf.period_end,
    lf.qtrs,
    lf.unit,
    v.value
from {{ ref('link_fact') }} as lf
inner join {{ bw_sat_current('sat_fact_value', 'hk_fact') }} as v
    on lf.hk_fact = v.hk_fact
inner join {{ ref('hub_concept') }} as con
    on lf.hk_concept = con.hk_concept
inner join {{ ref('hub_filing') }} as hf
    on lf.hk_filing = hf.hk_filing
inner join {{ bw_sat_current('sat_filing', 'hk_filing') }} as f
    on lf.hk_filing = f.hk_filing
inner join {{ ref('link_filing_registrant') }} as reg
    on lf.hk_filing = reg.hk_filing
inner join {{ ref('hub_company') }} as hc
    on reg.hk_company = hc.hk_company
where
    con.taxonomy in ('us-gaap', 'ifrs-full')
    and (
        f.form in ('10-K', '10-Q', '10-K/A', '10-Q/A', '10-KT', '10-KT/A', '20-F', '20-F/A', '40-F', '40-F/A', 'AFR')
    )
