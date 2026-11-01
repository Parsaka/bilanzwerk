-- All KPIs per company, period and version (formulas: seed kpi_definitions).
-- Averages of opening and closing balances use the balance four quarters earlier.
-- <kpi>_at is the latest acceptance time of the inputs the formula uses (fallbacks included).
-- Dating every KPI by the latest item of the whole row let one item that was first reported a
-- year later (e.g. in the next 10-K's comparatives) hide every KPI of that period at its own
-- as-of date; in run 41272420173 Z'' was usable at the last quarter before a bankruptcy for
-- only 66 % of the companies, CCC for 35 %.
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
        prev.ar_at as ar_open_at,
        prev.inv_at as inv_open_at,
        prev.ap_at as ap_open_at,
        prev.rev_at as rev_prev_at,
        case when prev.available_at > cur.available_at then prev.available_at else cur.available_at end as available_at_all
    from {{ ref('int_company_period_wide') }} as cur
    left join {{ ref('int_company_period_wide') }} as prev
        on
            cur.version = prev.version
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
            when w.inv is null and w.ar is not null and w.cogs_ttm_f is not null then 0
            else {{ bw_div('(coalesce(inv_open, inv) + inv) / 2', 'cogs_ttm_f') }} * 365
        end as dio,
        {{ bw_div('(coalesce(ap_open, ap) + ap) / 2', 'cogs_ttm_f') }} * 365 as dpo,
        {{ bw_div('tca', 'tcl') }} as current_ratio,
        {{ bw_div('tca - coalesce(inv, 0)', 'tcl') }} as quick_ratio,
        case when w.cfo_ttm < 0 then {{ bw_div('cash', '-cfo_ttm / 12') }} end as cash_runway_m,
        case
            when w.ebit_ttm_f + coalesce(w.da_ttm, 0) > 0
                then {{ bw_div('coalesce(std, 0) + coalesce(ltd, 0)', 'ebit_ttm_f + coalesce(da_ttm, 0)') }}
        end as debt_ebitda,
        {{ bw_div('ebit_ttm_f', 'intexp_ttm') }} as interest_coverage,
        {{ bw_div('eq_f', 'ta') }} as equity_ratio,
        {{ bw_div('rev_ttm', 'rev_ttm_prev_year') }} - 1 as rev_growth,
        {{ bw_div('ebit_ttm_f', 'rev_ttm') }} as ebit_margin,
        {{ bw_div('rev_ttm - cogs_ttm_f', 'rev_ttm') }} as gross_margin,
        {{ bw_div('cfo_ttm', 'rev_ttm') }} as cfo_margin,
        {{ bw_greatest_at(['tca', 'tcl', 'ta']) }} as wc_ta_at,
        {{ bw_greatest_at(['re', 'ta']) }} as re_ta_at,
        {{ bw_greatest_at(['ebit', 'ebt', 'intexp', 'ta']) }} as ebit_ta_at,
        {{ bw_greatest_at(['eq', 'eqp', 'tl', 'tle', 'ta']) }} as eq_tl_at,
        {{ bw_greatest_at(['ni', 'ta']) }} as ni_ta_at,
        {{ bw_greatest_at(['tcl', 'tca']) }} as cl_ca_at,
        {{ bw_greatest_at(['ni', 'da', 'tl', 'tle', 'eq', 'eqp', 'ta']) }} as ffo_tl_at,
        {{ bw_greatest_at(['ar', 'ar_open', 'rev']) }} as dso_at,
        {{ bw_greatest_at(['inv', 'inv_open', 'ar', 'cogs', 'rev', 'gp']) }} as dio_at,
        {{ bw_greatest_at(['ap', 'ap_open', 'cogs', 'rev', 'gp']) }} as dpo_at,
        {{ bw_greatest_at(['tca', 'tcl']) }} as current_ratio_at,
        {{ bw_greatest_at(['tca', 'inv', 'tcl']) }} as quick_ratio_at,
        {{ bw_greatest_at(['cfo', 'cash']) }} as cash_runway_m_at,
        {{ bw_greatest_at(['ebit', 'ebt', 'intexp', 'da', 'std', 'ltd']) }} as debt_ebitda_at,
        {{ bw_greatest_at(['ebit', 'ebt', 'intexp']) }} as interest_coverage_at,
        {{ bw_greatest_at(['eq', 'eqp', 'ta']) }} as equity_ratio_at,
        {{ bw_greatest_at(['rev', 'rev_prev']) }} as rev_growth_at,
        {{ bw_greatest_at(['ebit', 'ebt', 'intexp', 'rev']) }} as ebit_margin_at,
        {{ bw_greatest_at(['rev', 'cogs', 'gp']) }} as gross_margin_at,
        {{ bw_greatest_at(['cfo', 'rev']) }} as cfo_margin_at
    from w
)

select
    ratios.*,
    6.56 * ratios.wc_ta + 3.26 * ratios.re_ta + 6.72 * ratios.ebit_ta + 1.05 * ratios.eq_tl as zpp,
    ratios.dso + ratios.dio - ratios.dpo as ccc,
    {{ bw_greatest(['ratios.wc_ta_at', 'ratios.re_ta_at', 'ratios.ebit_ta_at', 'ratios.eq_tl_at']) }} as zpp_at,
    {{ bw_greatest(['ratios.dso_at', 'ratios.dio_at', 'ratios.dpo_at']) }} as ccc_at
from ratios
