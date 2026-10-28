{#- Use the configured schema name as is (staging, raw_vault, marts, ...), without the
    target prefix, so the Warehouse has the same layer names in dev and prod. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
