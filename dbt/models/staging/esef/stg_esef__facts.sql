-- ESEF facts in the same shape as SEC num rows: taxonomy + tag, period end, qtrs, unit.
with source as (
    select * from {{ source('esef', 'facts') }}
),

typed as (
    select
        cast(fxo_id as {{ bw_string(100) }}) as filing_bk,
        cast(left(concept, {{ dbt.position("':'", "concept") }} - 1) as {{ bw_string(64) }}) as taxonomy,
        cast(
            {{ dbt.right("concept", dbt.length("concept") ~ " - " ~ dbt.position("':'", "concept")) }}
            as {{ bw_string(256) }}
        ) as tag,
        cast({{ bw_nearest_month_end('cast(period_end as date)') }} as date) as period_end,
        case
            when period_start is null then 0
            else cast(round({{ dbt.datediff("period_start", "period_end", "day") }} / 91.3, 0) as {{ dbt.type_int() }})
        end as qtrs,
        cast(replace(unit, 'iso4217:', '') as {{ bw_string(32) }}) as unit,
        cast(value as decimal(38, 6)) as value,
        cast(null as {{ bw_string(4000) }}) as footnote,
        decimals
    from source
    where concept like '%:%'
),

-- ESEF reports can tag the same amount twice (e.g. in two tables with different precision):
-- keep the most precise one per filing, concept, period and unit
deduplicated as (
    select * from (
        select
            typed.*,
            row_number() over (
                partition by filing_bk, taxonomy, tag, period_end, qtrs, unit
                order by coalesce(decimals, 99) desc, value
            ) as rn
        from typed
    ) as ranked
    where rn = 1
)

select
    {{ bw_hash_key(["filing_bk", "taxonomy", "tag", "period_end", "qtrs", "unit"]) }} as hk_fact,
    {{ bw_hash_key(["filing_bk"]) }} as hk_filing,
    {{ bw_hash_key(["taxonomy", "tag"]) }} as hk_concept,
    filing_bk as adsh,
    filing_bk, taxonomy, tag, period_end, qtrs, unit, value, footnote,
    {{ bw_hash_diff(["value", "footnote"]) }} as hd_fact_value,
    {{ bw_run_ts() }} as load_datetime,
    cast('esef.facts' as {{ bw_string(50) }}) as record_source
from deduplicated
