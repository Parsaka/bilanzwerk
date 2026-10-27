-- Current company profile from the submissions file (latest load date per CIK).
with source as (
    select * from {{ source('sec_submissions', 'companies') }}
),

latest as (
    select
        source.*,
        row_number() over (partition by cik order by load_date desc) as rn
    from source
)

select
    {{ bw_hash_key(["'CIK'", "cik"]) }} as hk_company,
    'CIK' as company_bk_type,
    cast(cik as {{ bw_string(20) }}) as company_bk,
    cast(cik as {{ dbt.type_bigint() }}) as cik,
    cast(name as {{ bw_string(200) }}) as company_name,
    cast(entity_type as {{ bw_string(50) }}) as entity_type,
    cast(sic as {{ dbt.type_int() }}) as sic,
    cast(sic_description as {{ bw_string(200) }}) as sic_description,
    {%- if target.type == 'duckdb' %}
    cast(array_to_string(tickers, ',') as {{ bw_string(200) }}) as tickers,
    cast(array_to_string(exchanges, ',') as {{ bw_string(200) }}) as exchanges,
    {%- else %}
    cast(tickers as {{ bw_string(200) }}) as tickers,
    cast(exchanges as {{ bw_string(200) }}) as exchanges,
    {%- endif %}
    cast(fiscal_year_end as {{ bw_string(4) }}) as fiscal_year_end_mmdd,
    cast(state_of_incorporation as {{ bw_string(10) }}) as state_of_incorporation,
    cast(business_city as {{ bw_string(100) }}) as business_city,
    cast(business_state as {{ bw_string(10) }}) as business_state,
    cast(business_zip as {{ bw_string(20) }}) as business_zip,
    cast(lei as {{ bw_string(20) }}) as lei,
    cast(load_date as {{ bw_string(10) }}) as load_date,
    cast(load_date as {{ bw_timestamp() }}) as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_submissions.companies' as {{ bw_string(50) }}) as record_source
from latest
where rn = 1
