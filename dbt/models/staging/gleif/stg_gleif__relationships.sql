-- Parent relationships (direct and ultimate accounting consolidation parent).
with source as (
    select * from {{ source('gleif', 'relationships') }}
),

latest as (
    select
        source.*,
        row_number() over (
            partition by source.child_lei, source.parent_lei, source.relationship_type
            order by source.publish_date desc, case when source.variant = 'delta' then 0 else 1 end
        ) as rn
    from source
)

select
    {{ bw_hash_key(["child_lei", "parent_lei", "relationship_type"]) }} as hk_company_parent,
    {{ bw_hash_key(["'LEI'", "child_lei"]) }} as hk_company_child,
    {{ bw_hash_key(["'LEI'", "parent_lei"]) }} as hk_company_parent_entity,
    cast(child_lei as {{ bw_string(20) }}) as child_lei,
    cast(parent_lei as {{ bw_string(20) }}) as parent_lei,
    cast(relationship_type as {{ bw_string(60) }}) as relationship_type,
    cast(relationship_status as {{ bw_string(20) }}) as relationship_status,
    cast(registration_status as {{ bw_string(30) }}) as registration_status,
    {{ bw_run_ts() }} as load_datetime,
    cast('gleif.rr' as {{ bw_string(50) }}) as record_source
from latest
where rn = 1
