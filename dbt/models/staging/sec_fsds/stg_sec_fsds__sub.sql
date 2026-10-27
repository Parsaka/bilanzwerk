-- One row per SEC filing (10-K, 10-Q, 20-F, 40-F and amendments), with hash keys.
with source as (
    select * from {{ source('sec_fsds', 'sub') }}
    where 1 = 1 {{ bw_quarter_filter() }}
),

renamed as (
    select
        cast(adsh as {{ bw_string(20) }}) as adsh,
        cast(cik as {{ dbt.type_bigint() }}) as cik,
        cast(name as {{ bw_string(200) }}) as company_name,
        cast(sic as {{ dbt.type_int() }}) as sic,
        cast(countryba as {{ bw_string(2) }}) as country_ba,
        cast(stprba as {{ bw_string(2) }}) as state_ba,
        cast(cityba as {{ bw_string(100) }}) as city_ba,
        cast(zipba as {{ bw_string(20) }}) as zip_ba,
        cast(countryinc as {{ bw_string(3) }}) as country_inc,
        cast(fye as {{ bw_string(4) }}) as fiscal_year_end_mmdd,
        cast(form as {{ bw_string(20) }}) as form,
        cast(period as date) as period_end,
        cast(fy as {{ dbt.type_int() }}) as fiscal_year,
        cast(fp as {{ bw_string(4) }}) as fiscal_period,
        cast(filed as date) as filed_date,
        cast(accepted as {{ bw_timestamp() }}) as accepted_at,
        cast(coalesce(prevrpt, 0) as {{ dbt.type_int() }}) as is_amended_later,
        cast(instance as {{ bw_string(200) }}) as instance_file,
        cast(quarter as {{ bw_string(6) }}) as source_quarter
    from source
)

select
    {{ bw_hash_key(["adsh"]) }} as hk_filing,
    {{ bw_hash_key(["'CIK'", "cik"]) }} as hk_company,
    {{ bw_hash_key(["adsh", "'CIK'", "cik"]) }} as hk_filing_company,
    'CIK' as company_bk_type,
    cast(cik as {{ bw_string(20) }}) as company_bk,
    adsh as filing_bk,
    renamed.*,
    {{ bw_hash_diff(["form", "period_end", "fiscal_year", "fiscal_period", "filed_date", "accepted_at", "is_amended_later"]) }} as hd_filing,
    {{ bw_hash_diff(["company_name", "sic", "country_ba", "state_ba", "city_ba", "zip_ba", "fiscal_year_end_mmdd"]) }} as hd_company_sec,
    accepted_at as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_fsds.sub' as {{ bw_string(50) }}) as record_source
from renamed
