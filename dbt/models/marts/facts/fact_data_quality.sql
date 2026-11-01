-- Data quality scorecard: one row per run, rule and table, appended on every dbt run.
{{ config(materialized='incremental', incremental_strategy='append') }}

{%- set fy_filter = "version = '" ~ var('version_first_reported') ~ "'" %}
with rules as (

    -- Completeness: every 10-K / annual period has revenue, total assets and total liabilities
    select
        'COMPL_ANNUAL_CORE' as rule_code,
        'Completeness' as dq_dimension,
        'int_company_period_wide' as table_name,
        count(*) as rows_checked,
        sum(case when w.rev_ttm is null or w.ta is null or coalesce(w.tl, w.tle - w.eq) is null then 1 else 0 end) as rows_failed,
        cast(0.95 as {{ bw_float() }}) as target_pass_rate
    from {{ ref('int_company_period_wide') }} as w
    inner join {{ ref('dim_period') }} as p on w.period_key = p.period_key
    where
        w.{{ fy_filter }} and p.is_filed_period = 1 and p.first_form in ('10-K', '20-F', '40-F', 'AFR')
        and w.is_financial = 0

    union all

    -- Completeness: every SEC filer has a golden record
    select
        'COMPL_GOLDEN_RECORD',
        'Completeness',
        'bv_company_golden',
        count(*),
        sum(case when g.golden_company_id is null then 1 else 0 end),
        cast(1.0 as {{ bw_float() }})
    from {{ ref('hub_company') }} as h
    left join {{ ref('bv_company_golden') }} as g on h.hk_company = g.hk_company
    where h.company_bk_type = 'CIK'

    union all

    -- Validity: currencies are ISO codes
    select
        'VALID_ISO_CURRENCY',
        'Validity',
        'fact_financial_line',
        count(*),
        sum(case when c.currency_code is null then 1 else 0 end),
        cast(1.0 as {{ bw_float() }})
    from {{ ref('fact_financial_line') }} as f
    left join {{ ref('dim_currency') }} as c on f.currency_key = c.currency_code

    union all

    -- Validity: ratios within plausible bounds (equity ratio between -5 and 1)
    select
        'VALID_EQUITY_RATIO_BOUNDS',
        'Validity',
        'fact_kpi',
        count(*),
        sum(case when value < -5 or value > 1 then 1 else 0 end),
        cast(0.99 as {{ bw_float() }})
    from {{ ref('fact_kpi') }}
    where kpi_key = 'EQUITY_RATIO'

    union all

    -- Uniqueness: one row per grain in fact_financial_line
    select
        'UNIQ_FACT_FINANCIAL_LINE',
        'Uniqueness',
        'fact_financial_line',
        count(*),
        count(*) - count(distinct {{ dbt.concat(['company_id', "'|'", 'period_key', "'|'", 'line_item_key', "'|'", 'scenario_key', "'|'", 'version']) }}),
        cast(1.0 as {{ bw_float() }})
    from {{ ref('fact_financial_line') }}

    union all

    -- Uniqueness: one golden record per LEI
    select
        'UNIQ_GOLDEN_PER_LEI',
        'Uniqueness',
        'dim_company',
        count(distinct lei),
        count(distinct lei) - count(distinct case when n_ciks <= 1 then lei end),
        cast(0.99 as {{ bw_float() }})
    from {{ ref('dim_company') }}
    where is_current = 1 and lei is not null

    union all

    -- Consistency: Aktiva = Passiva within 0.5 % (the balance check, SLA >= 98 %)
    select
        'CONS_BALANCE_CHECK',
        'Consistency',
        'int_company_period_wide',
        count(*),
        sum(case when abs(ta - tle) > {{ var('balance_check_tolerance') }} * abs(ta) then 1 else 0 end),
        cast({{ var('balance_check_target_pass_rate') }} as {{ bw_float() }})
    from {{ ref('int_company_period_wide') }}
    where {{ fy_filter }} and ta is not null and tle is not null

    union all

    -- Consistency: cash at period end in the cash flow statement equals balance sheet cash
    select
        'CONS_CASH_BS_CF',
        'Consistency',
        'int_company_period_wide',
        count(*),
        sum(case when abs(cash - cash_cf) > 0.01 * greatest(abs(cash), 1) then 1 else 0 end),
        cast(0.90 as {{ bw_float() }})
    from {{ ref('int_company_period_wide') }}
    where {{ fy_filter }} and cash is not null and cash_cf is not null

    union all

    -- Consistency: four reported quarters add up to the reported year (revenue)
    select
        'CONS_QUARTERS_SUM_TO_YEAR',
        'Consistency',
        'bv_period_values',
        count(*),
        sum(case when abs(q.sum_q - a.value) > 0.005 * greatest(abs(a.value), 1) then 1 else 0 end),
        cast(0.98 as {{ bw_float() }})
    from (
        select
            q0.hk_company,
            q0.period_end,
            q0.amount + q1.amount + q2.amount + q3.amount as sum_q
        from {{ ref('bv_period_values') }} as q0
        inner join {{ ref('bv_period_values') }} as q1
            on
                q0.hk_company = q1.hk_company and q0.version = q1.version and q0.line_item_code = q1.line_item_code
                and q1.period_end = {{ bw_month_end(dbt.dateadd('month', -3, 'q0.period_end')) }}
        inner join {{ ref('bv_period_values') }} as q2
            on
                q0.hk_company = q2.hk_company and q0.version = q2.version and q0.line_item_code = q2.line_item_code
                and q2.period_end = {{ bw_month_end(dbt.dateadd('month', -6, 'q0.period_end')) }}
        inner join {{ ref('bv_period_values') }} as q3
            on
                q0.hk_company = q3.hk_company and q0.version = q3.version and q0.line_item_code = q3.line_item_code
                and q3.period_end = {{ bw_month_end(dbt.dateadd('month', -9, 'q0.period_end')) }}
        where
            q0.{{ fy_filter }} and q0.line_item_code = 'REV'
            and q1.derivation = 'reported' and q2.derivation = 'reported' and q3.derivation = 'reported'
            and q0.derivation = 'reported'
    ) as q
    inner join {{ ref('bv_line_item_values') }} as a
        on
            q.hk_company = a.hk_company and q.period_end = a.period_end
            and a.line_item_code = 'REV' and a.qtrs = 4 and a.{{ fy_filter }}

    union all

    -- Accuracy signal: total assets jump by the scaling factor against both neighbouring periods of
    -- the same company and come back (an XBRL scaling error: thousands tagged as units or the
    -- reverse). The first version compared with the sector median and flagged 8 % of the real
    -- periods, mostly shell companies that are genuinely 1,000 times smaller than the median
    -- (run 41245747626), which is size, not an error.
    select
        'SCALE_OUTLIER_TOTAL_ASSETS',
        'Validity',
        'int_company_period_wide',
        count(*),
        sum(
            case
                when
                    (ta > {{ var('scale_outlier_jump') }} * prev_ta and ta > {{ var('scale_outlier_jump') }} * next_ta)
                    or (ta * {{ var('scale_outlier_jump') }} < prev_ta and ta * {{ var('scale_outlier_jump') }} < next_ta)
                    then 1
                else 0
            end
        ),
        cast(0.999 as {{ bw_float() }})
    from (
        select
            w.ta,
            lag(w.ta) over (partition by w.company_id order by w.period_end) as prev_ta,
            lead(w.ta) over (partition by w.company_id order by w.period_end) as next_ta
        from {{ ref('int_company_period_wide') }} as w
        where w.{{ fy_filter }} and w.ta > 0
    ) as s
    where prev_ta > 0 and next_ta > 0

    union all

    -- Timeliness: the newest SEC statement was accepted within the last 100 days
    select
        'TIMELY_SEC_QUARTER',
        'Timeliness',
        'sat_filing',
        1,
        case when max(accepted_at) < {{ dbt.dateadd('day', -100, bw_run_ts()) }} then 1 else 0 end,
        cast(1.0 as {{ bw_float() }})
    from {{ ref('sat_filing') }}

    union all

    -- Master data: share of SEC filers matched to an LEI (a metric; no target)
    select
        'MDM_LEI_MATCH_RATE',
        'Master data',
        'bv_company_golden',
        count(*),
        sum(case when lei is null then 1 else 0 end),
        cast(null as {{ bw_float() }})
    from {{ ref('bv_company_golden') }}
    where
        company_bk_type = 'CIK'
        -- the filers in scope of the matching: those with a financial statement in the vault,
        -- not the ~1 M insiders and funds in the SEC submissions file
        and hk_company in (select p.hk_company from {{ ref('bv_company_periods') }} as p)
)

select
    cast('{{ invocation_id }}' as {{ bw_string(64) }}) as run_id,
    {{ bw_run_ts() }} as run_at,
    rule_code,
    dq_dimension,
    table_name,
    rows_checked,
    rows_failed,
    {{ bw_div('rows_checked - rows_failed', 'rows_checked') }} as pass_rate,
    target_pass_rate,
    case
        when target_pass_rate is null then 'info'
        when rows_checked = 0 then 'no_data'
        when {{ bw_div('rows_checked - rows_failed', 'rows_checked') }} >= target_pass_rate then 'pass'
        else 'fail'
    end as status
from rules
-- a `dbt run --empty` (schema-only, used before unit tests) checks no rows at all and is not a run
-- of the scorecard
where (select sum(r.rows_checked) from rules as r) > 0
