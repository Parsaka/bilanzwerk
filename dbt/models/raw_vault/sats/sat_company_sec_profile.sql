-- Current SEC profile from the submissions file (tickers, exchanges, entity type).
{%- set payload = ['company_name', 'entity_type', 'sic', 'sic_description', 'tickers', 'exchanges',
                   'fiscal_year_end_mmdd', 'state_of_incorporation', 'business_city',
                   'business_state', 'business_zip', 'lei'] %}
{{ bw_sat('int_sec_profile_hashed', 'hk_company', 'hd_company_sec_profile', payload) }}
