{#-
  Generic data-quality tests. These replace the dbt-expectations package, which has no
  maintained Fabric support (ADR-010). Each returns the failing rows.
-#}

{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}

{% test values_between(model, column_name, min_value=none, max_value=none, where=none) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
    {%- if where %} and ({{ where }}){% endif %}
    and (
        1 = 0
        {%- if min_value is not none %} or {{ column_name }} < {{ min_value }}{% endif %}
        {%- if max_value is not none %} or {{ column_name }} > {{ max_value }}{% endif %}
    )
{% endtest %}

{% test matches_iso_currency(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
    and {{ column_name }} not in (select currency_code from {{ ref('currencies') }})
{% endtest %}

{% test row_count_reconciles(model, compare_model, compare_column, column_name=none) %}
{#- Every distinct key in compare_model must exist in model (hub/link vs staging). -#}
select c.{{ compare_column }}
from (select distinct {{ compare_column }} from {{ compare_model }} where {{ compare_column }} is not null) as c
left join (select distinct {{ compare_column }} from {{ model }}) as m
    on c.{{ compare_column }} = m.{{ compare_column }}
where m.{{ compare_column }} is null
{% endtest %}

{% test pass_rate_at_least(model, numerator, denominator, threshold, where=none) %}
select sum({{ numerator }}) as passed, sum({{ denominator }}) as checked
from {{ model }}
{%- if where %} where {{ where }}{% endif %}
having sum({{ denominator }}) > 0
    and cast(sum({{ numerator }}) as {{ dbt.type_float() }}) / sum({{ denominator }}) < {{ threshold }}
{% endtest %}

{% test hash_is_sha256_hex(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is null or {{ dbt.length(column_name) }} <> 64
{% endtest %}

{% test no_overlapping_sic_ranges(model) %}
select a.sic_from, a.sic_to, b.sic_from as other_from, b.sic_to as other_to
from {{ model }} as a
join {{ model }} as b
    on a.sic_from < b.sic_from
    and a.sic_to >= b.sic_from
{% endtest %}

{% test scd2_no_overlap(model, key) %}
{#- SCD Type 2: versions of one key never overlap and valid_from < valid_to. -#}
select a.{{ key }}, a.valid_from, a.valid_to
from {{ model }} as a
join {{ model }} as b
    on a.{{ key }} = b.{{ key }}
    and a.valid_from < b.valid_from
    and a.valid_to > b.valid_from
union all
select {{ key }}, valid_from, valid_to
from {{ model }}
where valid_from >= valid_to
{% endtest %}
