import subprocess
import json
import os
import platform
from modules.ui.console_manager import console
from modules.path_utils import get_tool

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

class BitrateAnalyzer:
    def __init__(self):
        self.ffprobe_path = get_tool("ffprobe")

    def analyze(self, video_path):
        # WICHTIG: Rückgabe als Floats/Zahlen, nicht als Strings!
        results = {"avg_bitrate": 0.0, "peak_bitrate": 0.0, "profile": "Unknown"}
        
        try:
            cmd = [self.ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", video_path]
            
            process = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                encoding='utf-8', 
                errors='replace', 
                creationflags=CREATE_NO_WINDOW
            )
            
            if process.returncode != 0:
                console.print_error("FFprobe Fehler: Metadaten konnten nicht gelesen werden.")
                return results
                
            data = json.loads(process.stdout)
            
            # Dateigröße und Dauer für Durchschnittsberechnung
            size_bytes = os.path.getsize(video_path)
            duration = float(data.get("format", {}).get("duration", 1))
            
            # Berechnung in kbps
            avg_kbps = (size_bytes * 8) / duration / 1000
            results["avg_bitrate"] = round(float(avg_kbps), 2)

            # 2. Peak-Messung via Packet-Größen (Sekundenweise Aggregation)
            cmd_peak = [
                self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "packet=pts_time,size", "-of", "compact=p=0:nk=1", video_path
            ]
            
            proc = subprocess.Popen(
                cmd_peak, 
                stdout=subprocess.PIPE, 
                text=True, 
                encoding='utf-8', 
                errors='replace', 
                creationflags=CREATE_NO_WINDOW
            )
            
            max_bits, current_bits, last_sec = 0, 0, -1
            
            # Wir lesen den Stream zeilenweise, um Speicher zu sparen
            if proc.stdout:
                for line in proc.stdout:
                    parts = line.strip().split('|')
                    if len(parts) >= 2:
                        try:
                            # parts[0] ist pts_time, parts[1] ist size in Bytes
                            pts_raw = float(parts[0])
                            pts = int(pts_raw)
                            size = int(parts[1]) * 8 # Bytes zu Bits
                            
                            if pts == last_sec:
                                current_bits += size
                            else:
                                if current_bits > max_bits: 
                                    max_bits = current_bits
                                current_bits = size
                                last_sec = pts
                        except Exception:
                            continue
                
                proc.stdout.close()
            proc.wait()

            results["peak_bitrate"] = round(float(max_bits / 1000), 2)
            
            # Profil auslesen (z.B. Main 10, High, etc.)
            for s in data.get("streams", []):
                if s["codec_type"] == "video":
                    results["profile"] = s.get("profile", "Unknown")
                    break
            
            console.print_success(f"Analyse abgeschlossen: Peak {results['peak_bitrate']} kbps | Profil: {results['profile']}")
                    
        except Exception as e:
            console.print_error(f"Bitrate Analysis Error: {e}")
            
        return results

if __name__ == "__main__":
    pass