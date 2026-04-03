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
- VMAF-Graph als PNG
- Artefakt-Heatmap
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

Erstelle eine Hilfsdatei `get_ffmpeg.py` im Projektordner:
```python
import static_ffmpeg, subprocess, shutil
static_ffmpeg.add_paths()
ff = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True).stdout.strip()
fp = subprocess.run(['which', 'ffprobe'], capture_output=True, text=True).stdout.strip()
shutil.copy(ff, 'ffmpeg')
shutil.copy(fp, 'ffprobe')
print('Fertig:', ff)
```

Dann ausführen:
```bash
pip install --break-system-packages static-ffmpeg
python3 get_ffmpeg.py
chmod +x ffmpeg ffprobe
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

# Config-Datei einmalig anlegen (wichtig – sonst wird sie als Verzeichnis gemountet!)
echo '{}' > /mnt/user/appdata/VideoQualityAnalyzerPro/config.json

# Starten
cd /mnt/user/appdata/VideoQualityAnalyzerPro
docker compose up -d
```

Browser öffnen: **`http://NAS-IP:2498`**

> **Hinweis:** Die `config.json` muss vor dem ersten Start manuell angelegt werden. Sie speichert deine Einstellungen (Pfad-Mapping, Queue-Defaults) dauerhaft — auch nach Container-Updates.

### Web-Features

- Vollständige Analyse-Oberfläche im Browser
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

## Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE) — du darfst es frei nutzen, verändern und weitergeben, solange der Copyright-Hinweis erhalten bleibt.
