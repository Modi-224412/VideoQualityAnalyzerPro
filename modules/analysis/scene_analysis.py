import json
import os
import subprocess
import platform

from modules.path_utils import get_tool

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

class SceneAnalyzer:
    def __init__(self):
        self.threshold = 70.0  # Alles unter 70 VMAF gilt als "kritisch"

    def _get_fps_via_ffprobe(self, video_path):
        """
        Holt FPS sicher über ffprobe ohne externe Abhängigkeit.
        """
        try:
            ffprobe_path = get_tool("ffprobe")

            cmd = [
                ffprobe_path,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate",
                "-of", "csv=p=0",
                video_path
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=CREATE_NO_WINDOW
            )
            # r_frame_rate kommt als "num/den" z.B. "60000/1001"
            rate = result.stdout.strip()
            if "/" in rate:
                num, den = rate.split("/")
                fps = float(num) / float(den)
                if fps > 0:
                    return fps
        except Exception as e:
            print(f"FPS Erkennung fehlgeschlagen: {e}")
        return 24.0  # Sicherer Fallback

    def get_worst_scenes(self, vmaf_log_path, video_path, limit=5):
        """
        Analysiert das VMAF-Log und gibt die 'limit' schlechtesten Szenen zurück,
        die den Schwellenwert unterschreiten.
        """
        return self._process_log(vmaf_log_path, video_path, limit, use_threshold=True)

    def get_absolute_worst_frames(self, vmaf_log_path, video_path, limit=3):
        """
        Fall-back: Ignoriert den Threshold und gibt einfach die 3 schlechtesten Frames zurück.
        """
        return self._process_log(vmaf_log_path, video_path, limit, use_threshold=False)

    def _process_log(self, vmaf_log_path, video_path, limit, use_threshold=False):
        if not os.path.exists(vmaf_log_path):
            print(f"Fehler: Logdatei nicht gefunden unter {vmaf_log_path}")
            return []

        try:
            with open(vmaf_log_path, 'r', encoding='utf-8', errors='replace') as f:
                data = json.load(f)

            frames_data = data.get("frames", [])
            if not frames_data:
                print("Fehler: Keine Frame-Daten in der VMAF-JSON gefunden.")
                return []

            # FIX: Erste 30 Frames ignorieren (libvmaf Einschwingartefakte)
            # und Frames mit VMAF=0 komplett ausschließen
            WARMUP_FRAMES = 30
            fps = self._get_fps_via_ffprobe(video_path)

            scored_frames = []
            for i, f in enumerate(frames_data):
                score = f.get("metrics", {}).get("vmaf")
                if score is None:
                    continue

                f_num = f.get("frameNum", i)

                # FIX: Warmup-Frames und VMAF=0 ausschließen
                if f_num < WARMUP_FRAMES:
                    continue
                if score <= 0.0:
                    continue

                if use_threshold and score > self.threshold:
                    continue

                timestamp = f_num / fps
                scored_frames.append({
                    "frame": f_num,
                    "score": score,
                    "timestamp": timestamp
                })

            if not scored_frames and not use_threshold:
                return []

            sorted_frames = sorted(scored_frames, key=lambda x: x["score"])

            worst_scenes = []
            seen_times = []

            min_dist = 2.0 if len(scored_frames) > 20 else 0.5

            for entry in sorted_frames:
                if any(abs(entry["timestamp"] - t) < min_dist for t in seen_times):
                    continue

                worst_scenes.append({
                    "vmaf": round(entry["score"], 2),
                    "timestamp_fmt": self._format_timestamp(entry["timestamp"]),
                    "timestamp_raw": entry["timestamp"],
                    "frame": entry["frame"]
                })
                seen_times.append(entry["timestamp"])

                if len(worst_scenes) >= limit:
                    break

            worst_scenes.sort(key=lambda x: x["timestamp_raw"])

            if worst_scenes:
                print(f"Scene Analysis: Found {len(worst_scenes)} candidate frames.")

            return worst_scenes

        except Exception as e:
            print(f"Scene Analysis Error: {e}")
            return []

    def _format_timestamp(self, seconds):
        """Konvertiert Sekunden in MM:SS Format."""
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

if __name__ == "__main__":
    pass