-- 11 sectors (plus "unassigned") with their SIC ranges and NACE sections.
with ranges as (
    select
        sector_code,
        {{ dbt.listagg(dbt.concat(["cast(sic_from as " ~ bw_string(10) ~ ")", "'-'", "cast(sic_to as " ~ bw_string(10) ~ ")"]), "', '") }} as sic_ranges
    from {{ ref('sector_map') }}
    group by sector_code
),

nace as (
    select
        sector_code, {{ dbt.listagg('nace_section', "', '") }} as nace_sections
    from (select distinct
        sector_code,
        nace_section
    from {{ ref('sector_map') }}) as d
    group by sector_code
)

select
    s.sector_code as sector_key,
    s.sector_code,
    s.sector_de,
    s.sector_en,
    s.sort_order,
    s.is_financial,
    r.sic_ranges,
    n.nace_sections
from {{ ref('sectors') }} as s
left join ranges as r
    on s.sector_code = r.sector_code
left join nace as n
    on s.sector_code = n.sector_code
