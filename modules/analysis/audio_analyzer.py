import subprocess
import json
import platform
from modules.path_utils import get_tool
from modules.ui.console_manager import console

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


class AudioAnalyzer:
    def __init__(self):
        self.ffprobe_path = get_tool("ffprobe")

    def _analyze_single(self, video_path):
        """Analysiert den Audio-Stream einer einzelnen Videodatei via ffprobe."""
        result = {
            "has_audio":      False,
            "codec":          "N/A",
            "sample_rate":    "N/A",
            "channels":       0,
            "channel_layout": "N/A",
            "bitrate_kbps":   0.0,
            "bit_depth":      "N/A",
            "stream_count":   0,
            "status":         "Kein Audio-Stream gefunden",
        }

        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "a",
                video_path,
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
            data = json.loads(proc.stdout)
            streams = data.get("streams", [])

            if not streams:
                return result

            s = streams[0]
            result["has_audio"]    = True
            result["stream_count"] = len(streams)
            result["codec"]        = s.get("codec_name", "N/A").upper()
            result["sample_rate"]  = s.get("sample_rate", "N/A")
            result["channels"]     = int(s.get("channels", 0))

            # Channel-Layout: bevorzuge den gespeicherten Wert, sonst ableiten
            layout = s.get("channel_layout", "")
            if not layout:
                ch = result["channels"]
                if ch == 1:
                    layout = "mono"
                elif ch == 2:
                    layout = "stereo"
                elif ch == 6:
                    layout = "5.1"
                elif ch == 8:
                    layout = "7.1"
                else:
                    layout = f"{ch} Kanäle"
            result["channel_layout"] = layout

            # Bit-Tiefe (nicht immer vorhanden)
            bd = s.get("bits_per_raw_sample") or s.get("bits_per_sample")
            result["bit_depth"] = str(bd) + " Bit" if bd else "N/A"

            # Bitrate aus Stream-Tag oder Format-Bitrate
            br_str = s.get("bit_rate")
            if br_str:
                result["bitrate_kbps"] = round(int(br_str) / 1000, 1)

            result["status"] = (
                f"✅ {result['codec']} | "
                f"{result['sample_rate']} Hz | "
                f"{result['channel_layout']}"
            )

        except Exception as e:
            result["status"] = f"❌ Fehler: {e}"
            console.print_error(f"Audio-Analyse Fehler: {e}")

        return result

    def compare(self, orig_path, enco_path):
        """
        Analysiert Audio beider Dateien und vergleicht sie.
        Gibt ein Dict mit orig, enco, issues und summary zurück.
        """
        console.print_info("Audio-Analyse: Starte Prüfung...")

        orig = self._analyze_single(orig_path)
        enco = self._analyze_single(enco_path)

        issues = []

        if orig["has_audio"] and not enco["has_audio"]:
            issues.append("❌ Audio-Stream fehlt im Encoded-Video!")
        elif orig["has_audio"] and enco["has_audio"]:
            # Kanäle
            if orig["channels"] != enco["channels"] and orig["channels"] > 0:
                issues.append(
                    f"⚠️ Kanal-Änderung: {orig['channel_layout']} → {enco['channel_layout']}"
                )
            # Sample Rate
            if orig["sample_rate"] != enco["sample_rate"] and orig["sample_rate"] != "N/A":
                issues.append(
                    f"⚠️ Sample-Rate geändert: {orig['sample_rate']} → {enco['sample_rate']} Hz"
                )
            # Bitrate-Verlust (nur wenn beide bekannt und > 0)
            if orig["bitrate_kbps"] > 0 and enco["bitrate_kbps"] > 0:
                drop_pct = (orig["bitrate_kbps"] - enco["bitrate_kbps"]) / orig["bitrate_kbps"]
                if drop_pct > 0.5:
                    issues.append(
                        f"⚠️ Starker Audio-Bitratedrop: "
                        f"{orig['bitrate_kbps']:.0f} → {enco['bitrate_kbps']:.0f} kbps"
                    )
        elif not orig["has_audio"] and not enco["has_audio"]:
            issues.append("ℹ️ Beide Dateien haben keinen Audio-Stream.")

        if not issues:
            summary = "✅ Audio unauffällig – keine Probleme erkannt"
        else:
            summary = " | ".join(issues)

        console.print_success(f"Audio-Analyse abgeschlossen: {summary}")

        return {
            "original": orig,
            "encoded":  enco,
            "issues":   issues,
            "summary":  summary,
        }


if __name__ == "__main__":
    pass
