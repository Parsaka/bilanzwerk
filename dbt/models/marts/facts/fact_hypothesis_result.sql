-- The answer (H1-H4) as the last model run decided it, for the report's answer cards and the
-- titles that state a finding. Nothing on a report page is typed by hand.
select
    hypothesis_code,
    hypothesis,
    status,
    is_held,
    estimate,
    ci_low,
    ci_high,
    unit,
    text_de,
    text_en,
    run_id,
    data_version
from {{ ref('stg_analysis__hypothesis_results') }}
