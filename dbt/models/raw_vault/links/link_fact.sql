-- One row per reported amount: filing + concept + period end + duration (qtrs) + unit.
{{ bw_link(['stg_all__facts'], 'hk_fact', ['hk_filing', 'hk_concept'], extra_keys=['period_end', 'qtrs', 'unit']) }}
