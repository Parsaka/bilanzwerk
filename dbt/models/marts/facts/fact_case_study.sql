-- The three case studies of report page 8, chosen by a fixed rule (analysis/pipeline.py), with
-- the company version that was valid at the event.
select
    s.case_rank,
    coalesce(c.company_key, cur.company_key) as company_key,
    s.company_id,
    s.cik,
    s.company_name,
    s.sector_de,
    s.event_date,
    s.revenue_ttm_eur,
    s.lead_months_ccc,
    s.lead_months_z,
    s.run_id
from {{ ref('stg_analysis__case_studies') }} as s
left join {{ ref('dim_company') }} as c
    on
        s.company_id = c.company_id
        and s.event_date >= c.valid_from
        and s.event_date < c.valid_to
-- an event before the first known company version falls back to the current one
left join {{ ref('dim_company') }} as cur
    on
        s.company_id = cur.company_id
        and cur.is_current = 1
