# Video Quality Analyzer PRO

**Beta v1.0** — Professionelles Tool zur Videoqualitätsanalyse mit Vergleich von Original- und encodierten Videos.

Verfügbar als **Desktop-App** (Windows/Linux) und als **Web-Version** für NAS/Unraid (im Browser bedienbar).

---

## Features

| Metrik | Beschreibung |
|---|---|
| **VMAF** | Netflix-Qualitätsmetrik (perceptual quality score) |
| **SSIM** | Strukturelle Ähnlichkeit zwischen Original und Encoded |
| **PSNR** | Peak Signal-to-Noise Ratio |
| **Bitrate** | Bitratenanalyse über die gesamte Videolänge |
| **Artifacts** | Automatische Artefakt-Erkennung mit Heatmap |
| **Frame Drops** | Erkennung von Frame-Drops und Duplikaten |
| **Audio** | Audio-Stream-Analyse (Codec, Samplerate, Bitrate, Kanäle) |
| **HDR** | HDR/Dolby Vision Erkennung (HDR10, HLG, Dolby Vision) |
| **Szenenanalyse** | Szenenwechsel-Erkennung |

- Vergleichsmodus: Original vs. Encoded nebeneinander
- Solo-Modus: Einzelvideo analysieren (kein Original nötig)
- **Mehrfachanalyse (Batch-Modus):** Mehrere Video-Paare als Queue anlegen und sequenziell abarbeiten
  - Beliebig viele Jobs hinzufügen, einzeln konfigurieren (Metriken, Modus, Subsampling, GPU)
  - Batch-Import: N Originale + N Encoded gleichzeitig auswählen — automatisch nach Dateiname gepaart
  - Jobs per Drag & Drop (↑/↓) umsortieren, einzeln bearbeiten oder entfernen
  - GPU-Auswahl direkt im Mehrfachanalyse-Tab, auf alle Jobs anwendbar
- Integrierter Video-Player mit synchronem Vergleich
- HTML-Report Export (Dark & Light Mode)
- VMAF-Graph als PNG (Qualitätszonen, Durchschnitts- & Min-Linie, Zeitachse)
- Artefakt-Heatmap (Zeitachse, Max-Markierung, Threshold-Linie, Dark/Light Mode)
- **Queue-Persistenz:** Jobs bleiben nach Container-/App-Neustart erhalten
- Dark/Light Mode
- GPU-Beschleunigung (NVIDIA CUDA)
- Mobil-optimiertes Layout (Web-Version)
- REST-API mit Swagger-Dokumentation (Web-Version)

---

## Desktop-App

### Voraussetzungen

- Python 3.10+
- FFmpeg mit libvmaf Support

```bash
pip install -r requirements.txt
```

### FFmpeg (mit libvmaf)

**Windows:** `ffmpeg.exe` und `ffprobe.exe` mit libvmaf ins Projektverzeichnis legen.

**Linux:**

```bash
pip install --break-system-packages static-ffmpeg
python3 get_ffmpeg.py
chmod +x ffmpeg ffprobe
```

Die Datei `get_ffmpeg.py` liegt bereits im Projektordner und kann danach gelöscht werden:
```bash
rm get_ffmpeg.py
```

> **Hinweis:** `--break-system-packages` ist auf Debian/Ubuntu/Linux Mint nötig. Alternativ funktioniert auch `pip install --user static-ffmpeg` falls `static-ffmpeg` bereits im User-Pfad installiert ist.

### Starten

**Windows:**
```bash
python main_gui.py
```

**Linux:**
```bash
python3 main_gui.py
```

### Windows EXE selbst erstellen

```powershell
py -3.13 -m PyInstaller --noconfirm --onefile --windowed `
  --add-binary "ffmpeg.exe;." `
  --add-binary "ffprobe.exe;." `
  --add-data "modules;modules" `
  --add-data "icon.ico;." `
  --collect-all matplotlib `
  --collect-all cv2 `
  --collect-all PIL `
  --collect-all numpy `
  --icon="icon.ico" `
  --name "VideoQualityAnalyzerPro" main_gui.py
```

Die EXE liegt danach in `dist\VideoQualityAnalyzerPro.exe`.

---

## Web-Version (Docker / NAS / Unraid)

Die Web-Version läuft als Docker-Container und ist über den Browser erreichbar.

### Schnellstart (Unraid / NAS)

```bash
mkdir -p /mnt/user/appdata/VideoQualityAnalyzerPro

# Compose-Datei herunterladen
wget https://raw.githubusercontent.com/Modi-224412/VideoQualityAnalyzerPro/main/docker-compose.unraid.yml \
  -O /mnt/user/appdata/VideoQualityAnalyzerPro/docker-compose.yml

# Starten – config.json und queue.json werden beim ersten Start automatisch angelegt
cd /mnt/user/appdata/VideoQualityAnalyzerPro
docker compose up -d
```

Browser öffnen: **`http://NAS-IP:2498`**

> **Hinweis:** `config.json` und `queue.json` werden beim ersten Start automatisch unter `/mnt/user/appdata/VideoQualityAnalyzerPro/` angelegt. Kein manueller Schritt nötig.

### Web-Features

- Vollständige Analyse-Oberfläche im Browser
- **Mehrfachanalyse (Batch-Modus):** Jobs anlegen, per Batch-Import paaren und sequenziell abarbeiten lassen
- **Queue-Persistenz:** Jobs bleiben nach Container-Neustart erhalten (gespeichert in `queue.json`)
- Server-seitiger Datei-Browser für Video-Auswahl
- Live-Konsole mit Echtzeit-Logs
- Integrierter Video-Player (Einzel & synchroner Vergleich)
- Dark / Light Mode
- NVIDIA GPU wird automatisch erkannt — Fallback auf CPU
- Reports & Graphs direkt im Browser öffnen
- Responsives Layout — nutzbar auf Smartphone und Tablet
- REST-API für externe Steuerung und Automatisierung

### Video-Player: Web vs. Desktop

Der integrierte Video-Player unterscheidet sich je nach Version:

| Funktion | Desktop-App (EXE) | Web-Version |
|---|:---:|:---:|
| Einzel-Player | ✅ | ✅ |
| Synchroner Vergleich (Side-by-Side) | ✅ | ✅ |
| Seeking / Vor- & Zurückspulen | ✅ | ✅ (browserabhängig) |
| Vollbild | ✅ | ✅ |
| Frame-genaue Steuerung | ✅ | ❌ |
| Codec-Unterstützung | Alle (via FFmpeg/FFplay) | Nur Browser-native Codecs (H.264, H.265, VP9, AV1) |
| HEVC / H.265 | ✅ | ⚠️ (Chrome, Edge, Firefox) |

> **Hinweis:** Der Web-Player nutzt den HTML5-Videoplayer des Browsers. Formate wie MKV mit HEVC können je nach Browser und Betriebssystem eingeschränkt sein. Die Analyse selbst läuft immer vollständig über FFmpeg auf dem Server — der Player dient nur zur visuellen Kontrolle.

### REST-API ⚠️ Experimentell

> **Hinweis:** Die REST-API befindet sich noch in der experimentellen Phase. Endpunkte und Verhalten können sich in zukünftigen Versionen ändern.

Die Web-Version bietet eine REST-API unter dem Präfix `/api/`.
Interaktive Dokumentation ist automatisch verfügbar:

- **Swagger UI:** `http://NAS-IP:2498/docs`
- **ReDoc:** `http://NAS-IP:2498/redoc`

#### Endpunkte

**Einzelanalyse**

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/start` | Analyse starten |
| `POST` | `/api/stop` | Analyse abbrechen |
| `GET` | `/api/status` | Fortschritt & Status |
| `GET` | `/api/results` | Metriken als JSON (nach Abschluss) |
| `GET` | `/api/reports/list` | Alle HTML-Reports auflisten |
| `GET` | `/api/screenshots/list` | Screenshots auflisten |
| `GET` | `/api/heatmaps/list` | Heatmaps auflisten |
| `GET` | `/api/gpu` | GPU-Info |

**Mehrfachanalyse (Queue)**

| Methode | Pfad | Beschreibung |
|---|---|---|
| `POST` | `/api/queue/add` | Job zur Queue hinzufügen |
| `GET` | `/api/queue` | Alle Jobs anzeigen (inkl. Status & Ergebnisse) |
| `POST` | `/api/queue/start` | Queue starten |
| `POST` | `/api/queue/stop` | Queue stoppen & laufenden Job abbrechen |
| `POST` | `/api/queue/reorder` | Reihenfolge der wartenden Jobs ändern |
| `DELETE` | `/api/queue/{id}` | Wartenden Job entfernen |
| `DELETE` | `/api/queue` | Abgeschlossene Jobs löschen |
| `GET` | `/api/queue/{id}/results` | Ergebnisse eines einzelnen Jobs abrufen |

#### Beispiel: Analyse per curl starten

```bash
# Vergleichsanalyse starten
curl -X POST http://NAS-IP:2498/api/start \
  -H "Content-Type: application/json" \
  -d '{
    "orig_path": "/data/original.mkv",
    "enco_path": "/data/encoded.mp4",
    "metrics": ["VMAF", "SSIM", "PSNR"]
  }'

# Fortschritt abfragen
curl http://NAS-IP:2498/api/status

# Ergebnisse holen (nach Abschluss)
curl http://NAS-IP:2498/api/results
# → {"mode": "comparison", "vmaf_avg": 94.2, "vmaf_min": 81.5, "ssim": 0.98421, "psnr": 42.3, "report_url": "/reports/..."}
```

#### Parameter für `/api/start`

| Parameter | Typ | Standard | Beschreibung |
|---|---|---|---|
| `orig_path` | string | — | Pfad zum Originalvideo |
| `enco_path` | string | — | Pfad zum encodierten Video |
| `metrics` | array | alle | Aktive Metriken (VMAF, SSIM, PSNR, BITRATE, ARTIFACTS, FRAME DROPS, AUDIO) |
| `solo_mode` | bool | `false` | Solo-Modus (kein Original nötig) |
| `subsample` | int | `1` | VMAF-Subsampling (höher = schneller, weniger genau) |
| `offset_sec` | float | `0.0` | Zeitversatz zwischen Original und Encoded (Sekunden) |
| `art_frames` | int | `1000` | Anzahl Frames für Artefakt-Scan |
| `dark_mode` | bool | `true` | Dark Mode im HTML-Report |

---

### Container aktualisieren

```bash
docker compose pull && docker compose up -d
```

### GPU-Support

| GPU | Desktop-App | Web / Docker | Beschleunigung |
|---|:---:|:---:|---|
| **NVIDIA** (GTX/RTX) | ✅ | ✅ | CUDA – automatisch erkannt via `nvidia-smi` |
| **AMD** (Radeon RX / Pro) | ⚠️ | ❌ | Kein nativer Support – läuft im CPU-Modus |
| **Intel** (Arc) | ⚠️ | ❌ | Kein nativer Support – läuft im CPU-Modus |
| **CPU-Fallback** | ✅ | ✅ | Immer verfügbar, keine GPU nötig |

> **Docker/Unraid:** Voraussetzung für NVIDIA ist das **NVIDIA Container Toolkit** bzw. das **Unraid NVIDIA Plugin**. AMD und Intel GPUs werden im Container aktuell nicht unterstützt.

---

## Projektstruktur

```
VideoQualityAnalyzerPro/
├── main_gui.py                  # Desktop-App
├── web_app.py                   # Web-Version (FastAPI)
├── Dockerfile                   # Docker-Build
├── docker-compose.yml           # Standard Compose
├── docker-compose.unraid.yml    # Unraid-optimierte Compose
├── templates/index.html         # Web-UI
├── config.json                  # Einstellungen
├── requirements.txt
├── staxrip/                     # StaxRip Integration Scripts
│   ├── vqa_submit.ps1           # Nach Encode aufrufen – Job einstellen & Datei verschieben
│   └── vqa_watcher.ps1          # Hintergrund-Watcher – Ergebnis in CSV + Toast-Notification
└── modules/
    ├── analysis/                # VMAF, SSIM, PSNR, Audio, HDR, Szenen, Frame Drops
    ├── artifact_detection/      # Artefakt-Erkennung
    ├── app/                     # Config, GPU, Analysis-Runner
    ├── player/                  # Video-Player & Vergleichsfenster (Desktop)
    ├── processing/              # FFmpeg Filter-Factory
    ├── reporting/               # HTML-Report Generator
    ├── ui/                      # Theme, UI-Builder, Console (Desktop)
    ├── visualization/           # VMAF-Graph, Artefakt-Heatmap
    └── path_utils.py            # Plattformübergreifende Pfad-Auflösung
```

---

## StaxRip Integration

Die Scripts im Ordner `staxrip/` ermöglichen eine automatische Qualitätsprüfung nach jedem Encode direkt aus StaxRip heraus.

### Funktionsweise

```
StaxRip encodiert → vqa_submit.ps1 läuft → Datei → Bearbeitung\
                                          → Job an API gesendet
                                          → vqa_watcher.ps1 startet im Hintergrund
                                                    ↓
                                          Analyse läuft auf dem NAS
                                                    ↓
                                          Datei → Fertig\
                                          Ergebnis in vqa_ergebnisse.csv
                                          Windows Toast-Benachrichtigung
```

### Ordnerstruktur auf dem NAS

```
downloads/
└── Pruefung/
    ├── Bearbeitung/    ← Datei wird hierher verschoben während Analyse läuft
    ├── Fertig/         ← Datei landet hier nach abgeschlossener Analyse
    └── vqa_ergebnisse.csv  ← Alle Ergebnisse gesammelt (öffenbar in Excel)
```

Ordner auf dem NAS anlegen:
```bash
mkdir -p /mnt/user/downloads/Pruefung/Bearbeitung
mkdir -p /mnt/user/downloads/Pruefung/Fertig
```

### Scripts einrichten (Windows)

1. `staxrip/vqa_submit.ps1` und `staxrip/vqa_watcher.ps1` nach `C:\Scripts\` kopieren
2. In `vqa_submit.ps1` die NAS-IP eintragen:
```powershell
$ApiUrl  = "https://NAS-IP:443"
$BaseDir = "Z:\downloads\Pruefung"
```
3. Pfad-Mapping in der Web-UI einstellen (`⚙️ Einstellungen`):
   - Windows-Pfad (von): `Z:\downloads\`
   - Docker-Pfad (nach): `/data/`

### StaxRip konfigurieren

In StaxRip unter **Tools → Settings → Events → After Encoding**:

```
powershell.exe -ExecutionPolicy Bypass -File "C:\Scripts\vqa_submit.ps1" -Original "%source_file%" -Encoded "%target_file%"
```

### CSV-Ergebnisse

Nach jeder abgeschlossenen Analyse wird `Z:\downloads\Pruefung\vqa_ergebnisse.csv` automatisch ergänzt:

```
Datum,Dateiname,VMAF_Avg,VMAF_Min,SSIM,PSNR,Report
2026-04-12 14:23,film1.mp4,94.2,81.5,0.98421,42.3,https://NAS-IP/reports/...
```

---

## Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE) — du darfst es frei nutzen, verändern und weitergeben, solange der Copyright-Hinweis erhalten bleibt.
