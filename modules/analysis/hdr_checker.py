import subprocess
import json
import os
import platform
from modules.path_utils import get_tool

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

class HDRChecker:
    def analyze(self, video_path, ffmpeg_path):
        # FIX: get_tool statt .replace("ffmpeg.exe", "ffprobe.exe") – funktioniert auf allen Plattformen
        ffprobe_path = get_tool("ffprobe")

        # Erweiterte Abfrage: Streams für Metadaten, Frames für Dolby Vision Side-Data
        cmd = [
            ffprobe_path, 
            "-v", "quiet", 
            "-print_format", "json", 
            "-show_streams", 
            "-show_frames", "-read_intervals", "%+#1", # Nur den ersten Frame für Speed
            video_path
        ]
        
        hdr_info = {
            "pix_fmt": "Unbekannt", 
            "is_hdr": "Nein", 
            "hdr_format": "SDR",
            "dv_profile": "Keines",
            "bit_depth": 8
        }

        try:
            out = subprocess.check_output(
                cmd,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=CREATE_NO_WINDOW,
                timeout=30
            )
            data = json.loads(out)
            
            # 1. Stream-Analyse (Basis HDR & Bit-Tiefe)
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    pix = s.get("pix_fmt", "N/A")
                    hdr_info["pix_fmt"] = pix
                    
                    # Bit-Tiefe erkennen (wichtig für HDR-Indikation)
                    if "10le" in pix or "10be" in pix:
                        hdr_info["bit_depth"] = 10
                    elif "12le" in pix or "12be" in pix:
                        hdr_info["bit_depth"] = 12

                    transfer = s.get("color_transfer", "").lower()
                    primaries = s.get("color_primaries", "").lower()

                    # Erkennung basierend auf Transfer-Charakteristik oder Farbraum
                    if "smpte2084" in transfer or "st2084" in transfer:
                        hdr_info["is_hdr"] = "Ja"
                        hdr_info["hdr_format"] = "HDR10 / PQ"
                    elif "arib-std-b67" in transfer or "hlg" in transfer:
                        hdr_info["is_hdr"] = "Ja"
                        hdr_info["hdr_format"] = "HLG"
                    elif "bt2020" in primaries and hdr_info["bit_depth"] >= 10:
                        # Fallback: Wenn BT2020 und 10-Bit, ist es meist HDR, auch wenn Transfer-Tag fehlt
                        hdr_info["is_hdr"] = "Ja"
                        hdr_info["hdr_format"] = "HDR (BT.2020)"

            # 2. Frame-Analyse für Dolby Vision (Side-Data)
            for f in data.get("frames", []):
                for side in f.get("side_data_list", []):
                    stype = side.get("side_data_type", "")
                    if "DOVI" in stype or "Dolby Vision" in stype:
                        hdr_info["is_hdr"] = "Ja"
                        dv_p = side.get("dv_profile", "DV")
                        hdr_info["dv_profile"] = f"Profil {dv_p}"
                        
                        # Format-String ergänzen
                        if hdr_info["hdr_format"] == "SDR":
                            hdr_info["hdr_format"] = f"Dolby Vision (P{dv_p})"
                        else:
                            hdr_info["hdr_format"] = f"Dolby Vision + {hdr_info['hdr_format']}"

        except Exception as e:
            print(f"HDR/DV Check Error: {e}")
            
        return hdr_info

if __name__ == "__main__":
    pass