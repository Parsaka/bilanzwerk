-- Event attributes per filing from the submissions file: 8-K items, Form 15/25, late notices.
{{ bw_sat('stg_sec_submissions__filings', 'hk_filing', 'hd_event',
          ['form', 'filing_date', 'accepted_at', 'items', 'is_bankruptcy_8k', 'is_form_15',
           'is_form_25', 'is_late_filing_notice']) }}
