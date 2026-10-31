-- Pooled out-of-time backtest per model (rolling yearly splits), with the champion marked.
select
    model_name,
    case when model_name = '{{ var("risk_champion_model") }}' then 1 else 0 end as is_champion,
    n as n_observations,
    n_pos as n_events,
    pr_auc,
    recall_top5,
    brier,
    run_id,
    data_version
from {{ ref('stg_analysis__model_backtest') }}
