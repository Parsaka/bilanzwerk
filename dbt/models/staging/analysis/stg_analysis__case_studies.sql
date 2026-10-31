-- The three case-study companies (rule: analysis/pipeline.py CASE_RULE). Empty until the first run.
{{ bw_analysis_staging('case_studies', [
    ['case_rank', dbt.type_int()],
    ['company_id', bw_string(64)],
    ['cik', dbt.type_bigint()],
    ['company_name', bw_string(200)],
    ['sector_de', bw_string(60)],
    ['event_date', 'date'],
    ['revenue_ttm_eur', bw_float()],
    ['lead_months_ccc', bw_float()],
    ['lead_months_z', bw_float()],
    ['run_id', bw_string(64)],
    ['data_version', bw_string(32)],
]) }}
