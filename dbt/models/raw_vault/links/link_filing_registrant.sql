-- The registrant whose financial statements a filing contains (sub.cik for SEC, the LEI for
-- ESEF). Kept apart from link_filing_company, which also holds co-registrant associations
-- from the submissions file, so facts are never attributed to the wrong company.
{{ bw_link(['stg_all__filings'], 'hk_filing_company', ['hk_filing', 'hk_company']) }}
