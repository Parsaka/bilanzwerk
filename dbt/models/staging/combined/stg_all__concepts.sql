-- Distinct concepts from every source that reports or defines them (input for hub_concept).
select distinct
    hk_concept,
    taxonomy,
    tag,
    load_datetime,
    record_source
from {{ ref('stg_all__facts') }}

union all

select distinct
    hk_concept,
    taxonomy,
    tag,
    load_datetime,
    record_source
from {{ ref('stg_sec_fsds__tag') }}
