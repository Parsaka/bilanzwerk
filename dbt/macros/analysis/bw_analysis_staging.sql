{#
  Staging for a table the early-warning model writes back (source `analysis`): typed columns,
  and an empty relation with the same columns until the first model run
  (env BW_HAS_RISK_SCORES, as for risk_scores). `columns` is a list of [name, sql type].
#}
{% macro bw_analysis_staging(table, columns) %}
{% if env_var('BW_HAS_RISK_SCORES', 'false') == 'true' %}
    select
    {%- for name, type in columns %}
        cast({{ name }} as {{ type }}) as {{ name }}{{ "," if not loop.last }}
    {%- endfor %}
    from {{ source('analysis', table) }}
{% else %}
select
{%- for name, type in columns %}
    cast(null as {{ type }}) as {{ name }}{{ "," if not loop.last }}
{%- endfor %}
where 1 = 0
{% endif %}
{% endmacro %}
