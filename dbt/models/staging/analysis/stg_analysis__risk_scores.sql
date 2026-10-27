-- Risk scores written back by the early-warning model (analysis/). Empty until first run.
{% if env_var('BW_HAS_RISK_SCORES', 'false') == 'true' %}
select
    cast(cik as {{ dbt.type_bigint() }}) as cik,
    cast(as_of_date as date) as as_of_date,
    cast(model_name as {{ bw_string(40) }}) as model_name,
    cast(probability_12m as {{ bw_float() }}) as probability_12m,
    cast(risk_band as {{ bw_string(10) }}) as risk_band,
    cast(top_3_drivers as {{ bw_string(500) }}) as top_3_drivers,
    cast(run_id as {{ bw_string(64) }}) as run_id
from {{ source('analysis', 'risk_scores') }}
{% else %}
select
    cast(null as {{ dbt.type_bigint() }}) as cik,
    cast(null as date) as as_of_date,
    cast(null as {{ bw_string(40) }}) as model_name,
    cast(null as {{ bw_float() }}) as probability_12m,
    cast(null as {{ bw_string(10) }}) as risk_band,
    cast(null as {{ bw_string(500) }}) as top_3_drivers,
    cast(null as {{ bw_string(64) }}) as run_id
where 1 = 0
{% endif %}
