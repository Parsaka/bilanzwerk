with source as (
    select * from {{ source('esef', 'filings') }}
)

select
    {{ bw_hash_key(["fxo_id"]) }} as hk_filing,
    {{ bw_hash_key(["'LEI'", "lei"]) }} as hk_company,
    {{ bw_hash_key(["fxo_id", "'LEI'", "lei"]) }} as hk_filing_company,
    cast(fxo_id as {{ bw_string(100) }}) as filing_bk,
    'LEI' as company_bk_type,
    cast(lei as {{ bw_string(20) }}) as company_bk,
    cast(lei as {{ bw_string(20) }}) as lei,
    cast(entity_name as {{ bw_string(500) }}) as entity_name,
    cast(country as {{ bw_string(2) }}) as country,
    cast('AFR' as {{ bw_string(20) }}) as form,
    cast({{ bw_nearest_month_end('cast(period_end as date)') }} as date) as period_end,
    cast(year(period_end) as {{ dbt.type_int() }}) as fiscal_year,
    cast('FY' as {{ bw_string(4) }}) as fiscal_period,
    cast(left(date_added, 10) as date) as filed_date,
    cast(replace(left(date_added, 19), 'T', ' ') as {{ bw_timestamp() }}) as accepted_at,
    0 as is_amended_later,
    {{ bw_hash_diff(["'AFR'", "period_end", "date_added"]) }} as hd_filing,
    cast(replace(left(date_added, 19), 'T', ' ') as {{ bw_timestamp() }}) as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('esef.filings' as {{ bw_string(50) }}) as record_source
from source
where lei is not null
