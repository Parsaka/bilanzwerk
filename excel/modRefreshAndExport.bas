Attribute VB_Name = "modRefreshAndExport"
'==============================================================================
' Bilanzwerk Monatsbericht
' RefreshAndExport: aktualisiert alle Verbindungen (Semantikmodell, Power Query)
' synchron, wartet auf die CUBE-Formeln und speichert das Blatt "Cockpit" als
' PDF mit Datum im Unterordner "Export" neben der Arbeitsmappe.
'
' Quelle in Git: excel/modRefreshAndExport.bas
' Import: excel/finalize_workbook.ps1 oder VBA-Editor > Datei > Datei importieren
'==============================================================================
Option Explicit

Private Const COCKPIT_SHEET As String = "Cockpit"
Private Const EXPORT_FOLDER As String = "Export"

Public Sub RefreshAndExport()
    Dim pdfPath As String
    On Error GoTo Fail

    Application.ScreenUpdating = False
    Application.StatusBar = "Bilanzwerk: Verbindungen werden aktualisiert ..."
    RefreshAllConnections

    Application.StatusBar = "Bilanzwerk: CUBE-Formeln werden berechnet ..."
    Application.CalculateFull
    Application.CalculateUntilAsyncQueriesDone

    If Not CockpitIsComplete() Then
        Err.Raise vbObjectError + 513, "RefreshAndExport", _
            "Das Cockpit enthält Fehlerwerte (#N/A, #NAME?, #VALUE!). " & _
            "Verbindung '" & ThisWorkbook.Names("BW_Verbindung").RefersToRange.Value & "' und Unternehmen prüfen."
    End If

    pdfPath = ExportCockpit()
    Application.StatusBar = False
    Application.ScreenUpdating = True
    MsgBox "Cockpit gespeichert:" & vbCrLf & pdfPath, vbInformation, "Bilanzwerk"
    Exit Sub

Fail:
    Application.StatusBar = False
    Application.ScreenUpdating = True
    MsgBox "Aktualisierung oder Export fehlgeschlagen:" & vbCrLf & Err.Description, vbExclamation, "Bilanzwerk"
End Sub

' Refresh every connection in the foreground so the export never sees stale values.
' The background setting of each connection is restored afterwards.
Private Sub RefreshAllConnections()
    Dim conn As WorkbookConnection
    Dim background As Boolean

    For Each conn In ThisWorkbook.Connections
        Select Case conn.Type
            Case xlConnectionTypeOLEDB
                background = conn.OLEDBConnection.BackgroundQuery
                conn.OLEDBConnection.BackgroundQuery = False
                conn.Refresh
                conn.OLEDBConnection.BackgroundQuery = background
            Case xlConnectionTypeODBC
                background = conn.ODBCConnection.BackgroundQuery
                conn.ODBCConnection.BackgroundQuery = False
                conn.Refresh
                conn.ODBCConnection.BackgroundQuery = background
            Case Else
                conn.Refresh
        End Select
    Next conn

    Dim ws As Worksheet, pt As PivotTable
    For Each ws In ThisWorkbook.Worksheets
        For Each pt In ws.PivotTables
            pt.PivotCache.Refresh
        Next pt
    Next ws
End Sub

' True when no cell in the cockpit's print area holds an error value.
Private Function CockpitIsComplete() As Boolean
    Dim cell As Range
    For Each cell In ThisWorkbook.Worksheets(COCKPIT_SHEET).Range("Print_Area").Cells
        If IsError(cell.Value) Then
            CockpitIsComplete = False
            Exit Function
        End If
    Next cell
    CockpitIsComplete = True
End Function

' Saves the cockpit as Export\Management_Cockpit_<Unternehmen>_<GJ>_<yyyy-mm-dd>.pdf.
Private Function ExportCockpit() As String
    Dim folder As String, company As String, fiscalYear As String, path As String
    Dim ws As Worksheet

    Set ws = ThisWorkbook.Worksheets(COCKPIT_SHEET)
    folder = ThisWorkbook.Path & Application.PathSeparator & EXPORT_FOLDER
    If Dir(folder, vbDirectory) = "" Then MkDir folder

    company = SafeFileName(CStr(ws.Range("C3").Value))
    fiscalYear = CStr(ws.Range("C4").Value)
    path = folder & Application.PathSeparator & "Management_Cockpit_" & company & "_GJ" & fiscalYear & "_" & _
           Format(Date, "yyyy-mm-dd") & ".pdf"

    ws.ExportAsFixedFormat Type:=xlTypePDF, Filename:=path, Quality:=xlQualityStandard, _
        IncludeDocProperties:=True, IgnorePrintAreas:=False, OpenAfterPublish:=False
    ExportCockpit = path
End Function

Private Function SafeFileName(ByVal text As String) As String
    Dim bad As Variant, ch As Variant
    bad = Array("\", "/", ":", "*", "?", """", "<", ">", "|", ".", ",")
    For Each ch In bad
        text = Replace(text, ch, "")
    Next ch
    SafeFileName = Replace(Trim$(text), " ", "_")
End Function
