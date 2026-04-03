import subprocess
import os
import platform
from modules.path_utils import get_tool

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

class ScreenshotTool:
    def __init__(self, ffmpeg_path=None):
        self.ffmpeg_path = ffmpeg_path if ffmpeg_path else get_tool("ffmpeg")

    def extract_frame(self, video_path, frame_number, output_path, fallback_timestamp=None):
        """
        Extrahiert ein spezifisches Frame basierend auf der Frame-Nummer.
        FIX: Bei Fehlschlag wird automatisch extract_by_timestamp als Fallback aufgerufen.
        """
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            cmd = [
                self.ffmpeg_path,
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", video_path,
                "-vf", f"select=eq(n\\,{int(frame_number)})",
                "-frames:v", "1",
                "-vsync", "0",
                "-q:v", "2",
                output_path
            ]

            subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=120)

            # FIX: Echter Fallback statt leerem pass-Block
            if not os.path.exists(output_path):
                if fallback_timestamp is not None:
                    return self.extract_by_timestamp(video_path, fallback_timestamp, output_path)
                else:
                    # Timestamp aus Frame-Nummer schätzen (Annahme 24fps als letzter Ausweg)
                    estimated_ts = frame_number / 24.0
                    return self.extract_by_timestamp(video_path, estimated_ts, output_path)

            return True

        except Exception as e:
            print(f"Screenshot Error: {e}")
            # Auch bei Exception noch Fallback versuchen
            if fallback_timestamp is not None:
                return self.extract_by_timestamp(video_path, fallback_timestamp, output_path)
            return False

    def extract_by_timestamp(self, video_path, timestamp, output_path):
        """
        Fallback-Methode: Extraktion via Zeitstempel (Sekunden).
        Schneller und robuster als Frame-genaue Selektion.
        """
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            cmd = [
                self.ffmpeg_path,
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-ss", str(timestamp),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                output_path
            ]
            subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=120)
            return os.path.exists(output_path)
        except Exception as e:
            print(f"Timestamp Screenshot Error: {e}")
            return False

if __name__ == "__main__":
    pass