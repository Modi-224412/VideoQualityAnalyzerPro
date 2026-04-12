param(
    [string]$Original,
    [string]$Encoded
)

# ── Konfiguration ──────────────────────────────────────────────────────────────
$ApiUrl  = "https://NAS-IP:4433"
$BaseDir = "Z:\downloads\Pruefung"
# ──────────────────────────────────────────────────────────────────────────────

# Datei nach Bearbeitung verschieben
$filename    = Split-Path $Encoded -Leaf
$bearbeitung = "$BaseDir\Bearbeitung\$filename"
Move-Item -Path $Encoded -Destination $bearbeitung -Force

Write-Host "VQA: '$filename' -> Bearbeitung"

$body = @{
    orig_path  = $Original
    enco_path  = $bearbeitung
    metrics    = @("VMAF","SSIM","PSNR","BITRATE","ARTIFACTS","FRAME DROPS","AUDIO")
    solo_mode  = $false
    subsample  = 1
    offset_sec = 0.0
    art_frames = 1000
    dark_mode  = $true
} | ConvertTo-Json

try {
    $r = Invoke-RestMethod -Uri "$ApiUrl/api/queue/add" `
         -Method POST -ContentType "application/json" -Body $body `
         -SkipCertificateCheck

    Invoke-RestMethod -Uri "$ApiUrl/api/queue/start" -Method POST `
         -SkipCertificateCheck | Out-Null

    Write-Host "VQA: Job $($r.id) gestartet"

    # Hintergrund-Watcher starten (blockiert StaxRip nicht)
    Start-Process powershell -ArgumentList `
        "-ExecutionPolicy Bypass -File `"$PSScriptRoot\vqa_watcher.ps1`" -JobId $($r.id) -FilePath `"$bearbeitung`" -BaseDir `"$BaseDir`" -ApiUrl `"$ApiUrl`""

} catch {
    Write-Host "VQA Fehler: $_"
}
