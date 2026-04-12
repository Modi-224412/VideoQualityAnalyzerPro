import subprocess
import re
import platform
import sys
from modules.ui.console_manager import console
from modules.path_utils import get_tool

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

class ArtifactDetector:
    def __init__(self, ffmpeg_path=None):
        self.ffmpeg_path = ffmpeg_path if ffmpeg_path else get_tool("ffmpeg")
        self.ffprobe_path = get_tool("ffprobe")

    def _get_total_frames(self, video_path):
        """
        Ermittelt die Gesamtframe-Anzahl für den Ladebalken.
        Methode 1: nb_frames aus Stream-Metadaten (schnell, aber bei MKV/HEVC oft leer).
        Methode 2: Fallback via Dauer × FPS (zuverlässig für alle Container).
        """
        try:
            # Methode 1: nb_frames direkt aus Metadaten
            result = subprocess.run(
                [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=nb_frames", "-of", "csv=p=0", video_path],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
            )
            val = result.stdout.strip()
            if val.isdigit() and int(val) > 0:
                return int(val)
        except Exception:
            pass

        try:
            # Methode 2: Dauer × FPS berechnen
            result = subprocess.run(
                [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=r_frame_rate,duration",
                 "-of", "csv=p=0", video_path],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
            )
            # Ausgabe: "30000/1001,600.600600" oder "25/1,120.0"
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                fps_raw, dur_raw = parts[0], parts[1]
                if "/" in fps_raw:
                    num, den = fps_raw.split("/")
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_raw)
                duration = float(dur_raw)
                if fps > 0 and duration > 0:
                    return int(fps * duration)
        except Exception:
            pass

        return 0

    def detect(self, video_path, max_frames=1000, on_progress=None, stop_event=None):
        """
        on_progress:  optionaler Callback(done: int, total: int) für Live-Fortschritt.
        stop_event:   optionales threading.Event – wird es gesetzt, bricht der Scan ab.
        """
        total_expected = self._get_total_frames(video_path)
        # Falls max_frames gesetzt ist, ist das unser Ziel für den Ladebalken
        if max_frames > 0:
            total_expected = min(total_expected, max_frames) if total_expected > 0 else max_frames

        frames_label = "alle Frames" if max_frames == 0 else f"{max_frames} Frames"
        console.print_info(f"Artifact Scan: Starte Analyse ({frames_label})...")

        results = {
            "total_count": 0,
            "blockiness":  0.0,
            "blocking":    False,
            "result":      "Keine signifikanten Artefakte gefunden"
        }

        # FFmpeg Kommando
        # Kein -hwaccel: blockdetect ist ein CPU-Filter; D3D11VA/DXVA2-Hardware-Frames
        # sind nicht direkt mit Software-Filtern kompatibel und führen zu Fehlern auf AMD.
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel", "verbose",
            "-i", video_path,
            "-vf", "scale=1280:-1:flags=bicubic,format=yuv420p,blockdetect",
        ]
        if max_frames > 0:
            cmd += ["-frames:v", str(max_frames)]
        cmd += ["-an", "-f", "null", "-"]

        scores = []
        
        try:
            # Popen verwenden, um stderr live zu lesen (blockdetect schreibt in stderr)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=CREATE_NO_WINDOW
            )

            for line in process.stderr:
                if stop_event and stop_event.is_set():
                    process.kill()
                    console.print_warning("Artefakt-Scan abgebrochen.")
                    return results

                match = re.search(r"block:\s+(\d+\.?\d*)", line, re.IGNORECASE)
                if match:
                    val = float(match.group(1))
                    scores.append(val)

                    current_count = len(scores)
                    prog_total = max_frames if max_frames > 0 else total_expected
                    if on_progress and current_count % 50 == 0 and prog_total > 0:
                        on_progress(current_count, prog_total)

            process.wait()

            if on_progress:
                prog_total = max_frames if max_frames > 0 else (total_expected or len(scores))
                on_progress(prog_total, prog_total)

            if scores:
                avg_block = sum(scores) / len(scores)
                results["blockiness"] = round(avg_block, 4)

                THRESH_PER_FRAME = 3.5
                THRESH_WARN      = 3.0
                THRESH_CRITICAL  = 4.5

                results["total_count"] = sum(1 for s in scores if s > THRESH_PER_FRAME)

                if avg_block >= THRESH_CRITICAL:
                    results["blocking"] = True
                    results["result"] = f"❌ Starkes Blocking (Ø Score: {results['blockiness']})"
                elif avg_block >= THRESH_WARN:
                    results["blocking"] = True
                    results["result"] = f"⚠️ Leichte Blocking-Tendenz (Ø Score: {results['blockiness']})"
                else:
                    results["result"] = f"✅ Unauffällig (Ø Block-Score: {results['blockiness']})"
                
                console.print_success(f"Artifact Scan abgeschlossen: {results['result']}")
            else:
                # Falls blockdetect fehlschlägt, Fallback ohne Ladebalken (da meist kurz)
                console.print_info("blockdetect lieferte keine Werte – versuche blurdetect...")
                results = self._fallback_blurdetect(video_path, results)

        except Exception as e:
            if 'process' in locals():
                process.kill()
            results["result"] = f"❌ Fehler: {e}"
            console.print_error(f"Artifact Detection Fehler: {e}")

        return results

    def _fallback_blurdetect(self, video_path, results):
        """Einfacher Fallback-Scan."""
        try:
            cmd = [
                self.ffmpeg_path, "-hide_banner", "-loglevel", "verbose",
                "-i", video_path, "-vf", "scale=1280:-1:flags=bicubic,format=yuv420p,blurdetect=high=0.1:low=0.05",
                "-frames:v", "500", "-an", "-f", "null", "-"
            ]
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', creationflags=CREATE_NO_WINDOW, timeout=300)
            blur_matches = re.findall(r"blur(?:\s+mean)?[:\s]+(\d+\.?\d*)", process.stderr, re.IGNORECASE)
            if blur_matches:
                scores = [float(m) for m in blur_matches]
                results["blockiness"] = round(sum(scores)/len(scores), 4)
                results["result"] = f"✅ Scan via Blur-Fallback (Ø Blur: {results['blockiness']})"
            return results
        except Exception:
            return results