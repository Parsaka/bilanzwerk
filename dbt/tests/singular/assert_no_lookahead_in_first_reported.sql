-- Leakage guard in the warehouse: a first-reported value can never be available before its
-- period ended. (A value may well be public before the period's own statement, e.g. in an
-- earlier registration statement or in a delinquent filer's later annual report; that is not
-- lookahead. The model drops features published after its as-of date, analysis/data.py.)
select k.company_id, k.period_key, k.kpi_key, k.available_at, k.period_end_date
from {{ ref('fact_kpi') }} as k
where
    k.version = '{{ var("version_first_reported") }}'
    and cast(k.available_at as date) < k.period_end_date
