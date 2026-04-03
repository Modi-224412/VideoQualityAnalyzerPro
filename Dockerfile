# ── Stage 1: Statisches FFmpeg mit libvmaf ────────────────────────────────────
FROM mwader/static-ffmpeg:7.1 AS ffmpeg-stage

# ── Stage 2: Python App ───────────────────────────────────────────────────────
FROM python:3.12-slim

# System-Bibliotheken für OpenCV (headless)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# FFmpeg + FFprobe (mit libvmaf) aus Stage 1 kopieren
COPY --from=ffmpeg-stage /ffmpeg  /usr/local/bin/ffmpeg
COPY --from=ffmpeg-stage /ffprobe /usr/local/bin/ffprobe

WORKDIR /app

# Abhängigkeiten zuerst (Docker-Cache-Optimierung)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Projektdateien kopieren
COPY . .

# Ausgabe-Verzeichnisse anlegen
RUN mkdir -p reports temp/graphs temp/heatmaps temp/screenshots uploads

EXPOSE 2498

CMD ["python3", "web_app.py"]
