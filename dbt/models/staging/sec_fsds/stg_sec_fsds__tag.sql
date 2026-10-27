-- Concept definitions. Every quarter file repeats the definitions; the satellite keeps a new
-- row only when the definition text changes. Custom (company) tags are not kept here.
with source as (
    select * from {{ source('sec_fsds', 'tag') }}
    where coalesce(custom, 0) = 0 {{ bw_quarter_filter() }}
),

typed as (
    select
        cast(tag as {{ bw_string(256) }}) as tag,
        cast(version as {{ bw_string(32) }}) as version,
        case
            when version like 'us-gaap/%' then 'us-gaap'
            when version like 'ifrs%' then 'ifrs-full'
            when version like 'dei/%' then 'dei'
            when version like 'srt/%' then 'srt'
            else 'other'
        end as taxonomy,
        cast(abstract as {{ dbt.type_int() }}) as is_abstract,
        cast(datatype as {{ bw_string(32) }}) as datatype,
        cast(iord as {{ bw_string(1) }}) as instant_or_duration,
        cast(crdr as {{ bw_string(1) }}) as debit_or_credit,
        cast(tlabel as {{ bw_string(512) }}) as label,
        cast(doc as {{ bw_string(4000) }}) as documentation,
        cast(quarter as {{ bw_string(6) }}) as source_quarter,
        {{ dbt.dateadd(
            'month',
            "(cast(right(quarter, 1) as " ~ dbt.type_int() ~ ") - 1) * 3",
            "cast(" ~ dbt.concat(["left(quarter, 4)", "'-01-01'"]) ~ " as date)"
        ) }} as quarter_start
    from source
),

-- one definition per concept and quarter: the newest taxonomy version wins
ranked as (
    select
        typed.*,
        row_number() over (partition by typed.taxonomy, typed.tag, typed.source_quarter order by typed.version desc) as rn
    from typed
)

select
    {{ bw_hash_key(["taxonomy", "tag"]) }} as hk_concept,
    taxonomy,
    tag,
    version,
    is_abstract,
    datatype,
    instant_or_duration,
    debit_or_credit,
    label,
    documentation,
    source_quarter,
    {{ bw_hash_diff(["datatype", "instant_or_duration", "debit_or_credit", "label", "documentation"]) }} as hd_concept_def,
    cast(quarter_start as {{ bw_timestamp() }}) as effective_from,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_fsds.tag' as {{ bw_string(50) }}) as record_source
from ranked
where rn = 1
