param(
    [int]$JobId,
    [string]$FilePath,
    [string]$BaseDir,
    [string]$ApiUrl
)

$filename = Split-Path $FilePath -Leaf
$fertig   = "$BaseDir\Fertig\$filename"
$logFile  = "Z:\downloads\Pruefung\vqa_ergebnisse.csv"

# CSV-Header anlegen falls Datei neu
if (-not (Test-Path $logFile)) {
    "Datum,Dateiname,VMAF_Avg,VMAF_Min,SSIM,PSNR,Report" | Out-File $logFile -Encoding UTF8
}

Write-Host "VQA Watcher: Warte auf Job $JobId..."

while ($true) {
    Start-Sleep -Seconds 10
    try {
        $r = Invoke-RestMethod -Uri "$ApiUrl/api/queue/$JobId/results" `
             -ErrorAction Stop -SkipCertificateCheck

        # Datei nach Fertig verschieben
        Move-Item -Path $FilePath -Destination $fertig -Force

        # In CSV schreiben
        $datum  = Get-Date -Format "yyyy-MM-dd HH:mm"
        $report = if ($r.report_url) { "$ApiUrl$($r.report_url)" } else { "" }
        "$datum,$filename,$($r.vmaf_avg),$($r.vmaf_min),$($r.ssim),$($r.psnr),$report" |
            Out-File $logFile -Append -Encoding UTF8

        Write-Host "VQA: '$filename' -> Fertig (VMAF: $($r.vmaf_avg))"

        # Windows Toast-Benachrichtigung
        try {
            [Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
                [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $template.SelectSingleNode('//text[@id="1"]').InnerText = "VQA: $filename fertig"
            $template.SelectSingleNode('//text[@id="2"]').InnerText = "VMAF: $($r.vmaf_avg)"
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("VideoQualityAnalyzer").Show($toast)
        } catch {}

        break

    } catch {
        # 404 = Job nicht gefunden -> abbrechen
        if ($_.Exception.Response.StatusCode.value__ -eq 404) {
            Write-Host "VQA: Job $JobId nicht gefunden, Watcher beendet."
            break
        }
        # 425 = noch nicht fertig -> weiter warten
    }
}
