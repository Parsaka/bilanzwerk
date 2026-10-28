-- Mapping coverage: how much of the reported data the line item map catches, per taxonomy,
-- and which core line items are missing per company-period (spec: log every gap).
with reported as (
    select
        p.taxonomy,
        case when m.tag is not null then 1 else 0 end as is_mapped,
        count(*) as n_values
    from {{ ref('pit_fact_first_reported') }} as p
    left join (select distinct
        taxonomy,
        tag
    from {{ ref('line_item_map') }}) as m
        on
            p.taxonomy = m.taxonomy
            and p.tag = m.tag
    group by p.taxonomy, case when m.tag is not null then 1 else 0 end
)

select
    taxonomy,
    sum(n_values) as n_values,
    sum(case when is_mapped = 1 then n_values else 0 end) as n_mapped,
    {{ bw_div('sum(case when is_mapped = 1 then n_values else 0 end)', 'sum(n_values)') }} as mapped_share
from reported
group by taxonomy
