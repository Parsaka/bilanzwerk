-- Company-total amounts only: rows with empty segments and empty coreg (spec, pitfalls).
-- Text in "taxonomy" is normalised so FSDS ("ifrs/2023") and ESEF ("ifrs-full") agree.
with source as (
    select * from {{ source('sec_fsds', 'num') }}
    where segments is null and coreg is null {{ bw_quarter_filter() }}
),

typed as (
    select
        cast(adsh as {{ bw_string(20) }}) as adsh,
        cast(tag as {{ bw_string(256) }}) as tag,
        cast(version as {{ bw_string(32) }}) as version,
        case
            when version = adsh then 'custom'
            when version like 'us-gaap/%' then 'us-gaap'
            when version like 'ifrs%' then 'ifrs-full'
            when version like 'dei/%' then 'dei'
            when version like 'srt/%' then 'srt'
            else 'other'
        end as taxonomy,
        cast(ddate as date) as period_end,
        cast(qtrs as {{ dbt.type_int() }}) as qtrs,
        cast(uom as {{ bw_string(32) }}) as unit,
        cast(value as decimal(38, 6)) as value,
        cast(footnote as {{ bw_string(4000) }}) as footnote,
        cast(quarter as {{ bw_string(6) }}) as source_quarter
    from source
    where value is not null
)

select
    {{ bw_hash_key(["adsh", "taxonomy", "tag", "period_end", "qtrs", "unit"]) }} as hk_fact,
    {{ bw_hash_key(["adsh"]) }} as hk_filing,
    {{ bw_hash_key(["taxonomy", "tag"]) }} as hk_concept,
    typed.*,
    {{ bw_hash_diff(["value", "footnote"]) }} as hd_fact_value,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_fsds.num' as {{ bw_string(50) }}) as record_source
from typed
