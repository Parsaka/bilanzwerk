-- Scored candidate pairs from the Splink job (mdm/). Before the first MDM run the model is
-- empty with the right columns, so the whole project builds in one pass.
{% if env_var('BW_HAS_MDM', 'false') == 'true' %}
select
    cast(source_company_bk_type as {{ bw_string(3) }}) as source_company_bk_type,
    cast(source_company_bk as {{ bw_string(20) }}) as source_company_bk,
    cast(lei as {{ bw_string(20) }}) as lei,
    cast(match_probability as {{ bw_float() }}) as match_probability,
    cast(match_weight as {{ bw_float() }}) as match_weight,
    cast(match_status as {{ bw_string(20) }}) as match_status,
    cast(model_version as {{ bw_string(40) }}) as model_version
from {{ source('mdm', 'company_matches') }}
{% else %}
select
    cast(null as {{ bw_string(3) }}) as source_company_bk_type,
    cast(null as {{ bw_string(20) }}) as source_company_bk,
    cast(null as {{ bw_string(20) }}) as lei,
    cast(null as {{ bw_float() }}) as match_probability,
    cast(null as {{ bw_float() }}) as match_weight,
    cast(null as {{ bw_string(20) }}) as match_status,
    cast(null as {{ bw_string(40) }}) as model_version
where 1 = 0
{% endif %}
