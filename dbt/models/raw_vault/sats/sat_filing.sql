-- Filing attributes: form, period, fiscal year and period, filed, accepted, amended flag.
{{ bw_sat('stg_all__filings', 'hk_filing', 'hd_filing',
          ['form', 'period_end', 'fiscal_year', 'fiscal_period', 'filed_date', 'accepted_at', 'is_amended_later']) }}
