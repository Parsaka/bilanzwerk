select
    kpi_code as kpi_key,
    kpi_code,
    name_de,
    name_en,
    area,
    formula as formula_text,
    unit,
    direction,
    threshold_green,
    threshold_red,
    owner,
    source_line_items,
    description_de
from {{ ref('kpi_definitions') }}
