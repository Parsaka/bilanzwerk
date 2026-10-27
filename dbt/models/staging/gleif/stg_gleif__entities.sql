-- LEI records: the newest publication wins; a delta on the same day beats the full file.
with source as (
    select * from {{ source('gleif', 'entities') }}
),

latest as (
    select
        source.*,
        row_number() over (
            partition by source.lei
            order by source.publish_date desc, case when source.variant = 'delta' then 0 else 1 end, source.last_update_date desc
        ) as rn
    from source
)

select
    {{ bw_hash_key(["'LEI'", "lei"]) }} as hk_company,
    'LEI' as company_bk_type,
    cast(lei as {{ bw_string(20) }}) as company_bk,
    cast(lei as {{ bw_string(20) }}) as lei,
    cast(legal_name as {{ bw_string(500) }}) as legal_name,
    cast(other_name_1 as {{ bw_string(500) }}) as other_name_1,
    cast(other_name_2 as {{ bw_string(500) }}) as other_name_2,
    cast(other_name_3 as {{ bw_string(500) }}) as other_name_3,
    cast(legal_address_line as {{ bw_string(500) }}) as legal_address_line,
    cast(legal_city as {{ bw_string(200) }}) as legal_city,
    cast(legal_region as {{ bw_string(10) }}) as legal_region,
    cast(legal_country as {{ bw_string(2) }}) as legal_country,
    cast(legal_postal_code as {{ bw_string(20) }}) as legal_postal_code,
    cast(hq_address_line as {{ bw_string(500) }}) as hq_address_line,
    cast(hq_city as {{ bw_string(200) }}) as hq_city,
    cast(hq_region as {{ bw_string(10) }}) as hq_region,
    cast(hq_country as {{ bw_string(2) }}) as hq_country,
    cast(hq_postal_code as {{ bw_string(20) }}) as hq_postal_code,
    cast(legal_jurisdiction as {{ bw_string(10) }}) as legal_jurisdiction,
    cast(entity_category as {{ bw_string(30) }}) as entity_category,
    cast(legal_form_code as {{ bw_string(10) }}) as legal_form_code,
    cast(entity_status as {{ bw_string(20) }}) as entity_status,
    cast(registration_status as {{ bw_string(30) }}) as registration_status,
    cast(left(last_update_date, 10) as date) as last_update_date,
    {{ bw_hash_diff([
        "legal_name", "other_name_1", "other_name_2", "other_name_3",
        "legal_address_line", "legal_city", "legal_country", "legal_postal_code",
        "hq_address_line", "hq_city", "hq_country", "hq_postal_code",
        "legal_form_code", "entity_status", "registration_status"
    ]) }} as hd_company_gleif,
    cast(coalesce(replace(left(last_update_date, 19), 'T', ' '), cast(publish_date as {{ bw_string(10) }})) as {{ bw_timestamp() }}) as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('gleif.lei2' as {{ bw_string(50) }}) as record_source
from latest
where rn = 1
