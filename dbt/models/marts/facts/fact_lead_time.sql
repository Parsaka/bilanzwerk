-- H1: one row per company with a bankruptcy, with the lead time of the CCC and Z'' flags in
-- months (null = the flag never turned red and stayed red) and whether each flag could be
-- computed at the last observation before the event.
select
    coalesce(c.company_key, cur.company_key) as company_key,
    l.company_id,
    l.event_date,
    l.n_observations,
    l.lead_months_ccc,
    l.lead_months_z,
    l.ever_red_ccc,
    l.ever_red_z,
    l.ccc_available_last,
    l.z_available_last,
    l.run_id
from {{ ref('stg_analysis__lead_times') }} as l
left join {{ ref('dim_company') }} as c
    on
        l.company_id = c.company_id
        and l.event_date >= c.valid_from
        and l.event_date < c.valid_to
-- an event before the first known company version falls back to the current one
left join {{ ref('dim_company') }} as cur
    on
        l.company_id = cur.company_id
        and cur.is_current = 1
