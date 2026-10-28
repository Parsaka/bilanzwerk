-- Name history per CIK, used for SCD Type 2 names in dim_company.
with source as (
    select distinct
        cik,
        name,
        valid_from,
        valid_to
    from {{ source('sec_submissions', 'former_names') }}
)

select
    {{ bw_hash_key(["'CIK'", "cik"]) }} as hk_company,
    cast(cik as {{ dbt.type_bigint() }}) as cik,
    cast(name as {{ bw_string(200) }}) as company_name,
    cast(left(valid_from, 10) as date) as valid_from,
    cast(left(valid_to, 10) as date) as valid_to
from source
where name is not null
