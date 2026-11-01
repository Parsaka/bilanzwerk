-- Line item mapping: concepts -> about 60 target line items. When several tags feed one
-- line item, the lowest priority number that the company reported wins. Both point-in-time
-- versions are mapped; "version" becomes part of the fact grain.
-- Point-in-time: in the first-reported version the tag known first wins, and priority only
-- decides between tags of the same filing. Otherwise a tag a company adopted later (for
-- example the ASC 606 revenue tag, repeated for two prior years in the next 10-K) would replace
-- the value that was public at the time and date the period two years too late.
with versions as (
    select
        '{{ var("version_first_reported") }}' as version,
        p.*
    from {{ ref('pit_fact_first_reported') }} as p
    union all
    select
        '{{ var("version_latest") }}' as version,
        p.*
    from {{ ref('pit_fact_latest') }} as p
),

mapped as (
    select
        v.version,
        v.hk_company,
        v.company_bk_type,
        v.company_bk,
        m.line_item_code,
        li.period_type,
        li.is_monetary,
        v.taxonomy,
        v.tag,
        m.priority,
        v.period_end,
        v.qtrs,
        v.unit,
        v.value * m.sign as value,
        v.source_filing,
        v.available_at
    from versions as v
    inner join {{ ref('line_item_map') }} as m
        on
            v.taxonomy = m.taxonomy
            and v.tag = m.tag
    inner join {{ ref('line_items') }} as li
        on m.line_item_code = li.line_item_code
    where
        (li.period_type = 'instant' and v.qtrs = 0)
        or (li.period_type = 'duration' and v.qtrs between 1 and 4)
),

valid_units as (
    select mapped.*
    from mapped
    where
        (mapped.is_monetary = 1 and mapped.unit in (select c.currency_code from {{ ref('currencies') }} as c))
        or (mapped.is_monetary = 0 and mapped.unit = 'shares')
)

select
    version,
    hk_company,
    company_bk_type,
    company_bk,
    line_item_code,
    period_type,
    taxonomy,
    tag,
    priority,
    period_end,
    qtrs,
    unit,
    value,
    source_filing,
    available_at
from (
    select
        valid_units.*,
        row_number() over (
            partition by valid_units.version, valid_units.hk_company, valid_units.line_item_code, valid_units.period_end, valid_units.qtrs
            order by
                case when valid_units.version = '{{ var("version_first_reported") }}' then valid_units.available_at end asc,
                valid_units.priority, case when valid_units.unit = 'USD' then 0 when valid_units.unit = 'EUR' then 1 else 2 end, valid_units.unit
        ) as rn
    from valid_units
) as ranked
where rn = 1
