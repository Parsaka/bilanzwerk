-- One row per company business key: ('CIK', cik) for SEC filers, ('LEI', lei) for GLEIF/ESEF.
{{ config(unique_key='hk_company') }}
{{ bw_hub(['stg_all__companies'], 'hk_company', ['company_bk_type', 'company_bk']) }}
