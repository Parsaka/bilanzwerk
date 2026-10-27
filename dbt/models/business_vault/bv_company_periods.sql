-- The fiscal period calendar per company: one row per period end that the company filed a
-- 10-K / 10-Q (or ESEF report) for, with fiscal year, quarter and the first acceptance time.
with filings as (
    select
        reg.hk_company,
        f.period_end,
        f.fiscal_year,
        f.fiscal_period,
        f.form,
        f.accepted_at,
        hf.filing_bk,
        row_number() over (
            partition by reg.hk_company, f.period_end order by f.accepted_at, hf.filing_bk
        ) as rn
    from {{ bw_sat_current('sat_filing', 'hk_filing') }} as f
    inner join {{ ref('link_filing_registrant') }} as reg
        on f.hk_filing = reg.hk_filing
    inner join {{ ref('hub_filing') }} as hf
        on f.hk_filing = hf.hk_filing
    where
        f.form in ('10-K', '10-Q', '10-KT', '20-F', '40-F', 'AFR')
        and f.period_end is not null
)

select
    hk_company,
    period_end,
    fiscal_year,
    case fiscal_period
        when 'Q1' then 1 when 'Q2' then 2 when 'Q3' then 3 when 'FY' then 4 when 'Q4' then 4
    end as fiscal_quarter,
    fiscal_period,
    form as first_form,
    filing_bk as first_filing,
    accepted_at as first_accepted_at,
    {{ dbt.datediff('period_end', 'cast(accepted_at as date)', 'day') }} as filing_lag_days
from filings
where rn = 1
