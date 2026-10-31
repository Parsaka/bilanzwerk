{#-
  Link: one row per unique combination of hub keys. Insert-only.
-#}
{% macro bw_link(source_models, link_hash_key, foreign_hash_keys, extra_keys=[], load_datetime='load_datetime', record_source='record_source') -%}
with unioned as (
    {%- for src in source_models %}
    select
        {{ link_hash_key }},
        {%- for fk in foreign_hash_keys %}
        {{ fk }},
        {%- endfor %}
        {%- for k in extra_keys %}
        {{ k }},
        {%- endfor %}
        {{ load_datetime }},
        {{ record_source }}
    from {{ ref(src) }}
    where {{ link_hash_key }} is not null
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by {{ link_hash_key }} order by {{ load_datetime }}, {{ record_source }}
        ) as rn
    from unioned
)

select
    {{ link_hash_key }},
    {%- for fk in foreign_hash_keys %}
    {{ fk }},
    {%- endfor %}
    {%- for k in extra_keys %}
    {{ k }},
    {%- endfor %}
    {{ load_datetime }},
    {{ record_source }}
from ranked
where rn = 1
{%- if is_incremental() %}
    and not exists (
        select 1 from {{ this }} as tgt where tgt.{{ link_hash_key }} = ranked.{{ link_hash_key }}
    )
{%- endif %}
{%- endmacro %}
