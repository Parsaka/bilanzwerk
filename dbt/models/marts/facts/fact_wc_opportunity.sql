-- H4: cash that each company could free if DSO and DIO fell to its sector median and DPO
-- rose to it, per fiscal year (latest values, non-financial companies, EUR).
-- Stretch target: the sector's 25th percentile for DSO and DIO, the 75th for DPO.
-- Companies without a sector (no SIC/NACE mapping) stay out: a median over an unmapped,
-- mixed group is no benchmark.
with fy as (
    select
        k.company_id,
        k.company_key,
        k.sector_key,
        k.period_key,
        k.period_end,
        p.fiscal_year,
        k.dso,
        k.dio,
        k.dpo,
        k.rev_ttm_eur,
        k.cogs_ttm_eur
    from {{ ref('int_kpi_wide') }} as k
    inner join {{ ref('dim_period') }} as p
        on k.period_key = p.period_key
    where
        k.version = '{{ var("version_latest") }}'
        and k.is_financial = 0
        and k.sector_key <> '{{ var("unassigned_sector_code") }}'
        and p.is_fiscal_year_end = 1
        and k.dso between 0 and 730
        and k.dpo between 0 and 730
        and k.dio between 0 and 730
        and k.rev_ttm_eur > 0
),

with_benchmarks as (
    select
        fy.*,
        {{ bw_percentile_over('dso', 0.5, 'sector_key, fiscal_year') }} as sector_median_dso,
        {{ bw_percentile_over('dio', 0.5, 'sector_key, fiscal_year') }} as sector_median_dio,
        {{ bw_percentile_over('dpo', 0.5, 'sector_key, fiscal_year') }} as sector_median_dpo,
        {{ bw_percentile_over('dso', 0.25, 'sector_key, fiscal_year') }} as sector_p25_dso,
        {{ bw_percentile_over('dio', 0.25, 'sector_key, fiscal_year') }} as sector_p25_dio,
        {{ bw_percentile_over('dpo', 0.75, 'sector_key, fiscal_year') }} as sector_p75_dpo,
        count(*) over (partition by fy.sector_key, fy.fiscal_year) as sector_peer_count
    from fy
),

gaps as (
    select
        b.*,
        case when b.dso > b.sector_median_dso then b.dso - b.sector_median_dso else 0 end as excess_dso_days,
        case when b.dio > b.sector_median_dio then b.dio - b.sector_median_dio else 0 end as excess_dio_days,
        case when b.dpo < b.sector_median_dpo then b.sector_median_dpo - b.dpo else 0 end as dpo_gap_days,
        case when b.dso > b.sector_p25_dso then b.dso - b.sector_p25_dso else 0 end as stretch_dso_days,
        case when b.dio > b.sector_p25_dio then b.dio - b.sector_p25_dio else 0 end as stretch_dio_days,
        case when b.dpo < b.sector_p75_dpo then b.sector_p75_dpo - b.dpo else 0 end as stretch_dpo_days
    from with_benchmarks as b
)

select
    company_key,
    company_id,
    sector_key,
    period_key,
    period_end as period_end_date,
    fiscal_year,
    dso,
    dio,
    dpo,
    dso + dio - dpo as ccc,
    sector_median_dso,
    sector_median_dio,
    sector_median_dpo,
    sector_peer_count,
    excess_dso_days,
    excess_dio_days,
    dpo_gap_days,
    rev_ttm_eur as revenue_eur,
    cogs_ttm_eur as cogs_eur,
    excess_dso_days * rev_ttm_eur / 365 as cash_from_dso_eur,
    excess_dio_days * coalesce(cogs_ttm_eur, 0) / 365 as cash_from_dio_eur,
    dpo_gap_days * coalesce(cogs_ttm_eur, 0) / 365 as cash_from_dpo_eur,
    excess_dso_days * rev_ttm_eur / 365
    + excess_dio_days * coalesce(cogs_ttm_eur, 0) / 365
    + dpo_gap_days * coalesce(cogs_ttm_eur, 0) / 365 as cash_opportunity_eur,
    stretch_dso_days * rev_ttm_eur / 365
    + stretch_dio_days * coalesce(cogs_ttm_eur, 0) / 365
    + stretch_dpo_days * coalesce(cogs_ttm_eur, 0) / 365 as cash_opportunity_stretch_eur
from gaps
where sector_peer_count >= {{ var('wc_min_sector_peers') }}
