-- One flat extract for Tableau Public: working-capital opportunity with company and sector.
-- Name, CIK and LEI are the company's current ones, so every row of one company carries the same
-- key: with the name valid at each fiscal year, a renamed company showed up as two companies
-- and the workbook's "latest fiscal year per company" counted it twice (run 41245747626:
-- 9 149 companies and EUR 1 679 bn against 6 377 and EUR 1 307 bn in H4).
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
    on w.company_id = c.company_id and c.is_current = 1
inner join {{ ref('dim_sector') }} as s
    on w.sector_key = s.sector_key
