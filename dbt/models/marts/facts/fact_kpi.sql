-- One row per company, fiscal period, KPI and version: value, percentile within sector and
-- year (cross-section of all companies with the same period-end month), change over 1 and 4 quarters, and the red flag.
{%- set kpis = ['zpp', 'wc_ta', 're_ta', 'ebit_ta', 'eq_tl', 'ni_ta', 'cl_ca', 'ffo_tl', 'dso', 'dio', 'dpo', 'ccc',
                'current_ratio', 'quick_ratio', 'cash_runway_m', 'debt_ebitda', 'interest_coverage',
                'equity_ratio', 'rev_growth', 'ebit_margin', 'gross_margin', 'cfo_margin'] %}
{%- set signals = ['filing_lag_d', 'late_filing', 'restatement_count'] %}
with long_values as (
    {%- for k in kpis %}
        select
            version,
            company_id,
            company_key,
            sector_key,
            is_financial,
            period_key,
            period_end,
            '{{ k | upper }}' as kpi_code,
            cast({{ k }} as {{ bw_float() }}) as value,
            -- the KPI's own inputs; the opening balances of the year before are included
            {{ k }}_at as available_at
        from {{ ref('int_kpi_wide') }}
        where {{ k }} is not null
        union all
    {%- endfor %}
    {%- for s in signals %}
        select
            w.version,
            w.company_id,
            w.company_key,
            w.sector_key,
            w.is_financial,
            w.period_key,
            w.period_end,
            '{{ s | upper }}' as kpi_code,
            d.{{ s }} as value,
            d.first_accepted_at as available_at
        from {{ ref('int_data_signals') }} as d
        inner join {{ ref('int_kpi_wide') }} as w
            on d.period_key = w.period_key
        where d.{{ s }} is not null
        {%- if not loop.last %}
            union all
        {%- endif %}
    {%- endfor %}
),

with_changes as (
    select
        cur.*,
        cur.value - q1.value as change_1q,
        cur.value - q4.value as change_4q
    from long_values as cur
    left join long_values as q1
        on
            cur.version = q1.version and cur.company_id = q1.company_id and cur.kpi_code = q1.kpi_code
            and q1.period_end = {{ bw_month_end(dbt.dateadd('month', -3, 'cur.period_end')) }}
    left join long_values as q4
        on
            cur.version = q4.version and cur.company_id = q4.company_id and cur.kpi_code = q4.kpi_code
            and q4.period_end = {{ bw_month_end(dbt.dateadd('month', -12, 'cur.period_end')) }}
),

with_percentile as (
    select
        with_changes.*,
        percent_rank() over (
            partition by with_changes.version, with_changes.sector_key, year(with_changes.period_end), month(with_changes.period_end), with_changes.kpi_code order by with_changes.value
        ) as sector_percentile
    from with_changes
)

select
    p.company_key,
    p.company_id,
    p.period_key,
    p.period_end as period_end_date,
    p.kpi_code as kpi_key,
    p.version,
    p.value,
    p.sector_percentile,
    p.change_1q,
    p.change_4q,
    case
        when p.kpi_code = 'ZPP' and p.value < {{ var('zscore_distress_threshold') }} then 1
        when p.kpi_code = 'CCC' and p.sector_percentile > {{ var('ccc_red_flag_percentile') }} and p.change_4q > 0 then 1
        when
            p.kpi_code not in ('ZPP', 'CCC') and k.threshold_red is not null and k.direction = 'higher_is_better'
            and p.value < k.threshold_red then 1
        when
            p.kpi_code not in ('ZPP', 'CCC') and k.threshold_red is not null and k.direction = 'higher_is_worse'
            and p.value > k.threshold_red then 1
        else 0
    end as red_flag,
    p.available_at
from with_percentile as p
inner join {{ ref('kpi_definitions') }} as k
    on p.kpi_code = k.kpi_code
