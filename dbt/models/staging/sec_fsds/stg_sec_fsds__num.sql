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
),

hashed as (
    select
        {{ bw_hash_key(["adsh", "taxonomy", "tag", "period_end", "qtrs", "unit"]) }} as hk_fact,
        {{ bw_hash_key(["adsh"]) }} as hk_filing,
        {{ bw_hash_key(["taxonomy", "tag"]) }} as hk_concept,
        typed.*
    from typed
),

-- One row per hk_fact. The file's own key also has the taxonomy version and is case-sensitive,
-- while hk_fact ignores case (custom tags that differ only in case) and maps versions to one
-- taxonomy; a filing can also be repeated in a later quarter file. Any of these would give two
-- values for one fact in one batch (seen in the real data). Keep the later quarter file, then
-- the later version.
deduplicated as (
    select
        hk_fact,
        hk_filing,
        hk_concept,
        adsh,
        tag,
        version,
        taxonomy,
        period_end,
        qtrs,
        unit,
        value,
        footnote,
        source_quarter
    from (
        select
            hashed.*,
            row_number() over (
                partition by hashed.hk_fact
                order by hashed.source_quarter desc, hashed.version desc, hashed.tag desc, hashed.value desc
            ) as rn
        from hashed
    ) as ranked
    where rn = 1
)

select
    deduplicated.*,
    {{ bw_hash_diff(["value", "footnote"]) }} as hd_fact_value,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_fsds.num' as {{ bw_string(50) }}) as record_source
from deduplicated
