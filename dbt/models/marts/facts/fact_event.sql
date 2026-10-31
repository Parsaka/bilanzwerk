-- Events per company: bankruptcy (8-K Item 1.03), deregistration (Form 15), delisting
-- (Form 25) and late-filing notices (NT 10-K/Q). Event date = filing date.
with events as (
    select
        e.hk_filing,
        hf.filing_bk as filing,
        e.form,
        e.items,
        e.filing_date,
        e.accepted_at,
        case
            when e.is_bankruptcy_8k = 1 then 'BANKRUPTCY_8K_103'
            when e.is_form_15 = 1 then 'DEREGISTRATION_FORM_15'
            when e.is_form_25 = 1 then 'DELISTING_FORM_25'
            when e.is_late_filing_notice = 1 then 'LATE_FILING_NOTICE'
        end as event_type
    from {{ bw_sat_current('sat_event', 'hk_filing') }} as e
    inner join {{ ref('hub_filing') }} as hf
        on e.hk_filing = hf.hk_filing
    where e.is_bankruptcy_8k = 1 or e.is_form_15 = 1 or e.is_form_25 = 1 or e.is_late_filing_notice = 1
),

with_company as (
    select
        g.golden_company_id as company_id,
        ev.*,
        row_number() over (
            partition by g.golden_company_id, ev.filing_date, ev.event_type order by ev.filing
        ) as rn
    from events as ev
    inner join {{ ref('link_filing_company') }} as l
        on ev.hk_filing = l.hk_filing
    inner join {{ ref('bv_company_golden') }} as g
        on l.hk_company = g.hk_company
)

select
    {{ bw_hash_key(['w.company_id', 'w.filing_date', 'w.event_type']) }} as event_key,
    w.company_id,
    c.company_key,
    w.filing_date as event_date,
    w.event_type,
    case when w.event_type in ('BANKRUPTCY_8K_103') then 1 else 0 end as is_main_label,
    case when w.event_type in ('BANKRUPTCY_8K_103', 'DEREGISTRATION_FORM_15', 'DELISTING_FORM_25') then 1 else 0 end as is_distress_label,
    w.filing,
    w.form,
    case when w.event_type = 'BANKRUPTCY_8K_103' then '1.03' end as item_code,
    w.items as all_items,
    w.accepted_at
from with_company as w
left join {{ ref('dim_company') }} as c
    on
        w.company_id = c.company_id
        and w.filing_date >= c.valid_from
        and w.filing_date < c.valid_to
where w.rn = 1
