-- All KPIs per company, period and version (formulas: seed kpi_definitions).
-- Averages of opening and closing balances use the balance four quarters earlier.
with w as (
    select
        cur.*,
        -- fallbacks for line items companies often leave out
        coalesce(cur.tl, cur.tle - coalesce(cur.eq, cur.eqp), cur.ta - coalesce(cur.eq, cur.eqp)) as tl_f,
        coalesce(cur.eq, cur.eqp) as eq_f,
        coalesce(cur.ebit_ttm, cur.ebt_ttm + cur.intexp_ttm) as ebit_ttm_f,
        coalesce(cur.cogs_ttm, cur.rev_ttm - cur.gp_ttm) as cogs_ttm_f,
        prev.ar as ar_open,
        prev.inv as inv_open,
        prev.ap as ap_open,
        prev.rev_ttm as rev_ttm_prev_year,
        case when prev.available_at > cur.available_at then prev.available_at else cur.available_at end as available_at_all
    from {{ ref('int_company_period_wide') }} as cur
    left join {{ ref('int_company_period_wide') }} as prev
        on cur.version = prev.version
        and cur.company_id = prev.company_id
        and prev.period_end = {{ bw_month_end(dbt.dateadd('month', -12, 'cur.period_end')) }}
),

ratios as (
    select
        w.*,
        {{ bw_div('tca - tcl', 'ta') }} as wc_ta,
        {{ bw_div('re', 'ta') }} as re_ta,
        {{ bw_div('ebit_ttm_f', 'ta') }} as ebit_ta,
        {{ bw_div('eq_f', 'tl_f') }} as eq_tl,
        {{ bw_div('ni_ttm', 'ta') }} as ni_ta,
        {{ bw_div('tcl', 'tca') }} as cl_ca,
        {{ bw_div('ni_ttm + coalesce(da_ttm, 0)', 'tl_f') }} as ffo_tl,
        {{ bw_div('(coalesce(ar_open, ar) + ar) / 2', 'rev_ttm') }} * 365 as dso,
        case
            when inv is null and ar is not null and cogs_ttm_f is not null then 0
            else {{ bw_div('(coalesce(inv_open, inv) + inv) / 2', 'cogs_ttm_f') }} * 365
        end as dio,
        {{ bw_div('(coalesce(ap_open, ap) + ap) / 2', 'cogs_ttm_f') }} * 365 as dpo,
        {{ bw_div('tca', 'tcl') }} as current_ratio,
        {{ bw_div('tca - coalesce(inv, 0)', 'tcl') }} as quick_ratio,
        case when cfo_ttm < 0 then {{ bw_div('cash', '-cfo_ttm / 12') }} end as cash_runway_m,
        case when ebit_ttm_f + coalesce(da_ttm, 0) > 0
            then {{ bw_div('coalesce(std, 0) + coalesce(ltd, 0)', 'ebit_ttm_f + coalesce(da_ttm, 0)') }}
        end as debt_ebitda,
        {{ bw_div('ebit_ttm_f', 'intexp_ttm') }} as interest_coverage,
        {{ bw_div('eq_f', 'ta') }} as equity_ratio,
        {{ bw_div('rev_ttm', 'rev_ttm_prev_year') }} - 1 as rev_growth,
        {{ bw_div('ebit_ttm_f', 'rev_ttm') }} as ebit_margin,
        {{ bw_div('rev_ttm - cogs_ttm_f', 'rev_ttm') }} as gross_margin,
        {{ bw_div('cfo_ttm', 'rev_ttm') }} as cfo_margin
    from w
)

select
    ratios.*,
    6.56 * wc_ta + 3.26 * re_ta + 6.72 * ebit_ta + 1.05 * eq_tl as zpp,
    dso + dio - dpo as ccc
from ratios
