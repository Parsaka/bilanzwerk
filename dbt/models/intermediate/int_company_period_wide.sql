-- One row per company, period end and version with every line item as a column: instants at
-- the period end, flows as TTM. available_at is the latest acceptance time of any input, so
-- a KPI built from this row was public no earlier than that moment (point-in-time rule).
{%- set instants = ['CASH', 'STI', 'AR', 'INV', 'TCA', 'TA', 'AP', 'STD', 'TCL', 'LTD', 'LEASE', 'TL', 'RE', 'EQP', 'EQ', 'TLE', 'CASH_CF'] %}
{%- set flows = ['REV', 'COGS', 'GP', 'DA', 'EBIT', 'INTEXP', 'EBT', 'NI', 'CFO', 'CAPEX', 'OPEX'] %}
select
    version,
    company_id,
    company_key,
    sector_key,
    is_financial,
    period_key,
    period_end,
    max(currency_code) as currency_code,
    {%- for li in instants %}
    max(case when line_item_code = '{{ li }}' then cast(amount_local as {{ bw_float() }}) end) as {{ li | lower }},
    {%- endfor %}
    {%- for li in flows %}
    max(case when line_item_code = '{{ li }}' then cast(amount_ttm_local as {{ bw_float() }}) end) as {{ li | lower }}_ttm,
    max(case when line_item_code = '{{ li }}' then amount_ttm_eur end) as {{ li | lower }}_ttm_eur,
    {%- endfor %}
    max(available_at) as available_at
from {{ ref('int_period_values_golden') }}
where currency_code <> 'shares'
group by version, company_id, company_key, sector_key, is_financial, period_key, period_end
