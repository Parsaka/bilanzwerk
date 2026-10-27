-- GLEIF legal entity attributes (names, addresses, legal form, status) with history.
{{ bw_sat('stg_gleif__entities', 'hk_company', 'hd_company_gleif',
          ['lei', 'legal_name', 'other_name_1', 'other_name_2', 'other_name_3',
           'legal_address_line', 'legal_city', 'legal_region', 'legal_country', 'legal_postal_code',
           'hq_address_line', 'hq_city', 'hq_region', 'hq_country', 'hq_postal_code',
           'legal_jurisdiction', 'entity_category', 'legal_form_code', 'entity_status',
           'registration_status', 'last_update_date']) }}
