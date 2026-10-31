-- Presentation: which statement and line a concept appears on, and the negating flag.
with source as (
    select * from {{ source('sec_fsds', 'pre') }}
    where 1 = 1 {{ bw_quarter_filter() }}
),

typed as (
    select
        cast(adsh as {{ bw_string(20) }}) as adsh,
        cast(report as {{ dbt.type_int() }}) as report,
        cast(line as {{ dbt.type_int() }}) as line,
        cast(stmt as {{ bw_string(2) }}) as statement_code,
        cast(inpth as {{ dbt.type_int() }}) as is_parenthetical,
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
        cast(plabel as {{ bw_string(512) }}) as presentation_label,
        cast(coalesce(negating, 0) as {{ dbt.type_int() }}) as is_negating
    from source
)

select
    {{ bw_hash_key(["adsh", "report", "line"]) }} as hk_presentation,
    {{ bw_hash_key(["adsh"]) }} as hk_filing,
    {{ bw_hash_key(["taxonomy", "tag"]) }} as hk_concept,
    typed.*,
    {{ bw_hash_diff(["statement_code", "is_parenthetical", "presentation_label", "is_negating"]) }} as hd_presentation,
    {{ bw_run_ts() }} as load_datetime,
    cast('sec_fsds.pre' as {{ bw_string(50) }}) as record_source
from typed
