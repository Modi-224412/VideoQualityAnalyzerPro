"""
web_app.py – FastAPI Web-Interface für VideoQualityAnalyzerPro

Start:   python3 web_app.py
Browser: http://localhost:2498  oder  http://NAS-IP:2498
"""

import os
import re
import time
import queue
import asyncio
import threading
import webbrowser
import subprocess
import mimetypes
from pathlib import Path
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional

from modules.app.analysis_runner  import AnalysisRunner
from modules.app.config_manager   import ConfigManager
from modules.ui.console_manager   import console
from modules.path_utils            import APP_PATH, get_tool

# ── GPU-Erkennung ─────────────────────────────────────────────────────────────
def _detect_gpu() -> tuple[bool, str]:
    """Prüft ob eine NVIDIA-GPU verfügbar ist. Gibt (verfügbar, Name) zurück."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout.strip():
            name = r.stdout.strip().split("\n")[0].strip()
            return True, name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False, "CPU"

GPU_AVAILABLE, GPU_NAME = _detect_gpu()

# ── App Setup ─────────────────────────────────────────────────────────────────
_TAGS = [
    {
        "name": "Analyse",
        "description": "Analyse starten, stoppen und Ergebnisse abrufen.",
    },
    {
        "name": "Dateien",
        "description": "Gespeicherte Reports, Screenshots und Heatmaps auflisten.",
    },
    {
        "name": "System",
        "description": "GPU-Status und allgemeine System-Informationen.",
    },
    {
        "name": "Mehrfachanalyse",
        "description": (
            "Jobs in die Mehrfachanalyse stellen — werden automatisch nacheinander abgearbeitet. "
            "Ideal für automatische Qualitätsprüfung nach jedem Encode (z.B. StaxRip)."
        ),
    },
]

app = FastAPI(
    title="VideoQualityAnalyzerPro",
    description="""
## Willkommen zur VideoQualityAnalyzerPro API

Mit dieser API kannst du Videoqualitäts-Analysen **automatisiert starten**, den **Fortschritt überwachen**
und die **Ergebnisse als JSON** abrufen — z.B. aus Scripts, Encoding-Pipelines oder anderen Tools.

### Schnellstart

**1. Analyse starten**
```
POST /api/start
```

**2. Fortschritt prüfen**
```
GET /api/status  →  {"status": "Running: 42.0%  |  Remaining: 01:23 min", "progress": 42.0, ...}
```

**3. Ergebnisse holen**
```
GET /api/results  →  {"vmaf_avg": 94.2, "ssim": 0.98, "psnr": 42.3, ...}
```

### Hinweise
- Videodateien liegen im Docker-Container unter `/data/` (gemountet von deinem NAS-Medienordner)
- Über `/api/queue/add` können mehrere Jobs in die **Mehrfachanalyse** gestellt werden — sie werden automatisch nacheinander abgearbeitet
- Die Web-Oberfläche ist unter `/` erreichbar
""",
    version="1.0",
    openapi_tags=_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DIRS = {
    "reports":     os.path.join(APP_PATH, "reports"),
    "temp":        os.path.join(APP_PATH, "temp"),
    "graphs":      os.path.join(APP_PATH, "temp", "graphs"),
    "heatmaps":    os.path.join(APP_PATH, "temp", "heatmaps"),
    "screenshots": os.path.join(APP_PATH, "temp", "screenshots"),
    "uploads":     os.path.join(APP_PATH, "uploads"),
}
for d in DIRS.values():
    os.makedirs(d, exist_ok=True)

# Reports und Temp-Dateien als statische Dateien serven
app.mount("/reports", StaticFiles(directory=DIRS["reports"]), name="reports")
app.mount("/temp",    StaticFiles(directory=DIRS["temp"]),    name="temp")

# ── Job State ─────────────────────────────────────────────────────────────────
ALL_METRICS = ["VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"]

_log_queue: queue.Queue = queue.Queue()

job: dict = {
    "running":    False,
    "aborted":    False,
    "progress":   0.0,
    "status":     "idle",
    "report_url": None,
    "results":    None,
}

# ── Mehrfachanalyse ─────────────────────────────────────────────────────────────
_q_jobs: list[dict]       = []        # alle Jobs (waiting / running / done / failed)
_q_lock: threading.Lock   = threading.Lock()
_q_counter: int           = 0
_q_done_event             = threading.Event()
_q_done_event.set()                   # Initial: kein Job läuft


def _next_qid() -> int:
    global _q_counter
    _q_counter += 1
    return _q_counter


def _queue_worker():
    """Hintergrund-Thread: arbeitet Mehrfachanalysen-Jobs nacheinander ab."""
    while True:
        # Warten bis kein Job mehr läuft
        _q_done_event.wait()

        # Nächsten wartenden Job suchen
        next_job = None
        with _q_lock:
            for j in _q_jobs:
                if j["status"] == "waiting":
                    next_job = j
                    break

        if next_job is None:
            time.sleep(1)
            continue

        # Sicherheitscheck: manueller Job könnte noch laufen
        if job["running"]:
            time.sleep(1)
            continue

        # Job starten
        _q_done_event.clear()
        next_job["status"]     = "running"
        next_job["started_at"] = datetime.now().isoformat(timespec="seconds")

        # Globalen Job-State zurücksetzen (Web-UI zeigt Fortschritt)
        job.update({
            "running": True, "aborted": False,
            "progress": 0.0, "status": "Starting...",
            "report_url": None, "results": None,
        })
        while not _log_queue.empty():
            try: _log_queue.get_nowait()
            except queue.Empty: break

        cbs = _make_callbacks(next_job["art_frames"])

        def _q_done(_qj=next_job):
            _qj["status"]      = "done"
            _qj["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _qj["results"]     = job.get("results")
            _qj["report_url"]  = job.get("report_url")
            job.update({"running": False, "status": "Done", "progress": 100.0})
            _q_done_event.set()

        def _q_failed(_qj=next_job):
            _qj["status"]      = "failed"
            _qj["finished_at"] = datetime.now().isoformat(timespec="seconds")
            job.update({"running": False, "aborted": True,
                        "status": "Aborted", "progress": 0.0})
            _q_done_event.set()

        cbs["on_done"]         = _q_done
        cbs["handle_abort_ui"] = _q_failed

        try:
            runner.cb = cbs
            runner.start(
                orig           = next_job["orig_path"],
                enco           = next_job["enco_path"],
                subsample      = next_job["subsample"],
                gpu_active     = GPU_AVAILABLE,
                dark_mode      = next_job["dark_mode"],
                active_metrics = set(next_job["metrics"]),
                offset_sec     = next_job["offset_sec"],
                solo_mode      = next_job["solo_mode"],
                gpu_type       = "cuda" if GPU_AVAILABLE else "cpu",
                gpu_device     = None,
            )
        except Exception as e:
            next_job["status"]      = "failed"
            next_job["error"]       = str(e)
            next_job["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _q_done_event.set()

        # Auf Abschluss warten, dann nächsten Job
        _q_done_event.wait()
        time.sleep(0.5)


# Worker-Thread starten
_worker_thread = threading.Thread(target=_queue_worker, daemon=True, name="QueueWorker")
_worker_thread.start()


# ── Console → Log-Queue ───────────────────────────────────────────────────────
console.register_ui_callback(lambda msg: _log_queue.put(msg))
console.register_progress_callback(lambda msg: _log_queue.put(msg))

# ── webbrowser.open abfangen → Report-URL speichern ──────────────────────────
def _capture_report_url(url, *a, **kw):
    """Intercepts webbrowser.open() and converts file:// URL to web URL."""
    if url.startswith("file://"):
        filename = Path(url[7:]).name          # z.B. "Report_20260321_120000.html"
        job["report_url"] = f"/reports/{filename}"
    return True

webbrowser.open = _capture_report_url

# ── Callbacks für AnalysisRunner ──────────────────────────────────────────────
def _make_callbacks(art_frames: int = 1000) -> dict:
    def _update_ui(perc: float, start_t: float):
        job["progress"] = perc
        diff = time.time() - start_t
        if perc > 0:
            rem  = ((diff / perc) * 100) - diff
            m, s = divmod(int(rem), 60)
            job["status"] = f"Running: {perc:.1f}%  |  Remaining: {m:02d}:{s:02d} min"
        else:
            job["status"] = f"Running: {perc:.1f}%"

    def _on_abort():
        job.update({"running": False, "aborted": True,
                    "status": "Aborted", "progress": 0.0})

    def _on_done():
        job.update({"running": False, "status": "Done", "progress": 100.0})

    def _on_results(data: dict):
        job["results"] = data

    return {
        "update_ui":           _update_ui,
        "set_progress_busy":   lambda t: job.update({"status": t}),
        "handle_abort_ui":     _on_abort,
        "on_done":             _on_done,
        "on_results":          _on_results,
        "get_artifact_frames": lambda: art_frames,
    }

# ── Config / Queue-Settings ───────────────────────────────────────────────────
_config_mgr = ConfigManager(os.path.join(APP_PATH, "config.json"))

_QUEUE_SETTINGS_DEFAULTS = {
    "path_from":          "",
    "path_to":            "/data/",
    "default_metrics":    list(ALL_METRICS),
    "default_subsample":  1,
    "default_art_frames": 1000,
    "default_dark_mode":  True,
}

def _get_queue_settings() -> dict:
    cfg = _config_mgr.load()
    return {**_QUEUE_SETTINGS_DEFAULTS, **cfg.get("queue_settings", {})}

def _apply_path_mapping(path: str, path_from: str, path_to: str) -> str:
    """Ersetzt das Pfad-Präfix (z.B. Z:\\ → /data/)."""
    if not path_from or not path:
        return path
    norm      = path.replace("\\", "/")
    norm_from = path_from.replace("\\", "/").rstrip("/") + "/"
    norm_to   = path_to.rstrip("/") + "/"
    if norm.lower().startswith(norm_from.lower()):
        return norm_to + norm[len(norm_from):]
    return path


# ── AnalysisRunner ────────────────────────────────────────────────────────────
ffmpeg_path = get_tool("ffmpeg")

runner = AnalysisRunner(
    ffmpeg_path  = ffmpeg_path,
    app_path     = APP_PATH,
    dirs         = DIRS,
    ui_callbacks = _make_callbacks(),
)

# ── Request / Response Models ──────────────────────────────────────────────────
class StartRequest(BaseModel):
    orig_path:  str       = Field(...,  description="Pfad zum **Originalvideo** im Container (z.B. `/data/original.mkv`)")
    enco_path:  str       = Field(...,  description="Pfad zum **encodierten Video** im Container (z.B. `/data/encoded.mp4`)")
    metrics:    List[str] = Field(ALL_METRICS, description="Aktive Metriken. Mögliche Werte: `VMAF`, `SSIM`, `PSNR`, `BITRATE`, `ARTIFACTS`, `FRAME DROPS`, `AUDIO`")
    solo_mode:  bool      = Field(False, description="**Solo-Modus**: Analysiert nur das `enco_path`-Video ohne Referenz. `orig_path` wird ignoriert. Nur BITRATE, ARTIFACTS, FRAME DROPS und AUDIO verfügbar.")
    subsample:  int       = Field(1,    description="VMAF-Subsampling: nur jeden n-ten Frame analysieren. `1` = alle Frames (genaueste), `4` = jeden 4. Frame (schneller).", ge=1, le=100)
    offset_sec: float     = Field(0.0,  description="Zeitversatz in Sekunden zwischen Original und Encoded (falls die Videos nicht synchron beginnen).")
    art_frames: int       = Field(1000, description="Maximale Anzahl Frames für den Artefakt-Scan. Mehr Frames = genauer, aber langsamer.", ge=1)
    dark_mode:  bool      = Field(True, description="Dark Mode im generierten HTML-Report.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Vergleichsanalyse (VMAF + SSIM + PSNR)",
                    "value": {
                        "orig_path":  "/data/original.mkv",
                        "enco_path":  "/data/encoded.mp4",
                        "metrics":    ["VMAF", "SSIM", "PSNR"],
                        "solo_mode":  False,
                        "subsample":  1,
                        "offset_sec": 0.0,
                        "art_frames": 1000,
                        "dark_mode":  True,
                    }
                },
                {
                    "summary": "Solo-Scan (kein Original nötig)",
                    "value": {
                        "orig_path":  "",
                        "enco_path":  "/data/encoded.mp4",
                        "metrics":    ["BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"],
                        "solo_mode":  True,
                        "subsample":  1,
                        "offset_sec": 0.0,
                        "art_frames": 500,
                        "dark_mode":  True,
                    }
                },
            ]
        }
    }


class QueueSettings(BaseModel):
    path_from:          str       = Field("",       description="Externes Pfad-Präfix das ersetzt wird (z.B. `Z:\\\\` oder `\\\\\\\\NAS\\\\downloads\\\\`). Leer lassen = kein Mapping.")
    path_to:            str       = Field("/data/", description="Docker/Container Pfad-Präfix (z.B. `/data/`)")
    default_metrics:    List[str] = Field(default_factory=lambda: list(ALL_METRICS), description="Standard-Metriken für Queue-Jobs")
    default_subsample:  int       = Field(1,    ge=1, le=100, description="Standard VMAF-Subsampling")
    default_art_frames: int       = Field(1000, ge=1,         description="Standard Artefakt-Frames")
    default_dark_mode:  bool      = Field(True,               description="Dark Mode im Report")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "summary": "StaxRip auf Windows mit Z:-Laufwerk",
                "value": {
                    "path_from":          "Z:\\",
                    "path_to":            "/data/",
                    "default_metrics":    ["VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"],
                    "default_subsample":  1,
                    "default_art_frames": 1000,
                    "default_dark_mode":  True,
                }
            }]
        }
    }


class JobStatus(BaseModel):
    running:    bool
    aborted:    bool
    progress:   float           = Field(description="Fortschritt in Prozent (0–100)")
    status:     str             = Field(description="Statustext, z.B. 'Running: 42.0%  |  Remaining: 01:23 min' oder 'Done'")
    report_url: Optional[str]   = Field(None, description="Relativer URL zum HTML-Report, sobald die Analyse abgeschlossen ist")
    results:    Optional[dict]  = Field(None, description="Metriken nach Abschluss (auch über `/api/results` abrufbar)")

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(os.path.join(APP_PATH, "templates", "index.html"))


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join(APP_PATH, "icon.ico"))


@app.get("/icon.png")
async def icon_png():
    return FileResponse(os.path.join(APP_PATH, "icon.png"))


@app.get("/screenshots/list")
async def list_screenshots():
    """Gibt alle vorhandenen Screenshots zurück."""
    shots_dir = DIRS["screenshots"]
    try:
        files = sorted(
            [f for f in os.listdir(shots_dir) if f.lower().endswith((".jpg", ".png"))],
        )
        return {"screenshots": [{"name": f, "url": f"/temp/screenshots/{f}"} for f in files]}
    except Exception:
        return {"screenshots": []}


@app.get("/reports/list")
async def list_reports():
    """Gibt alle vorhandenen HTML-Reports zurück, neueste zuerst."""
    reports_dir = DIRS["reports"]
    try:
        files = sorted(
            [f for f in os.listdir(reports_dir) if f.endswith(".html")],
            reverse=True
        )
        return {"reports": [{"name": f, "url": f"/reports/{f}"} for f in files]}
    except Exception:
        return {"reports": []}


@app.post("/start")
async def start_analysis(req: StartRequest):
    if job["running"]:
        return JSONResponse({"error": "Analysis already running"}, status_code=409)

    # Job-State zurücksetzen
    job.update({
        "running":    True,
        "aborted":    False,
        "progress":   0.0,
        "status":     "Starting...",
        "report_url": None,
        "results":    None,
    })

    # Log-Queue leeren
    while not _log_queue.empty():
        try:
            _log_queue.get_nowait()
        except queue.Empty:
            break

    runner.cb = _make_callbacks(req.art_frames)
    runner.start(
        orig           = req.orig_path,
        enco           = req.enco_path,
        subsample      = req.subsample,
        gpu_active     = GPU_AVAILABLE,
        dark_mode      = req.dark_mode,
        active_metrics = set(req.metrics),
        offset_sec     = req.offset_sec,
        solo_mode      = req.solo_mode,
        gpu_type       = "cuda" if GPU_AVAILABLE else "cpu",
        gpu_device     = None,
    )
    return {"status": "started"}


@app.post("/stop")
async def stop_analysis():
    if not job["running"]:
        return {"status": "not running"}
    runner.stop()
    return {"status": "stopped"}


@app.get("/status")
async def get_status():
    return job


@app.get("/gpu")
async def gpu_info():
    return {"available": GPU_AVAILABLE, "name": GPU_NAME}


@app.get("/stream")
async def stream_video(path: str, request: Request):
    """Streamt eine Videodatei mit Range-Request-Support (für Browser-Seeking)."""
    ALLOWED = ("/data", APP_PATH)
    real = os.path.realpath(path)
    if not any(real.startswith(os.path.realpath(a)) for a in ALLOWED):
        return JSONResponse({"error": "Zugriff verweigert"}, status_code=403)
    if not os.path.isfile(real):
        return JSONResponse({"error": "Datei nicht gefunden"}, status_code=404)

    file_size  = os.path.getsize(real)
    mime_type  = mimetypes.guess_type(real)[0] or "video/mp4"
    range_hdr  = request.headers.get("range")

    if range_hdr:
        m = re.match(r"bytes=(\d+)-(\d*)", range_hdr)
        if m:
            start = int(m.group(1))
            end   = int(m.group(2)) if m.group(2) else file_size - 1
            end   = min(end, file_size - 1)
            length = end - start + 1

            def _chunk():
                with open(real, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        data = f.read(min(65536, remaining))
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            return StreamingResponse(_chunk(), status_code=206, headers={
                "Content-Range":  f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(length),
                "Content-Type":   mime_type,
            })

    def _full():
        with open(real, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(_full(), headers={
        "Accept-Ranges":  "bytes",
        "Content-Length": str(file_size),
        "Content-Type":   mime_type,
    })


@app.get("/browse")
async def browse(path: str = "/data"):
    """Gibt Verzeichnisinhalt zurück – nur Verzeichnisse und Videodateien."""
    VIDEO_EXT = {".mkv",".mp4",".avi",".mov",".ts",".m2ts",".wmv",".flv",".webm",".m4v",".mpg",".mpeg"}

    # Sicherheit: nur innerhalb erlaubter Wurzeln
    ALLOWED = ("/data", APP_PATH + "/reports", APP_PATH + "/temp")
    real = os.path.realpath(path)
    if not any(real.startswith(os.path.realpath(a)) for a in ALLOWED):
        return JSONResponse({"error": "Zugriff verweigert"}, status_code=403)

    if not os.path.isdir(real):
        return JSONResponse({"error": "Kein Verzeichnis"}, status_code=400)

    entries = []
    try:
        for item in sorted(os.scandir(real), key=lambda e: (not e.is_dir(), e.name.lower())):
            if item.is_dir():
                entries.append({"name": item.name, "path": item.path, "type": "dir"})
            elif os.path.splitext(item.name)[1].lower() in VIDEO_EXT:
                size = item.stat().st_size
                entries.append({"name": item.name, "path": item.path, "type": "file",
                                 "size": f"{size / 1_073_741_824:.2f} GB" if size > 1e9
                                         else f"{size / 1_048_576:.1f} MB"})
    except PermissionError:
        pass

    parent = str(Path(real).parent) if real != "/" else None
    return {"path": real, "parent": parent, "entries": entries}


@app.get("/logs")
async def stream_logs(request: Request):
    """SSE-Endpoint: streamt Live-Logs in Echtzeit an den Browser."""
    async def generator():
        ping_counter = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                msg = _log_queue.get_nowait()
                safe = msg.replace("\n", " ").replace("\r", "")
                yield f"data: {safe}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.15)
                ping_counter += 1
                if ping_counter >= 20:      # alle ~3s ein Keep-Alive senden
                    yield ": ping\n\n"
                    ping_counter = 0

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",      # Nginx-Buffering deaktivieren (wichtig für Unraid)
        },
    )


# ── /api/ Router ──────────────────────────────────────────────────────────────
api = APIRouter(prefix="/api")


@api.post("/start", summary="Analyse starten", tags=["Analyse"],
          responses={
              200: {"description": "Analyse wurde erfolgreich gestartet", "content": {"application/json": {"example": {"status": "started"}}}},
              409: {"description": "Es läuft bereits eine Analyse", "content": {"application/json": {"example": {"error": "Analysis already running"}}}},
          })
async def api_start(req: StartRequest):
    """
    Startet eine neue Video-Qualitätsanalyse.

    - Im **Vergleichsmodus** werden Original und Encoded gegenübergestellt (VMAF, SSIM, PSNR, …)
    - Im **Solo-Modus** (`solo_mode: true`) wird nur das Encoded-Video analysiert — kein Original nötig

    Gibt `409` zurück wenn bereits eine Analyse läuft.
    Nach dem Start den Fortschritt über `/api/status` verfolgen.
    """
    return await start_analysis(req)


@api.post("/stop", summary="Analyse abbrechen", tags=["Analyse"],
          responses={
              200: {"content": {"application/json": {"examples": {
                  "gestoppt": {"value": {"status": "stopped"}},
                  "nicht aktiv": {"value": {"status": "not running"}},
              }}}},
          })
async def api_stop():
    """Bricht die aktuell laufende Analyse ab. Hat keine Auswirkung wenn keine Analyse läuft."""
    return await stop_analysis()


@api.get("/status", summary="Fortschritt & Status abfragen", tags=["Analyse"],
         response_model=JobStatus)
async def api_status():
    """
    Gibt den aktuellen Analyse-Status zurück.

    **`status`-Werte:**
    - `idle` — keine Analyse aktiv
    - `Starting...` — wird vorbereitet
    - `Running: 42.0%  |  Remaining: 01:23 min` — läuft
    - `Done` — abgeschlossen
    - `Aborted` — abgebrochen

    Sobald `status` == `Done`: Ergebnisse über `/api/results` abrufen.
    """
    return await get_status()


@api.get("/results", summary="Metriken als JSON abrufen", tags=["Analyse"],
         responses={
             200: {"description": "Ergebnisse der letzten Analyse", "content": {"application/json": {"examples": {
                 "Vergleichsanalyse": {"value": {"mode": "comparison", "vmaf_avg": 94.2, "vmaf_min": 81.5, "ssim": 0.98421, "psnr": 42.3, "report_url": "/reports/Report_20260322_120000.html"}},
                 "Solo-Scan": {"value": {"mode": "solo", "report_url": "/reports/Report_20260322_120000.html"}},
             }}}},
             404: {"description": "Noch keine Analyse durchgeführt"},
         })
async def api_results():
    """
    Gibt die Metriken der zuletzt abgeschlossenen Analyse als JSON zurück.

    **Vergleichsmodus** liefert:
    - `vmaf_avg` — VMAF-Durchschnitt (0–100, höher = besser)
    - `vmaf_min` — VMAF-Minimum (schlechteste Szene)
    - `ssim` — Strukturelle Ähnlichkeit (0–1, näher an 1 = besser)
    - `psnr` — Peak Signal-to-Noise Ratio in dB (höher = besser)
    - `report_url` — Link zum vollständigen HTML-Report

    **Solo-Modus** liefert nur `report_url`.

    Gibt `404` zurück wenn noch keine Analyse abgeschlossen wurde.
    """
    if job["results"] is None:
        return JSONResponse({"error": "Noch keine Ergebnisse verfügbar"}, status_code=404)
    return {**job["results"], "report_url": job["report_url"]}


@api.get("/reports/list", summary="Alle HTML-Reports auflisten", tags=["Dateien"],
         responses={200: {"content": {"application/json": {"example": {"reports": [{"name": "Report_20260322_120000.html", "url": "/reports/Report_20260322_120000.html"}]}}}}})
async def api_list_reports():
    """Gibt alle generierten HTML-Reports zurück, neueste zuerst. Der `url`-Wert kann direkt im Browser geöffnet werden."""
    return await list_reports()


@api.get("/screenshots/list", summary="Screenshots auflisten", tags=["Dateien"],
         responses={200: {"content": {"application/json": {"example": {"screenshots": [{"name": "frame_00001.jpg", "url": "/temp/screenshots/frame_00001.jpg"}]}}}}})
async def api_list_screenshots():
    """Gibt alle vorhandenen Frame-Screenshots zurück. Screenshots werden während der Analyse automatisch erstellt."""
    return await list_screenshots()


@api.get("/heatmaps/list", summary="Artefakt-Heatmaps auflisten", tags=["Dateien"],
         responses={200: {"content": {"application/json": {"example": {"heatmaps": [{"name": "heatmap.png", "url": "/temp/heatmaps/heatmap.png"}]}}}}})
async def api_list_heatmaps():
    """Gibt alle generierten Artefakt-Heatmaps zurück. Heatmaps zeigen wo im Video Kompressionsartefakte auftreten."""
    heatmaps_dir = DIRS["heatmaps"]
    try:
        files = sorted(
            [f for f in os.listdir(heatmaps_dir) if f.lower().endswith(".png")]
        )
        return {"heatmaps": [{"name": f, "url": f"/temp/heatmaps/{f}"} for f in files]}
    except Exception:
        return {"heatmaps": []}


@api.post("/queue/add", summary="Job zur Mehrfachanalyse hinzufügen", tags=["Mehrfachanalyse"],
          responses={
              200: {"content": {"application/json": {"example": {"id": 3, "status": "waiting", "position": 2}}}},
          })
async def api_queue_add(req: StartRequest):
    """
    Fügt einen neuen Analyse-Job zur Mehrfachanalyse hinzu.
    Er wird automatisch gestartet sobald alle vorherigen Jobs abgeschlossen sind.

    **Pfad-Mapping** wird automatisch angewendet wenn in den Einstellungen konfiguriert
    (z.B. `Z:\\film.mkv` → `/data/film.mkv`).

    Gibt die **Job-ID** zurück — damit kannst du den Status und die Ergebnisse später abrufen.
    """
    qs = _get_queue_settings()
    orig_path = _apply_path_mapping(req.orig_path, qs["path_from"], qs["path_to"])
    enco_path = _apply_path_mapping(req.enco_path, qs["path_from"], qs["path_to"])

    with _q_lock:
        jid = _next_qid()
        waiting_count = sum(1 for j in _q_jobs if j["status"] == "waiting")
        _q_jobs.append({
            "id":          jid,
            "status":      "waiting",
            "position":    waiting_count + 1,
            "orig_path":   orig_path,
            "enco_path":   enco_path,
            "metrics":     req.metrics,
            "solo_mode":   req.solo_mode,
            "subsample":   req.subsample,
            "offset_sec":  req.offset_sec,
            "art_frames":  req.art_frames,
            "dark_mode":   req.dark_mode,
            "added_at":    datetime.now().isoformat(timespec="seconds"),
            "started_at":  None,
            "finished_at": None,
            "results":     None,
            "report_url":  None,
            "error":       None,
        })
    return {"id": jid, "status": "waiting", "position": waiting_count + 1}


@api.get("/queue", summary="Mehrfachanalyse anzeigen", tags=["Mehrfachanalyse"],
         responses={200: {"content": {"application/json": {"example": {
             "jobs": [
                 {"id": 1, "status": "done",    "enco_path": "/data/film1.mp4", "added_at": "2026-03-22T12:00:00", "finished_at": "2026-03-22T12:05:00"},
                 {"id": 2, "status": "running", "enco_path": "/data/film2.mp4", "added_at": "2026-03-22T12:05:00", "finished_at": None},
                 {"id": 3, "status": "waiting", "enco_path": "/data/film3.mp4", "added_at": "2026-03-22T12:06:00", "finished_at": None},
             ],
             "summary": {"waiting": 1, "running": 1, "done": 1, "failed": 0},
         }}}}})
async def api_queue_list():
    """
    Zeigt alle Jobs in der Mehrfachanalyse — inkl. laufende und abgeschlossene.

    **Status-Werte:**
    - `waiting` — wartet auf Verarbeitung
    - `running` — wird gerade analysiert
    - `done` — abgeschlossen (Ergebnisse verfügbar)
    - `failed` — fehlgeschlagen
    """
    with _q_lock:
        jobs = list(_q_jobs)
    summary = {s: sum(1 for j in jobs if j["status"] == s)
               for s in ("waiting", "running", "done", "failed")}
    return {"jobs": jobs, "summary": summary}


@api.get("/queue/{job_id}/results", summary="Ergebnisse eines Jobs abrufen", tags=["Mehrfachanalyse"],
         responses={
             200: {"content": {"application/json": {"example": {"id": 1, "status": "done", "vmaf_avg": 94.2, "vmaf_min": 81.5, "ssim": 0.98421, "psnr": 42.3, "report_url": "/reports/Report_20260322_120000.html"}}}},
             404: {"description": "Job nicht gefunden"},
             425: {"description": "Job noch nicht abgeschlossen"},
         })
async def api_queue_job_results(job_id: int):
    """
    Gibt die Analyseergebnisse eines bestimmten Mehrfachanalysen-Jobs zurück.

    Nur verfügbar wenn `status` == `done`.
    """
    with _q_lock:
        match = next((j for j in _q_jobs if j["id"] == job_id), None)
    if match is None:
        return JSONResponse({"error": f"Job {job_id} nicht gefunden"}, status_code=404)
    if match["status"] != "done":
        return JSONResponse({"error": f"Job {job_id} ist noch nicht abgeschlossen (status: {match['status']})"}, status_code=425)
    result = {"id": match["id"], "status": match["status"], "report_url": match["report_url"]}
    if match["results"]:
        result.update(match["results"])
    return result


@api.delete("/queue/{job_id}", summary="Wartenden Job entfernen", tags=["Mehrfachanalyse"],
            responses={
                200: {"content": {"application/json": {"example": {"status": "removed", "id": 3}}}},
                404: {"description": "Job nicht gefunden"},
                409: {"description": "Job läuft bereits und kann nicht entfernt werden"},
            })
async def api_queue_remove(job_id: int):
    """
    Entfernt einen **wartenden** Job aus der Mehrfachanalyse.
    Laufende oder abgeschlossene Jobs können nicht entfernt werden.
    """
    with _q_lock:
        match = next((j for j in _q_jobs if j["id"] == job_id), None)
        if match is None:
            return JSONResponse({"error": f"Job {job_id} nicht gefunden"}, status_code=404)
        if match["status"] != "waiting":
            return JSONResponse({"error": f"Job {job_id} hat status '{match['status']}' und kann nicht entfernt werden"}, status_code=409)
        _q_jobs.remove(match)
    return {"status": "removed", "id": job_id}


@api.delete("/queue", summary="Abgeschlossene Jobs löschen", tags=["Mehrfachanalyse"],
            responses={200: {"content": {"application/json": {"example": {"cleared": 5}}}}})
async def api_queue_clear():
    """Entfernt alle **abgeschlossenen** (`done` und `failed`) Jobs aus der Liste. Laufende und wartende bleiben erhalten."""
    with _q_lock:
        before = len(_q_jobs)
        _q_jobs[:] = [j for j in _q_jobs if j["status"] in ("waiting", "running")]
        cleared = before - len(_q_jobs)
    return {"cleared": cleared}


@api.get("/settings", summary="Einstellungen laden", tags=["System"],
         responses={200: {"content": {"application/json": {"example": {
             "path_from": "Z:\\", "path_to": "/data/",
             "default_metrics": ["VMAF", "SSIM", "PSNR"],
             "default_subsample": 1, "default_art_frames": 1000, "default_dark_mode": True,
         }}}}})
async def api_get_settings():
    """Gibt die aktuellen Mehrfachanalysen-Einstellungen zurück (Pfad-Mapping, Standard-Metriken, etc.)."""
    return _get_queue_settings()


@api.post("/settings", summary="Einstellungen speichern", tags=["System"],
          responses={200: {"content": {"application/json": {"example": {"status": "saved"}}}}})
async def api_save_settings(settings: QueueSettings):
    """
    Speichert die Mehrfachanalysen-Einstellungen dauerhaft in `config.json`.

    **Pfad-Mapping:** Wenn `path_from` gesetzt ist, werden Pfade in `/api/queue/add` automatisch konvertiert.

    Beispiel: `path_from = Z:\\`, `path_to = /data/`
    → StaxRip sendet `Z:\\filme\\encoded.mp4` → wird zu `/data/filme/encoded.mp4`
    """
    cfg = _config_mgr.load()
    cfg["queue_settings"] = settings.model_dump()
    _config_mgr.save(cfg)
    return {"status": "saved"}


@api.get("/gpu", summary="GPU-Status abfragen", tags=["System"],
         responses={200: {"content": {"application/json": {"examples": {
             "Mit GPU": {"value": {"available": True, "name": "NVIDIA GeForce RTX 3080"}},
             "Ohne GPU": {"value": {"available": False, "name": "CPU"}},
         }}}}})
async def api_gpu():
    """
    Gibt zurück ob eine NVIDIA-GPU erkannt wurde und deren Namen.
    Falls keine GPU vorhanden: läuft die Analyse im CPU-Modus (langsamer).
    """
    return await gpu_info()


app.include_router(api)


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Video Quality Analyzer PRO  –  Web Edition")
    print("  http://0.0.0.0:2498")
    if GPU_AVAILABLE:
        print(f"  GPU: {GPU_NAME} (CUDA aktiv)")
    else:
        print("  GPU: Nicht gefunden – CPU-Modus")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=2498)
