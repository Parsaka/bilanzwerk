-- Values whose latest version differs from the first reported one (more than rounding).
-- The restatement rate per company is a KPI and a model feature (as of the restating filing).
select
    f.hk_company,
    f.taxonomy,
    f.tag,
    f.period_end,
    f.qtrs,
    f.unit,
    f.value as first_value,
    l.value as latest_value,
    f.source_filing as first_filing,
    l.source_filing as latest_filing,
    f.available_at as first_available_at,
    l.available_at as restated_at
from {{ ref('pit_fact_first_reported') }} as f
inner join {{ ref('pit_fact_latest') }} as l
    on f.hk_company = l.hk_company
    and f.taxonomy = l.taxonomy
    and f.tag = l.tag
    and f.period_end = l.period_end
    and f.qtrs = l.qtrs
    and f.unit = l.unit
where f.source_filing <> l.source_filing
    and abs(f.value - l.value) > 0.005 * greatest(abs(f.value), abs(l.value), 1)
