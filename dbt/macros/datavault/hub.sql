{#-
  Hub: one row per business key. Insert-only. The first load wins and is never updated.

  source_models: list of staged relations that carry the hub's hash key and business key
  columns (same names in every source). Several sources can feed one hub (SEC and ESEF).
-#}
{% macro bw_hub(source_models, hash_key, business_keys, load_datetime='load_datetime', record_source='record_source') -%}
{%- set bk_list = business_keys if business_keys is not string else [business_keys] -%}
with unioned as (
    {%- for src in source_models %}
    select
        {{ hash_key }},
        {%- for bk in bk_list %}
        {{ bk }},
        {%- endfor %}
        {{ load_datetime }},
        {{ record_source }}
    from {{ ref(src) }}
    where {{ hash_key }} is not null
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by {{ hash_key }} order by {{ load_datetime }}, {{ record_source }}
        ) as rn
    from unioned
)

select
    {{ hash_key }},
    {%- for bk in bk_list %}
    {{ bk }},
    {%- endfor %}
    {{ load_datetime }},
    {{ record_source }}
from ranked
where rn = 1
{%- if is_incremental() %}
    and not exists (
        select 1 from {{ this }} as tgt where tgt.{{ hash_key }} = ranked.{{ hash_key }}
    )
{%- endif %}
{%- endmacro %}
