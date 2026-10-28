-- One row per reported concept: taxonomy + tag (us-gaap:Revenues, ifrs-full:Revenue).
{{ config(unique_key='hk_concept') }}
{{ bw_hub(['stg_all__concepts'], 'hk_concept', ['taxonomy', 'tag']) }}
