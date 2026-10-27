-- Plan values are frozen on 1 January from data public before that day: the plan of a period
-- can never use information from inside its own year.
select company_id, period_end_date, available_at
from {{ ref('fact_financial_line') }}
where scenario_key = 'PLAN'
    and year(available_at) <> year(period_end_date)
