{#-
  Point-in-time table: for each hub key and each as-of date of a date spine, the
  effective_from of the satellite row that was valid on that date. Joining a PIT to its
  satellites with equality joins replaces costly range joins in the marts.

  satellites: list of dicts {name: 'sat_company_sec', alias: 'sec'}.
-#}
{% macro bw_pit(hub_model, hash_key, satellites, as_of_model, as_of_column='as_of_date') -%}
with spine as (
    select h.{{ hash_key }}, a.{{ as_of_column }}
    from {{ ref(hub_model) }} as h
    cross join {{ ref(as_of_model) }} as a
)

select
    spine.{{ hash_key }},
    spine.{{ as_of_column }},
    {%- for sat in satellites %}
    (
        select max(s.effective_from)
        from {{ ref(sat.name) }} as s
        where s.{{ hash_key }} = spine.{{ hash_key }}
            and s.effective_from <= spine.{{ as_of_column }}
    ) as {{ sat.alias }}_effective_from{{ "," if not loop.last }}
    {%- endfor %}
from spine
{%- endmacro %}
