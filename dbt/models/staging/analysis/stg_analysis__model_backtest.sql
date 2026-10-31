-- Pooled out-of-time backtest per model (analysis/backtest.py). Empty until the first run.
{{ bw_analysis_staging('model_backtest', [
    ['model_name', bw_string(40)],
    ['n', dbt.type_bigint()],
    ['n_pos', dbt.type_bigint()],
    ['pr_auc', bw_float()],
    ['recall_top5', bw_float()],
    ['brier', bw_float()],
    ['run_id', bw_string(64)],
    ['data_version', bw_string(32)],
]) }}
