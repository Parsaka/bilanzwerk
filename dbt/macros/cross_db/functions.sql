{#- Small cross-database helpers so every model runs on DuckDB (local, CI) and Fabric. -#}

{#- Continuous percentile as a window function over a partition. -#}
{% macro bw_percentile_over(expr, p, partition_by) -%}
    {{ adapter.dispatch('bw_percentile_over', 'bilanzwerk')(expr, p, partition_by) }}
{%- endmacro %}
{% macro default__bw_percentile_over(expr, p, partition_by) -%}
    quantile_cont({{ expr }}, {{ p }}) over (partition by {{ partition_by }})
{%- endmacro %}
{% macro fabric__bw_percentile_over(expr, p, partition_by) -%}
    percentile_cont({{ p }}) within group (order by {{ expr }}) over (partition by {{ partition_by }})
{%- endmacro %}

{#- 64-bit floating point type and safe division. dbt.type_float() is FLOAT on DuckDB, which is
    32-bit and loses amounts above about 16 million at the last digits; Fabric FLOAT is 64-bit. -#}
{% macro bw_float() -%}
    {{ adapter.dispatch('bw_float', 'bilanzwerk')() }}
{%- endmacro %}
{% macro default__bw_float() -%}double{%- endmacro %}
{% macro fabric__bw_float() -%}float{%- endmacro %}

{% macro bw_div(numerator, denominator) -%}
    cast({{ numerator }} as {{ bw_float() }}) / nullif(cast({{ denominator }} as {{ bw_float() }}), 0)
{%- endmacro %}

{#- Timestamp type and current time. -#}
{% macro bw_timestamp() -%}{{ dbt.type_timestamp() }}{%- endmacro %}

{% macro bw_run_ts() -%}
    cast('{{ run_started_at.strftime("%Y-%m-%d %H:%M:%S") }}' as {{ dbt.type_timestamp() }})
{%- endmacro %}

{#- Last day of the month of a date. -#}
{% macro bw_month_end(d) -%}
    {{ adapter.dispatch('bw_month_end', 'bilanzwerk')(d) }}
{%- endmacro %}
{% macro default__bw_month_end(d) -%}last_day({{ d }}){%- endmacro %}
{% macro fabric__bw_month_end(d) -%}eomonth({{ d }}){%- endmacro %}

{#- Text type with a length on Fabric. -#}
{% macro bw_string(n=none) -%}
    {{ adapter.dispatch('bw_string', 'bilanzwerk')(n) }}
{%- endmacro %}
{% macro default__bw_string(n) -%}varchar{%- endmacro %}
{% macro fabric__bw_string(n) -%}varchar({{ n or 8000 }}){%- endmacro %}

{#- Text contains: items like "1.03,9.01". -#}
{% macro bw_contains(haystack, needle) -%}
    ({{ haystack }} like '%{{ needle }}%')
{%- endmacro %}

{#- Restrict SEC FSDS staging to one quarter when the pipeline passes --vars "load_quarter: 2025q4".
    This is how a single quarter is (re)loaded without scanning the full history. -#}
{% macro bw_quarter_filter(column='quarter') -%}
    {%- if var('load_quarter', none) %} and {{ column }} = '{{ var("load_quarter") }}'{% endif -%}
{%- endmacro %}

{#- Round a date to the nearest month end, the way SEC FSDS rounds ddate and period
    (day 1-15 -> end of the previous month, day 16+ -> end of the same month). Applied to
    ESEF dates so both sources share one period grid. -#}
{% macro bw_nearest_month_end(d) -%}
    case
        when day({{ d }}) <= 15 then {{ bw_month_end(dbt.dateadd('month', -1, d)) }}
        else {{ bw_month_end(d) }}
    end
{%- endmacro %}

{#- A dense integer sequence 0..99999 built from cross joins (no recursion, works everywhere). -#}
{% macro bw_numbers() -%}
    select (d1.n + 10 * d2.n + 100 * d3.n + 1000 * d4.n + 10000 * d5.n) as n
    from (select 0 as n union all select 1 union all select 2 union all select 3 union all select 4
          union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) as d1
    cross join (select 0 as n union all select 1 union all select 2 union all select 3 union all select 4
          union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) as d2
    cross join (select 0 as n union all select 1 union all select 2 union all select 3 union all select 4
          union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) as d3
    cross join (select 0 as n union all select 1 union all select 2 union all select 3 union all select 4
          union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) as d4
    cross join (select 0 as n union all select 1 union all select 2 union all select 3 union all select 4
          union all select 5 union all select 6 union all select 7 union all select 8 union all select 9) as d5
{%- endmacro %}

{% macro bw_date_spine(start_date, end_date) -%}
    select cast({{ dbt.dateadd('day', 'n', "cast('" ~ start_date ~ "' as date)") }} as date) as date_day
    from ({{ bw_numbers() }}) as numbers
    where n <= {{ dbt.datediff("cast('" ~ start_date ~ "' as date)", "cast('" ~ end_date ~ "' as date)", 'day') }}
{%- endmacro %}

{#- Integer division (DuckDB's "/" returns a double). -#}
{% macro bw_intdiv(a, b) -%}
    {{ adapter.dispatch('bw_intdiv', 'bilanzwerk')(a, b) }}
{%- endmacro %}
{% macro default__bw_intdiv(a, b) -%}(({{ a }}) // ({{ b }})){%- endmacro %}
{% macro fabric__bw_intdiv(a, b) -%}(({{ a }}) / ({{ b }})){%- endmacro %}

{#- Latest of several timestamps, ignoring NULLs (an input a formula does not use is NULL).
    DuckDB and the Fabric warehouse both have GREATEST with this NULL rule. -#}
{% macro bw_greatest(exprs) -%}
    greatest({{ exprs | join(', ') }})
{%- endmacro %}

{#- greatest(<input>_at, ...) for a list of input column names. -#}
{% macro bw_greatest_at(inputs) -%}
    {%- set cols = [] -%}
    {%- for i in inputs %}{% do cols.append(i ~ '_at') %}{% endfor -%}
    {{ bw_greatest(cols) }}
{%- endmacro %}
