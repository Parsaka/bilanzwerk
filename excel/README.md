# Excel-Monatsbericht

`Bilanzwerk_Monatsbericht.xlsm`: the controllers' monthly report on top of the Power BI
semantic model.

| Sheet | What it does |
|---|---|
| Cockpit | One printable page with a fixed layout: CUBEELEMENT/CUBEWERT formulas for amounts (fiscal year, prior year, plan), ten KPIs at fiscal year end with sector percentile and red flag, the early-warning block (champion model). |
| Stammdaten | Golden record (current version) via Power Query from `marts.dim_company`; the cockpit looks up ID, LEI, CIK, sector, country and status with XVERWEIS from the company in `C3`. |
| Risikoliste | Power Query: latest risk scores of the champion model, riskiest first. |
| Peer | PivotTable on the semantic model with slicers for sector and fiscal year. |
| Hinweise | Connection name (`BW_Verbindung`), how to use, glossary pointers. |

Macro `RefreshAndExport` (module `modRefreshAndExport.bas`) refreshes all connections in the
foreground, waits for the CUBE formulas, refuses to export a cockpit with error values, and
saves the cockpit as `Export/Management_Cockpit_<Unternehmen>_GJ<Jahr>_<Datum>.pdf`.

## Results workbook without Fabric

`Bilanzwerk_Ergebnisse.xlsx` holds the results of the real-data run as values with native
Excel charts (answer H1–H4, sectors, top 20, models, lead times, case studies, label audit,
data quality). It opens anywhere; the live report below needs the semantic model.

```bash
git archive origin/real-data-results results | tar -x -C /tmp/r
uv run python scripts/results_workbook.py --results /tmp/r/results
```

## Build

```bash
uv run python excel/build_workbook.py      # cells, formulas, formats, print setup (any OS)
```

```powershell
# Windows with Excel: connection, Power Query, PivotTable and slicers, VBA module -> .xlsm
.\excel\finalize_workbook.ps1 -Workspace "Bilanzwerk" -SqlEndpoint "<endpoint>.datawarehouse.fabric.microsoft.com" -Warehouse "wh_bilanzwerk"
```

The split is deliberate: everything that is plain cell content is generated and reviewed as
code; the parts that only Excel can write (OLAP connection, Power Query mashup, pivot caches,
the compiled VBA project) are added by Excel itself through the script, so nothing binary is
hand-assembled.

## Notes

* **Why company_id and not the name:** the cube member for the company is the golden record ID
  (`[dim_company].[company_id]`). A company that changed its name keeps its history; slicing by
  name would drop the years before the rename (SCD type 2 in `dim_company`).
* **Fiscal year:** amounts slice by `dim_period[fiscal_year]` (flows summed over the four quarters,
  balances at year end via `[Bestand]`); KPIs additionally by `is_fiscal_year_end = 1`.
* **Plan** exists for revenue only (`int_revenue_plan`, frozen on 1 January).
* **Access:** CUBE formulas and the PivotTable go through the semantic model, so RLS (Sektor-Team)
  and OLS (Reporting) apply. Power Query reads the Warehouse directly and needs the Analyst role.
* **VBA in Git:** after changing the macro in the VBA editor, export the module over
  `excel/modRefreshAndExport.bas` (right click > Export file). Git stores it as UTF-8 and checks it
  out as Windows-1252 with CRLF (`.gitattributes`), which is what the VBA editor expects.
* **Not yet tested against the live model:** the formulas and the script were written against the
  model in `powerbi/`, the layout was checked by rendering the generated file; the first run on
  Windows against the deployed model is still open.
