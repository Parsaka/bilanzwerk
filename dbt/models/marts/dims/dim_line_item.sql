-- Hierarchy: statement (Bilanz, GuV, Cashflow) > group (Aktiva, Passiva, ...) > line item.
select
    line_item_code as line_item_key,
    line_item_code,
    statement_code,
    statement_de,
    statement_en,
    group_code,
    group_de,
    group_en,
    label_de,
    label_en,
    period_type,
    is_monetary,
    is_core,
    sort_order,
    owner
from {{ ref('line_items') }}
