{#-
  Data Vault hash keys and hash diffs.

  Convention (ADR-004): SHA-256 over the upper-cased, trimmed business key parts joined by
  "||", rendered as 64 lower-case hex characters. NULL parts become the empty string so a
  hash is never NULL. The output is byte-identical on DuckDB and on the Fabric Warehouse
  (UTF-8 collation), so local and cloud loads produce the same keys.

  hash_diff uses the same rule but keeps the case of the attributes, because a change from
  "Apple Inc" to "APPLE INC" is a real change in the source.
-#}

{% macro bw_hash_key(columns) -%}
    {{ bw_hash(columns, upper=true) }}
{%- endmacro %}

{% macro bw_hash_diff(columns) -%}
    {{ bw_hash(columns, upper=false) }}
{%- endmacro %}

{% macro bw_hash(columns, upper=true) -%}
    {%- if columns is string -%}{%- set columns = [columns] -%}{%- endif -%}
    {%- set parts = [] -%}
    {%- for col in columns -%}
        {%- set part = "coalesce(trim(cast(" ~ col ~ " as " ~ dbt.type_string() ~ ")), '" ~ var('hash_null_placeholder') ~ "')" -%}
        {%- if upper -%}{%- set part = "upper(" ~ part ~ ")" -%}{%- endif -%}
        {%- do parts.append(part) -%}
    {%- endfor -%}
    {{ adapter.dispatch('bw_sha256', 'bilanzwerk')(bw_concat_ws(var('hash_delimiter'), parts)) }}
{%- endmacro %}

{% macro bw_concat_ws(delimiter, parts) -%}
    {%- if parts | length == 1 -%}
        {{ parts[0] }}
    {%- else -%}
        concat_ws('{{ delimiter }}', {{ parts | join(', ') }})
    {%- endif -%}
{%- endmacro %}

{% macro default__bw_sha256(expr) -%}
    sha256({{ expr }})
{%- endmacro %}

{% macro duckdb__bw_sha256(expr) -%}
    sha256({{ expr }})
{%- endmacro %}

{% macro fabric__bw_sha256(expr) -%}
    lower(convert(char(64), hashbytes('SHA2_256', cast({{ expr }} as varchar(8000))), 2))
{%- endmacro %}

{% macro bw_hash_type() -%}
    {{ adapter.dispatch('bw_hash_type', 'bilanzwerk')() }}
{%- endmacro %}
{% macro default__bw_hash_type() -%}varchar{%- endmacro %}
{% macro fabric__bw_hash_type() -%}char(64){%- endmacro %}
