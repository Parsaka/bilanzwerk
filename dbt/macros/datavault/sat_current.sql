{#- The current (latest effective) row of a satellite per parent key, as a subquery. -#}
{% macro bw_sat_current(sat_model, parent_hash_key) -%}
(
    select *
    from (
        select
            s.*,
            row_number() over (
                partition by s.{{ parent_hash_key }} order by s.effective_from desc, s.load_datetime desc
            ) as sat_rn
        from {{ ref(sat_model) }} as s
    ) as ranked
    where sat_rn = 1
)
{%- endmacro %}
