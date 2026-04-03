import subprocess
import platform
import sys
from collections import Counter
from modules.path_utils import get_tool
from modules.ui.console_manager import console

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

def get_total_frames(ffprobe_path, file_path):
    """Holt die Gesamtzahl der Frames – nb_frames zuerst, dann duration×FPS als Fallback."""
    # Methode 1: nb_frames Metadaten
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=nb_frames", "-of", "csv=p=0", file_path],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
        )
        val = result.stdout.strip()
        if val.isdigit() and int(val) > 0:
            return int(val)
    except Exception:
        pass
    # Methode 2: duration × FPS
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate,duration", "-of", "csv=p=0", file_path],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
        )
        parts = result.stdout.strip().split(",")
        if len(parts) >= 2:
            fps_raw, dur_raw = parts[0], parts[1]
            fps = float(fps_raw.split("/")[0]) / float(fps_raw.split("/")[1]) if "/" in fps_raw else float(fps_raw)
            duration = float(dur_raw)
            if fps > 0 and duration > 0:
                return int(fps * duration)
    except Exception:
        pass
    return 0

def detect_frame_drops(ffmpeg_path, file_path, label="Video", on_progress=None):
    """
    Erkennt Frame-Drops und Duplikate durch Stream-Processing der Timestamps.
    Inklusive Live-Prozent-Ladebalken.
    """
    ffprobe_path = get_tool("ffprobe")
    
    # 1. Gesamtzahl ermitteln
    total_expected = get_total_frames(ffprobe_path, file_path)

    cmd = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time",
        "-of", "csv=p=0",
        file_path
    ]

    timestamps = []
    frame_count = 0
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=CREATE_NO_WINDOW
        )

        # Zeilenweise auslesen für Stabilität und Fortschritt
        for line in process.stdout:
            line = line.strip()
            if line and line != "N/A":
                try:
                    val = float(line.split(",")[0])
                    timestamps.append(val)
                    frame_count += 1
                    
                    if on_progress and (frame_count % 500 == 0 or frame_count == total_expected):
                        on_progress(frame_count, total_expected)
                except (ValueError, IndexError):
                    continue
        
        process.wait()

        if not timestamps:
            return {
                "drops": 0, "duplicates": 0,
                "total_frames": 0, "status": "Keine Frame-Daten gefunden"
            }

        total_frames = len(timestamps)

        # Deltas zwischen aufeinanderfolgenden Frames berechnen
        deltas = [
            timestamps[i + 1] - timestamps[i]
            for i in range(len(timestamps) - 1)
            if timestamps[i + 1] - timestamps[i] > 0
        ]

        if not deltas:
            return {
                "drops": 0, "duplicates": 0,
                "total_frames": total_frames,
                "status": "Keine verwertbaren Timestamp-Deltas"
            }

        # Modus: häufigster Delta-Wert
        rounded = [round(d, 4) for d in deltas]
        mode_counts = Counter(rounded).most_common(1)
        mode_delta = mode_counts[0][0]

        if mode_delta <= 0:
            sorted_d = sorted(deltas)
            mode_delta = sorted_d[len(sorted_d) // 2]

        drops = 0
        duplicates = 0

        for d in deltas:
            ratio = d / mode_delta
            if ratio > 1.8:
                drops += max(1, round(ratio) - 1)
            elif ratio < 0.35:
                duplicates += 1

        # Bewertung des Ergebnisses
        if drops == 0 and duplicates == 0:
            status = "✅ Keine Frame-Drops erkannt"
        elif drops <= 2:
            status = f"⚠️ Vereinzelte Frame-Drops ({drops}x) – unkritisch"
        elif drops <= 10:
            status = f"⚠️ Leichte Frame-Drops ({drops}x)"
        else:
            status = f"❌ Kritische Frame-Drops ({drops}x)"

        return {
            "drops": drops,
            "duplicates": duplicates,
            "total_frames": total_frames,
            "status": status
        }

    except Exception as e:
        if 'process' in locals():
            process.kill()
        return {
            "drops": 0, "duplicates": 0,
            "total_frames": 0, "status": f"Fehler: {e}"
        }