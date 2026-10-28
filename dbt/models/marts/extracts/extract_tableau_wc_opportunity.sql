-- One flat extract for Tableau Public: working-capital opportunity with company and sector.
select
    c.company_name,
    c.cik,
    c.lei,
    s.sector_de,
    s.sector_en,
    w.fiscal_year,
    w.dso,
    w.dio,
    w.dpo,
    w.ccc,
    w.sector_median_dso,
    w.sector_median_dio,
    w.sector_median_dpo,
    w.revenue_eur,
    w.cash_opportunity_eur,
    w.cash_opportunity_stretch_eur
from {{ ref('fact_wc_opportunity') }} as w
inner join {{ ref('dim_company') }} as c
    on w.company_key = c.company_key
inner join {{ ref('dim_sector') }} as s
    on w.sector_key = s.sector_key
