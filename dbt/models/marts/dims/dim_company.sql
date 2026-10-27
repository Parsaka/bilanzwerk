-- Golden record per real company with SCD Type 2 history on name and sector.
-- Survivorship (spec): legal name from GLEIF, SIC from SEC, address from GLEIF headquarters,
-- status "inactive" when GLEIF says lapsed/inactive and SEC filings stopped (18 months).
with golden as (
    select * from {{ ref('bv_company_golden') }}
),

sec_history as (
    select
        g.golden_company_id,
        s.effective_from,
        s.company_name,
        s.sic,
        s.country_ba
    from {{ ref('sat_company_sec') }} as s
    inner join golden as g
        on s.hk_company = g.hk_company
),

former_names as (
    -- names from the submissions file that predate the first statement in the warehouse
    select
        g.golden_company_id,
        cast(fn.valid_from as {{ bw_timestamp() }}) as effective_from,
        fn.company_name,
        first_sic.sic,
        first_sic.country_ba
    from {{ ref('stg_sec_submissions__former_names') }} as fn
    inner join golden as g
        on fn.hk_company = g.hk_company
    inner join (
        select golden_company_id, sic, country_ba,
            row_number() over (partition by golden_company_id order by effective_from) as rn
        from sec_history
    ) as first_sic
        on g.golden_company_id = first_sic.golden_company_id
        and first_sic.rn = 1
    where fn.valid_from is not null
        and fn.valid_from < (select min(cast(h.effective_from as date)) from sec_history as h
                             where h.golden_company_id = g.golden_company_id)
),

esef_history as (
    -- LEI-only issuers have no SEC history: one version from the GLEIF name
    select
        g.golden_company_id,
        cast('1900-01-01' as {{ bw_timestamp() }}) as effective_from,
        gl.legal_name as company_name,
        cast(null as {{ dbt.type_int() }}) as sic,
        gl.hq_country as country_ba
    from golden as g
    inner join {{ bw_sat_current('sat_company_gleif', 'hk_company') }} as gl
        on g.hk_company = gl.hk_company
    where g.company_bk_type = 'LEI'
        and not exists (
            select 1 from golden as g2
            where g2.golden_company_id = g.golden_company_id and g2.company_bk_type = 'CIK'
        )
),

history as (
    select * from sec_history
    union all
    select * from former_names
    union all
    select * from esef_history
),

with_sector as (
    select
        h.*,
        coalesce(sm.sector_code, 'S99') as sector_code
    from history as h
    left join {{ ref('sector_map') }} as sm
        on h.sic between sm.sic_from and sm.sic_to
),

changes as (
    select
        w.*,
        lag({{ bw_hash_diff(['company_name', 'sector_code']) }}) over (
            partition by golden_company_id order by effective_from
        ) as previous_hash,
        {{ bw_hash_diff(['company_name', 'sector_code']) }} as current_hash
    from with_sector as w
),

versions as (
    select
        golden_company_id,
        effective_from,
        company_name,
        sic,
        sector_code,
        row_number() over (partition by golden_company_id order by effective_from) as version_number
    from changes
    where previous_hash is null or previous_hash <> current_hash
),

scd as (
    select
        v.*,
        case when version_number = 1 then cast('1900-01-01' as date) else cast(effective_from as date) end as valid_from,
        coalesce(
            cast(lead(effective_from) over (partition by golden_company_id order by effective_from) as date),
            cast('9999-12-31' as date)
        ) as valid_to
    from versions as v
),

ids as (
    -- one row per golden id with its CIK and LEI
    select
        golden_company_id,
        max(cik) as cik,
        max(lei) as lei,
        max(case when company_bk_type = 'CIK' then match_source end) as match_source,
        max(case when company_bk_type = 'CIK' then match_probability end) as match_probability,
        count(distinct case when company_bk_type = 'CIK' then company_bk end) as n_ciks
    from golden
    group by golden_company_id
),

gleif as (
    select g.golden_company_id, gl.*
    from golden as g
    inner join {{ bw_sat_current('sat_company_gleif', 'hk_company') }} as gl
        on g.hk_company = gl.hk_company
    where g.company_bk_type = 'LEI'
),

last_filing as (
    select g.golden_company_id, max(f.accepted_at) as last_accepted_at
    from golden as g
    inner join {{ ref('link_filing_registrant') }} as r
        on g.hk_company = r.hk_company
    inner join {{ bw_sat_current('sat_filing', 'hk_filing') }} as f
        on r.hk_filing = f.hk_filing
    group by g.golden_company_id
)

select
    {{ bw_hash_key(['scd.golden_company_id', 'scd.valid_from']) }} as company_key,
    scd.golden_company_id as company_id,
    ids.cik,
    ids.lei,
    scd.company_name,
    coalesce(gleif.legal_name, scd.company_name) as legal_name,
    scd.sic,
    scd.sector_code as sector_key,
    coalesce(gleif.hq_country, gleif.legal_country, case when ids.cik is not null then 'US' end) as country_code,
    gleif.hq_city,
    gleif.hq_postal_code,
    gleif.legal_form_code,
    gleif.entity_status as gleif_entity_status,
    gleif.registration_status as gleif_registration_status,
    case
        when coalesce(gleif.registration_status, 'LAPSED') in ('LAPSED', 'RETIRED', 'ANNULLED')
            and (lf.last_accepted_at is null or lf.last_accepted_at < {{ dbt.dateadd('month', -18, bw_run_ts()) }})
            then 'inactive'
        else 'active'
    end as company_status,
    ids.match_source,
    ids.match_probability,
    case when ids.lei is not null then 1 else 0 end as is_lei_matched,
    ids.n_ciks,
    case when scd.sector_code = 'S11' then 1 else 0 end as is_financial,
    scd.version_number,
    scd.valid_from,
    scd.valid_to,
    case when scd.valid_to = cast('9999-12-31' as date) then 1 else 0 end as is_current,
    lf.last_accepted_at
from scd
inner join ids
    on scd.golden_company_id = ids.golden_company_id
left join gleif
    on scd.golden_company_id = gleif.golden_company_id
left join last_filing as lf
    on scd.golden_company_id = lf.golden_company_id
