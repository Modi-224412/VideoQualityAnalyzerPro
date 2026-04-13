import json
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from modules.ui.console_manager import console
from modules.path_utils import APP_PATH

app_path = APP_PATH

class ArtifactHeatmapGenerator:
    def __init__(self, ffmpeg_path=None):
        self.ffmpeg_path = ffmpeg_path

    def generate(self, vmaf_log_path, dark_mode=True, fps=None):
        """
        Generiert eine visuelle Heatmap basierend auf CAMBI oder VMAF-Scores.

        Args:
            vmaf_log_path: Pfad zur vmaf.json
            dark_mode: True für dunklen Hintergrund
            fps: Framerate für Zeitachse – falls None wird Frame-Nummer genutzt
        """
        heatmap_dir = os.path.join(app_path, "temp", "heatmaps")
        os.makedirs(heatmap_dir, exist_ok=True)
        output_path = os.path.join(heatmap_dir, "heatmap_latest.png")

        if not vmaf_log_path or not os.path.exists(vmaf_log_path):
            console.print_error("Heatmap Fehler: VMAF Log-Datei nicht gefunden.")
            return "N/A"

        try:
            with open(vmaf_log_path, 'rb') as f:
                data = json.loads(f.read().decode('utf-8', errors='replace'))

            frames = data.get("frames", [])
            if not frames:
                console.print_warning("Heatmap: Keine Frame-Daten im Log gefunden.")
                return "N/A"

            # FPS aus Log lesen falls nicht übergeben
            if fps is None:
                fps = data.get("fps") or data.get("pooled_metrics", {}).get("fps")

            frame_numbers = []
            scores = []
            for i, f in enumerate(frames):
                metrics = f.get("metrics", {})
                val = metrics.get("cambi")
                if val is None:
                    val = 100 - metrics.get("vmaf", 100)
                frame_numbers.append(f.get("frameNum", i))
                scores.append(val)

            scores_arr = np.array(scores)
            max_score  = float(np.max(scores_arr))
            avg_score  = float(np.mean(scores_arr))

            # Threshold: 1.5× Durchschnitt, mindestens 10
            threshold = max(avg_score * 1.5, 10.0)

            # X-Achse: Sekunden/Minuten wenn FPS bekannt
            try:
                fps_val = float(fps) if fps else None
            except (TypeError, ValueError):
                fps_val = None

            if fps_val and fps_val > 0:
                x_values = [n / fps_val for n in frame_numbers]
                x_label  = "Zeit (s)"
                total    = x_values[-1] if x_values else 0
                if total >= 90:
                    x_values = [v / 60 for v in x_values]
                    x_label  = "Zeit (min)"
            else:
                x_values = frame_numbers
                x_label  = "Frame"

            # Theme-Farben
            bg_color   = '#1e1e1e' if dark_mode else '#ffffff'
            text_color = '#f0f0f0' if dark_mode else '#2c3e50'
            dim_color  = '#888888'

            if dark_mode:
                plt.style.use('dark_background')
            else:
                plt.style.use('default')

            fig, ax = plt.subplots(figsize=(14, 3.5), facecolor=bg_color)
            ax.set_facecolor(bg_color)

            data_array = scores_arr.reshape(1, -1)
            img = ax.imshow(
                data_array, aspect='auto', cmap='magma',
                interpolation='nearest',
                extent=[x_values[0], x_values[-1], 0, 1]
            )

            # Threshold-Linie (als vertikale Markierung im Colorbar-Bereich)
            # Normierter Threshold-Wert für axvline nicht sinnvoll → als Text-Annotation
            # Stattdessen: schlechteste Stelle markieren
            worst_idx   = int(np.argmax(scores_arr))
            worst_x     = x_values[worst_idx]
            worst_score = scores_arr[worst_idx]

            ax.axvline(x=worst_x, color='#e74c3c', linewidth=1.2, linestyle='--', alpha=0.85)
            ax.text(worst_x, 0.98, f'Max: {worst_score:.1f}',
                    color='#e74c3c', fontsize=7, va='top', ha='center',
                    transform=ax.get_xaxis_transform())

            ax.set_title("Artefakt & Banding Intensität (Timeline)",
                         color=text_color, fontsize=11, pad=10)
            ax.set_xlabel(x_label, color=dim_color, fontsize=8)
            ax.set_yticks([])
            ax.tick_params(axis='x', colors=dim_color, labelsize=7)
            for spine in ax.spines.values():
                spine.set_visible(False)

            # Colorbar
            cbar = fig.colorbar(img, orientation='vertical', pad=0.02)
            cbar.outline.set_visible(False)
            cbar.ax.tick_params(labelsize=7, colors=dim_color)
            cbar.set_label('Intensität', color=dim_color, fontsize=8)

            # Threshold-Linie in Colorbar
            norm_threshold = threshold / max_score if max_score > 0 else 0.5
            cbar.ax.axhline(y=norm_threshold * cbar.ax.get_ylim()[1],
                            color='#f1c40f', linewidth=1.0, linestyle='--')

            # Info-Zeile unten
            info = f"Ø {avg_score:.1f}  |  Max {worst_score:.1f}  |  Threshold {threshold:.1f}"
            fig.text(0.5, 0.01, info, ha='center', va='bottom',
                     fontsize=7, color=dim_color)

            plt.tight_layout(rect=[0, 0.05, 1, 1])
            plt.savefig(output_path, dpi=150, facecolor=bg_color)
            plt.close()

            console.print_success(f"Heatmap erfolgreich erstellt: {os.path.basename(output_path)}")
            return output_path

        except Exception as e:
            console.print_error(f"Heatmap Generation Error: {e}")
            return "N/A"
