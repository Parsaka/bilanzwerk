{#-
  Satellite: descriptive attributes with full history. Insert-only.

  A new row is written only when the hash_diff differs from the previous row of the same
  parent key, ordered by the effective time (the business time the source states the
  values, e.g. the SEC acceptance datetime). This is checked twice:
    1. inside the incoming batch (several filings of one company in one quarter file), and
    2. against the latest row already in the satellite (incremental runs).
  Identical reruns therefore insert nothing.
-#}
{% macro bw_sat(source_model, parent_hash_key, hash_diff, payload, effective_from='effective_from', load_datetime='load_datetime', record_source='record_source') -%}
with staged as (
    select distinct
        {{ parent_hash_key }},
        {{ hash_diff }},
        {%- for col in payload %}
        {{ col }},
        {%- endfor %}
        {{ effective_from }},
        {{ load_datetime }},
        {{ record_source }}
    from {{ ref(source_model) }}
    where {{ parent_hash_key }} is not null
),

{%- if is_incremental() %}

latest_existing as (
    select {{ parent_hash_key }}, {{ hash_diff }}, {{ effective_from }}
    from (
        select
            {{ parent_hash_key }},
            {{ hash_diff }},
            {{ effective_from }},
            row_number() over (
                partition by {{ parent_hash_key }}
                order by {{ effective_from }} desc, {{ load_datetime }} desc
            ) as rn
        from {{ this }}
    ) as t
    where rn = 1
),

new_rows as (
    select s.*
    from staged as s
    left join latest_existing as e
        on s.{{ parent_hash_key }} = e.{{ parent_hash_key }}
    where e.{{ parent_hash_key }} is null
        or s.{{ effective_from }} > e.{{ effective_from }}
),

with_previous as (
    select
        n.*,
        coalesce(
            lag(n.{{ hash_diff }}) over (
                partition by n.{{ parent_hash_key }}
                order by n.{{ effective_from }}, n.{{ hash_diff }}
            ),
            e.{{ hash_diff }}
        ) as previous_hash_diff
    from new_rows as n
    left join latest_existing as e
        on n.{{ parent_hash_key }} = e.{{ parent_hash_key }}
)

{%- else %}

with_previous as (
    select
        s.*,
        lag(s.{{ hash_diff }}) over (
            partition by s.{{ parent_hash_key }}
            order by s.{{ effective_from }}, s.{{ hash_diff }}
        ) as previous_hash_diff
    from staged as s
)

{%- endif %}

select
    {{ parent_hash_key }},
    {{ hash_diff }},
    {%- for col in payload %}
    {{ col }},
    {%- endfor %}
    {{ effective_from }},
    {{ load_datetime }},
    {{ record_source }}
from with_previous
where previous_hash_diff is null
    or previous_hash_diff <> {{ hash_diff }}
{%- endmacro %}
