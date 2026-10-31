-- Lead time of the CCC and Z'' flags per company with a bankruptcy (analysis/leadtime.py).
-- Empty until the first run.
{{ bw_analysis_staging('lead_times', [
    ['company_id', bw_string(64)],
    ['event_date', 'date'],
    ['n_observations', dbt.type_int()],
    ['lead_months_ccc', bw_float()],
    ['lead_months_z', bw_float()],
    ['ever_red_ccc', dbt.type_int()],
    ['ever_red_z', dbt.type_int()],
    ['ccc_available_last', dbt.type_int()],
    ['z_available_last', dbt.type_int()],
    ['run_id', bw_string(64)],
    ['data_version', bw_string(32)],
]) }}
