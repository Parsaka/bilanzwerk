-- One row per company and period end. Fiscal year and quarter follow the company's fiscal
-- year end month (SEC "fye"), so prior-year comparatives get the same labels as filed periods.
with periods as (
    select distinct g.golden_company_id, v.period_end
    from {{ ref('bv_period_values') }} as v
    inner join {{ ref('bv_company_golden') }} as g
        on v.hk_company = g.hk_company
),

fye as (
    -- fiscal year end month: from the latest SEC statement, else the month of the annual report
    select golden_company_id, max(fye_month) as fye_month
    from (
        select
            g.golden_company_id,
            cast(left(s.fiscal_year_end_mmdd, 2) as {{ dbt.type_int() }}) as fye_month,
            row_number() over (partition by g.golden_company_id order by s.effective_from desc) as rn
        from {{ ref('sat_company_sec') }} as s
        inner join {{ ref('bv_company_golden') }} as g
            on s.hk_company = g.hk_company
        where s.fiscal_year_end_mmdd is not null and s.fiscal_year_end_mmdd <> ''

        union all

        select g.golden_company_id, month(p.period_end), 1
        from {{ ref('bv_company_periods') }} as p
        inner join {{ ref('bv_company_golden') }} as g
            on p.hk_company = g.hk_company
        where g.company_bk_type = 'LEI' and p.fiscal_period = 'FY'
    ) as x
    where rn = 1
    group by golden_company_id
),

filed as (
    select golden_company_id, period_end, fiscal_year as sec_fiscal_year, fiscal_period as sec_fiscal_period,
        first_form, first_filing, first_accepted_at, filing_lag_days
    from (
        select
            g.golden_company_id,
            p.*,
            row_number() over (partition by g.golden_company_id, p.period_end order by p.first_accepted_at) as rn
        from {{ ref('bv_company_periods') }} as p
        inner join {{ ref('bv_company_golden') }} as g
            on p.hk_company = g.hk_company
    ) as x
    where rn = 1
),

labelled as (
    select
        p.golden_company_id,
        p.period_end,
        coalesce(f.fye_month, 12) as fye_month,
        year(p.period_end) + case when month(p.period_end) > coalesce(f.fye_month, 12) then 1 else 0 end as fiscal_year,
        cast({{ bw_intdiv('(month(p.period_end) - coalesce(f.fye_month, 12) + 11) % 12', '3') }} + 1 as {{ dbt.type_int() }}) as fiscal_quarter
    from periods as p
    left join fye as f
        on p.golden_company_id = f.golden_company_id
)

select
    {{ bw_hash_key(['l.golden_company_id', 'l.period_end']) }} as period_key,
    l.golden_company_id as company_id,
    l.period_end as period_end_date,
    l.fiscal_year,
    l.fiscal_quarter,
    {{ dbt.concat(["'GJ '", "cast(l.fiscal_year as " ~ bw_string(4) ~ ")", "' Q'", "cast(l.fiscal_quarter as " ~ bw_string(1) ~ ")"]) }} as fiscal_period_label,
    case when l.fiscal_quarter = 4 then 1 else 0 end as is_fiscal_year_end,
    l.fye_month,
    year(l.period_end) as calendar_year,
    cast({{ bw_intdiv('month(l.period_end) - 1', '3') }} + 1 as {{ dbt.type_int() }}) as calendar_quarter,
    f.sec_fiscal_year,
    f.sec_fiscal_period,
    f.first_form,
    f.first_filing,
    f.first_accepted_at,
    f.filing_lag_days,
    case when f.first_filing is not null then 1 else 0 end as is_filed_period
from labelled as l
left join filed as f
    on l.golden_company_id = f.golden_company_id
    and l.period_end = f.period_end
