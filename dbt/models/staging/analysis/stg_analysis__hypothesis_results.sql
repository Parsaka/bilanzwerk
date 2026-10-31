-- H1-H4 as the model run decided them (analysis/answer.py). Empty until the first run.
{{ bw_analysis_staging('hypothesis_results', [
    ['hypothesis_code', bw_string(2)],
    ['hypothesis', bw_string(40)],
    ['status', bw_string(20)],
    ['is_held', dbt.type_int()],
    ['estimate', bw_float()],
    ['ci_low', bw_float()],
    ['ci_high', bw_float()],
    ['unit', bw_string(20)],
    ['text_de', bw_string(400)],
    ['text_en', bw_string(400)],
    ['run_id', bw_string(64)],
    ['data_version', bw_string(32)],
]) }}
