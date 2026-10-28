-- Bridge to master data: every company key (CIK or LEI) -> one golden company id.
-- Match precedence for an SEC filer:
--   1. steward decision "match" (seed stewardship_decisions, survives reruns)
--   2. steward decision "no_match" removes any automatic match
--   3. LEI stated by the filer in the SEC submissions profile
--   4. Splink match above the upper threshold (mdm/)
-- The golden id is the hash key of the LEI when a match exists, otherwise of the CIK.
with sec as (
    select
        hk_company,
        company_bk as cik
    from {{ ref('hub_company') }}
    where company_bk_type = 'CIK'
),

steward as (
    select
        source_company_bk,
        lei,
        decision
    from {{ ref('stewardship_decisions') }}
    where source_company_bk_type = 'CIK'
),

candidates as (
    select
        s.source_company_bk as cik,
        s.lei,
        1 as precedence,
        'steward' as match_source,
        cast(1.0 as {{ bw_float() }}) as match_probability
    from steward as s
    where s.decision = 'match'

    union all

    select
        h.company_bk,
        p.lei,
        3,
        'sec_profile',
        cast(1.0 as {{ bw_float() }})
    from {{ bw_sat_current('sat_company_sec_profile', 'hk_company') }} as p
    inner join {{ ref('hub_company') }} as h
        on p.hk_company = h.hk_company
    where p.lei is not null and p.lei <> ''

    union all

    select
        m.source_company_bk,
        m.lei,
        4,
        'splink',
        m.match_probability
    from {{ ref('stg_mdm__company_matches') }} as m
    where m.source_company_bk_type = 'CIK' and m.match_status = 'match'
),

allowed as (
    select c.*
    from candidates as c
    where not exists (
        select 1 from steward as s
        where s.decision = 'no_match' and s.source_company_bk = c.cik and s.lei = c.lei
    )
),

best as (
    select
        cik,
        lei,
        match_source,
        match_probability
    from (
        select
            allowed.*,
            row_number() over (partition by allowed.cik order by allowed.precedence asc, allowed.match_probability desc, allowed.lei asc) as rn
        from allowed
    ) as ranked
    where rn = 1
),

sec_golden as (
    select
        sec.hk_company,
        'CIK' as company_bk_type,
        sec.cik as company_bk,
        cast(sec.cik as {{ dbt.type_bigint() }}) as cik,
        best.lei,
        case
            when best.lei is not null then {{ bw_hash_key(["'LEI'", "best.lei"]) }}
            else sec.hk_company
        end as golden_company_id,
        coalesce(best.match_source, 'unmatched') as match_source,
        best.match_probability
    from sec
    left join best
        on sec.cik = best.cik
),

lei_companies as (
    -- ESEF issuers (they file under their LEI) and every LEI matched to an SEC filer
    select distinct
        h.hk_company,
        h.company_bk as lei
    from {{ ref('hub_company') }} as h
    inner join {{ ref('link_filing_registrant') }} as r
        on h.hk_company = r.hk_company
    where h.company_bk_type = 'LEI'

    union

    select
        {{ bw_hash_key(["'LEI'", "lei"]) }} as hk_company,
        lei
    from best
)

select * from sec_golden

union all

select
    l.hk_company,
    'LEI' as company_bk_type,
    l.lei as company_bk,
    cast(null as {{ dbt.type_bigint() }}) as cik,
    l.lei,
    l.hk_company as golden_company_id,
    'lei_native' as match_source,
    cast(1.0 as {{ bw_float() }}) as match_probability
from lei_companies as l
