-- Open stewardship cases: candidate pairs between the two match thresholds without a steward
-- decision yet. The Power BI data quality page lists them; decisions go to the seed.
select
    m.source_company_bk_type,
    m.source_company_bk,
    m.lei,
    m.match_probability,
    m.match_weight,
    m.model_version,
    sp.company_name as sec_name,
    gl.legal_name as gleif_legal_name,
    gl.hq_city as gleif_city,
    gl.hq_country as gleif_country
from {{ ref('stg_mdm__company_matches') }} as m
left join {{ ref('stewardship_decisions') }} as d
    on m.source_company_bk = d.source_company_bk
    and m.lei = d.lei
left join {{ bw_sat_current('sat_company_sec_profile', 'hk_company') }} as sp
    on sp.hk_company = {{ bw_hash_key(["'CIK'", 'm.source_company_bk']) }}
left join {{ bw_sat_current('sat_company_gleif', 'hk_company') }} as gl
    on gl.lei = m.lei
where m.match_status = 'review'
    and d.decision is null
