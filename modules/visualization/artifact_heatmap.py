import json
import os
import matplotlib.pyplot as plt
import numpy as np
from modules.ui.console_manager import console
from modules.path_utils import APP_PATH

app_path = APP_PATH

class ArtifactHeatmapGenerator:
    def __init__(self, ffmpeg_path=None):
        self.ffmpeg_path = ffmpeg_path

    def generate(self, vmaf_log_path):
        """
        Generiert eine visuelle Heatmap basierend auf CAMBI oder VMAF-Scores aus dem Log.
        """
        heatmap_dir = os.path.join(app_path, "temp", "heatmaps")
        os.makedirs(heatmap_dir, exist_ok=True)
        output_path = os.path.join(heatmap_dir, "heatmap_latest.png")

        if not vmaf_log_path or not os.path.exists(vmaf_log_path):
            console.print_error("Heatmap Fehler: VMAF Log-Datei nicht gefunden.")
            return "N/A"

        try:
            # Robuster Load: Liest Bytes und ersetzt ungültige Zeichen
            with open(vmaf_log_path, 'rb') as f:
                raw_data = f.read()
                decoded_data = raw_data.decode('utf-8', errors='replace')
                data = json.loads(decoded_data)

            frames = data.get("frames", [])
            if not frames:
                console.print_warning("Heatmap: Keine Frame-Daten im Log gefunden.")
                return "N/A"

            scores = []
            for f in frames:
                metrics = f.get("metrics", {})
                # CAMBI ist ideal für Banding/Artefakte
                val = metrics.get("cambi")
                if val is None:
                    # Fallback: Invertierter VMAF (niedriger VMAF = hohe Artefakt-Dichte)
                    val = 100 - metrics.get("vmaf", 100)
                scores.append(val)

            # --- Visualisierung im Dark-Style ---
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(12, 2.5), facecolor='#1e1e1e')
            ax.set_facecolor('#1e1e1e')
            
            data_array = np.array(scores).reshape(1, -1)
            
            # Interpolation 'nearest' verhindert verwaschene Ergebnisse bei langen Videos
            img = ax.imshow(data_array, aspect='auto', cmap='magma', interpolation='nearest')
            
            ax.set_title("Artifact & Banding Intensity (Timeline)", color='#2ecc71', fontsize=10, pad=10)
            ax.set_xlabel("Frames", color='#888888', fontsize=8)
            ax.set_yticks([]) # Keine Y-Achse nötig für 1D Heatmap
            
            # Colorbar Styling
            cbar = fig.colorbar(img, orientation='vertical', pad=0.02)
            cbar.outline.set_visible(False)
            cbar.ax.tick_params(labelsize=7, colors='#888888')
            cbar.set_label('Intensity', color='#888888', fontsize=8)

            plt.tight_layout()
            plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor())
            plt.close()

            console.print_success(f"Heatmap erfolgreich erstellt: {os.path.basename(output_path)}")
            return output_path

        except Exception as e:
            console.print_error(f"Heatmap Generation Error: {e}")
            return "N/A"