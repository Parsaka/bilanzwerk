-- All reported amounts (SEC FSDS and ESEF) in one shape, the input for link_fact and sat_fact_value.
select
    hk_fact,
    hk_filing,
    hk_concept,
    adsh as filing_bk,
    taxonomy,
    tag,
    period_end,
    qtrs,
    unit,
    value,
    footnote,
    hd_fact_value,
    load_datetime as effective_from,
    load_datetime,
    record_source
from {{ ref('stg_sec_fsds__num') }}

union all

select
    hk_fact,
    hk_filing,
    hk_concept,
    filing_bk,
    taxonomy,
    tag,
    period_end,
    qtrs,
    unit,
    value,
    footnote,
    hd_fact_value,
    load_datetime as effective_from,
    load_datetime,
    record_source
from {{ ref('stg_esef__facts') }}
