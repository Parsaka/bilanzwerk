<#
.SYNOPSIS
  Turns excel/Bilanzwerk_Monatsbericht.xlsx (built by build_workbook.py) into the finished
  Bilanzwerk_Monatsbericht.xlsm: connection to the semantic model, Power Query sheets,
  peer PivotTable with slicers, VBA module.

.DESCRIPTION
  Needs Windows with desktop Excel (Microsoft 365), the MSOLAP provider that comes with it,
  and "Trust access to the VBA project object model" switched on
  (File > Options > Trust Center > Trust Center Settings > Macro Settings).
  Sign-in to Power BI and the Fabric Warehouse happens in the Excel dialogs on first refresh.

.EXAMPLE
  .\excel\finalize_workbook.ps1 -Workspace "Bilanzwerk" -SqlEndpoint "xxxx.datawarehouse.fabric.microsoft.com" -Warehouse "wh_bilanzwerk"
#>
param(
    [Parameter(Mandatory = $true)] [string] $Workspace,
    [Parameter(Mandatory = $true)] [string] $SqlEndpoint,
    [Parameter(Mandatory = $true)] [string] $Warehouse,
    [string] $Dataset = "Bilanzwerk",
    [string] $ConnectionName = "Bilanzwerk"
)
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $here "Bilanzwerk_Monatsbericht.xlsx"
$target = Join-Path $here "Bilanzwerk_Monatsbericht.xlsm"
$bas = Join-Path $here "modRefreshAndExport.bas"
if (-not (Test-Path $source)) { throw "Run 'uv run python excel/build_workbook.py' first: $source is missing." }

# Excel constants
$xlCmdCube = 1; $xlCmdSql = 2; $xlSrcExternal = 0; $xlYes = 1
$xlExternal = 2; $xlPivotTableVersion15 = 5
$xlRowField = 1; $xlDataField = 4; $xlOpenXMLWorkbookMacroEnabled = 52

function Add-QueryTable($wb, $sheetName, $queryName, $sql) {
    $m = @"
let
    Source = Sql.Database("$SqlEndpoint", "$Warehouse", [Query = "$($sql -replace '"', '""')"])
in
    Source
"@
    $existing = $wb.Queries | Where-Object { $_.Name -eq $queryName }
    if ($existing) { $existing.Delete() }
    [void] $wb.Queries.Add($queryName, $m)
    $ws = $wb.Worksheets.Item($sheetName)
    $conn = "OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=`$Workbook`$;Location=$queryName;Extended Properties=`"`""
    $lo = $ws.ListObjects.Add($xlSrcExternal, $conn, [Type]::Missing, $xlYes, $ws.Range("A1"))
    $lo.Name = $queryName
    $lo.QueryTable.CommandType = $xlCmdSql
    $lo.QueryTable.CommandText = "SELECT * FROM [$queryName]"
    $lo.QueryTable.BackgroundQuery = $false
    $lo.QueryTable.Refresh($false) | Out-Null
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $true          # sign-in dialogs need a visible Excel
$excel.DisplayAlerts = $false
try {
    $wb = $excel.Workbooks.Open($source)

    # 1. Connection to the semantic model over the XMLA endpoint (same as Analyze in Excel).
    $cs = "OLEDB;Provider=MSOLAP.8;Data Source=powerbi://api.powerbi.com/v1.0/myorg/$Workspace;" +
          "Initial Catalog=$Dataset;Integrated Security=ClaimsToken"
    $old = $wb.Connections | Where-Object { $_.Name -eq $ConnectionName }
    if ($old) { $old.Delete() }
    $model = $wb.Connections.Add2($ConnectionName, "Semantikmodell Bilanzwerk (Power BI)", $cs, "Model", $xlCmdCube)
    $wb.Worksheets.Item("Hinweise").Range("B1").Value2 = $ConnectionName

    # 2. Power Query: golden record (XLOOKUP source, columns A:I in this order) and the risk list.
    Add-QueryTable $wb "Stammdaten" "Stammdaten" @"
select c.company_name, c.company_id, c.lei, c.cik, s.sector_de, c.country_code, c.hq_city,
       c.company_status, c.match_source
from marts.dim_company as c
left join marts.dim_sector as s on s.sector_key = c.sector_key
where c.is_current = 1
order by c.company_name
"@
    Add-QueryTable $wb "Risikoliste" "Risikoliste" @"
select c.company_name, s.sector_de, r.as_of_date, r.probability_12m, r.risk_band, r.top_3_drivers
from marts.fact_risk_score as r
join marts.dim_company as c on c.company_key = r.company_key
left join marts.dim_sector as s on s.sector_key = c.sector_key
where r.is_champion = 1
  and r.as_of_date = (select max(as_of_date) from marts.fact_risk_score where is_champion = 1)
order by r.probability_12m desc
"@

    # 3. Peer table: PivotTable on the semantic model with slicers for sector and fiscal year.
    $peer = $wb.Worksheets.Item("Peer")
    $cache = $wb.PivotCaches().Create($xlExternal, $model, $xlPivotTableVersion15)
    $pt = $cache.CreatePivotTable($peer.Range("A4"), "PeerVergleich")
    $pt.ManualUpdate = $true
    $pt.CubeFields.Item("[dim_company].[company_name]").Orientation = $xlRowField
    foreach ($m in @("Umsatz", "EBIT-Marge", "Eigenkapitalquote", "DSO", "DIO", "DPO", "CCC", "Risiko 12M")) {
        $pt.CubeFields.Item("[Measures].[$m]").Orientation = $xlDataField
    }
    $pt.ManualUpdate = $false
    $top = 4 * 15
    foreach ($f in @(@("[dim_sector].[sector_de]", "Sektor"), @("[dim_period].[fiscal_year]", "Geschäftsjahr"))) {
        $sc = $wb.SlicerCaches.Add2($pt, $f[0])
        [void] $sc.Slicers.Add($peer, [Type]::Missing, $f[1], $f[1], $top, 820, 180, 200)
        $top += 210
    }

    # 4. VBA module from Git.
    try {
        [void] $wb.VBProject.VBComponents.Import($bas)
    } catch {
        throw "VBA import refused: switch on 'Trust access to the VBA project object model' and run again."
    }

    $wb.Worksheets.Item("Cockpit").Activate()
    $excel.CalculateFull()
    $wb.SaveAs($target, $xlOpenXMLWorkbookMacroEnabled)
    Write-Host "Saved $target"
} finally {
    if ($wb) { $wb.Close($false) }
    $excel.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}
