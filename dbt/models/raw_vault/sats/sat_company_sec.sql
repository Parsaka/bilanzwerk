-- SEC company attributes as stated in each filing; history by acceptance time.
{{ bw_sat('stg_sec_fsds__sub', 'hk_company', 'hd_company_sec',
          ['company_name', 'sic', 'country_ba', 'state_ba', 'city_ba', 'zip_ba', 'fiscal_year_end_mmdd']) }}
