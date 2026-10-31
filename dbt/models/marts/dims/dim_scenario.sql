select
    scenario_code as scenario_key,
    scenario_code,
    scenario_de,
    scenario_en,
    description
from {{ ref('scenarios') }}
