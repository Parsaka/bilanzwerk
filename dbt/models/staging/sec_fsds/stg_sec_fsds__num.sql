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

-- One row per filing, concept, period and unit, the grain of hk_fact. The file's own key also
-- has the taxonomy version, so two versions that normalise to the same taxonomy (e.g. two
-- "other" taxonomies with the same tag) or a filing repeated in a later quarter file would give
-- two values for one fact in one batch. Keep the later quarter file, then the later version.
deduplicated as (
    select
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
            typed.*,
            row_number() over (
                partition by typed.adsh, typed.taxonomy, typed.tag, typed.period_end, typed.qtrs, typed.unit
                order by typed.source_quarter desc, typed.version desc, typed.value desc
            ) as rn
        from typed
    ) as ranked
    where rn = 1
)

select
    {{ bw_hash_key(["adsh", "taxonomy", "tag", "period_end", "qtrs", "unit"]) }} as hk_fact,
    {{ bw_hash_key(["adsh"]) }} as hk_filing,
    {{ bw_hash_key(["taxonomy", "tag"]) }} as hk_concept,
    deduplicated.*,
    {{ bw_hash_diff(["value", "footnote"]) }} as hd_fact_value,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_fsds.num' as {{ bw_string(50) }}) as record_source
from deduplicated
