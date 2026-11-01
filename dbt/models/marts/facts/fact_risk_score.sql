-- Probability of bankruptcy within 12 months per company, as-of date and model, written back
-- by the early-warning model (analysis/), with the three strongest drivers.
select
    {{ bw_hash_key(['g.golden_company_id', 'r.as_of_date', 'r.model_name']) }} as risk_score_key,
    c.company_key,
    g.golden_company_id as company_id,
    r.as_of_date,
    r.model_name,
    case when r.model_name = '{{ var("risk_champion_model") }}' then 1 else 0 end as is_champion,
    r.probability_12m,
    r.risk_band,
    -- 1 on each company's latest as-of date per model: the report filters on it instead of
    -- finding the latest date per company in DAX (risk table on page 7)
    case
        when r.as_of_date = max(r.as_of_date) over (partition by g.golden_company_id, r.model_name) then 1
        else 0
    end as is_latest_for_company,
    r.top_3_drivers,
    r.run_id
from {{ ref('stg_analysis__risk_scores') }} as r
inner join {{ ref('bv_company_golden') }} as g
    on
        g.company_bk_type = 'CIK'
        and r.cik = g.cik
left join {{ ref('dim_company') }} as c
    on
        g.golden_company_id = c.company_id
        and r.as_of_date >= c.valid_from
        and r.as_of_date < c.valid_to
