import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import json
import os

from modules.path_utils import APP_PATH

def create_vmaf_graph(log_path=None, dark_mode=False, fps=None):
    """
    Erstellt einen VMAF-Zeitverlauf-Graph aus dem VMAF JSON-Log.

    Args:
        log_path: Pfad zur vmaf.json – falls None wird Standard-Pfad genutzt
        dark_mode: True für dunklen Hintergrund
        fps: Frames pro Sekunde für Zeitachse – falls None wird Frame-Nummer genutzt
    Returns:
        Pfad zum gespeicherten Graph oder leerer String bei Fehler
    """
    if log_path is None:
        log_path = os.path.join(APP_PATH, "temp", "vmaf.json")

    if not os.path.exists(log_path):
        print(f"VMAF Graph: Log nicht gefunden unter {log_path}")
        return ""

    graph_dir = os.path.join(APP_PATH, "temp", "graphs")
    os.makedirs(graph_dir, exist_ok=True)
    output_path = os.path.join(graph_dir, "vmaf_graph.png")

    try:
        with open(log_path, "r", encoding='utf-8', errors='replace') as f:
            data = json.load(f)

        frames = data.get("frames", [])
        if not frames:
            print("VMAF Graph: Keine Frame-Daten im Log.")
            return ""

        # FPS aus Log lesen falls nicht übergeben
        if fps is None:
            fps = data.get("fps") or data.get("pooled_metrics", {}).get("fps")

        frame_numbers = []
        vmaf_scores   = []
        for i, f in enumerate(frames):
            score = f.get("metrics", {}).get("vmaf")
            frame_numbers.append(f.get("frameNum", i))
            vmaf_scores.append(float('nan') if (score is None or score < 2.0) else score)

        valid_scores = [s for s in vmaf_scores if s == s]
        if not valid_scores:
            print("VMAF Graph: Keine gültigen VMAF-Werte im Log.")
            return ""

        # X-Achse: Sekunden wenn FPS bekannt
        try:
            fps_val = float(fps) if fps else None
        except (TypeError, ValueError):
            fps_val = None

        if fps_val and fps_val > 0:
            x_values = [n / fps_val for n in frame_numbers]
            x_label  = "Zeit (s)"
            total_sec = x_values[-1] if x_values else 0
            # Minuten-Format ab 90 Sekunden
            if total_sec >= 90:
                x_values = [v / 60 for v in x_values]
                x_label  = "Zeit (min)"
        else:
            x_values = frame_numbers
            x_label  = "Frame"

        # Theme-Farben
        bg_color   = '#1e1e1e' if dark_mode else '#ffffff'
        grid_color = '#444444' if dark_mode else '#dddddd'
        text_color = '#f0f0f0' if dark_mode else '#2c3e50'
        line_color = '#3498db'

        fig, ax = plt.subplots(figsize=(14, 5), facecolor=bg_color)
        ax.set_facecolor(bg_color)

        x_min = min(x_values) if x_values else 0
        x_max = max(x_values) if x_values else 1

        # Qualitätszonen (Hintergrundbereiche)
        zone_alpha = 0.07 if dark_mode else 0.10
        ax.axhspan(90, 100, color='#2ecc71', alpha=zone_alpha)   # Sehr gut (grün)
        ax.axhspan(75,  90, color='#f1c40f', alpha=zone_alpha)   # Gut (gelb)
        ax.axhspan(60,  75, color='#e67e22', alpha=zone_alpha)   # Mittelmäßig (orange)
        ax.axhspan(0,   60, color='#e74c3c', alpha=zone_alpha)   # Schlecht (rot)

        # Zonenbezeichnungen (rechts)
        zone_label_color = '#888888' if dark_mode else '#aaaaaa'
        for y, label in [(95, 'Sehr gut'), (82, 'Gut'), (67, 'Mittel'), (30, 'Schlecht')]:
            ax.text(x_max, y, label, va='center', ha='right',
                    fontsize=7, color=zone_label_color, style='italic')

        # VMAF-Linie
        ax.plot(x_values, vmaf_scores, color=line_color, linewidth=1.2)

        # Durchschnittslinie
        avg = sum(valid_scores) / len(valid_scores)
        ax.axhline(y=avg, color='#2ecc71', linewidth=1.0, linestyle='--',
                   label=f'Ø {avg:.2f}')

        # Minimum-Linie
        min_score = min(valid_scores)
        ax.axhline(y=min_score, color='#e74c3c', linewidth=0.8, linestyle=':',
                   label=f'Min {min_score:.2f}')

        # Min-Punkt markieren
        min_idx = next(i for i, s in enumerate(vmaf_scores) if abs(s - min_score) < 0.01)
        ax.plot(x_values[min_idx], min_score, 'o', color='#e74c3c', markersize=5, zorder=5)

        ax.set_ylim(0, 105)
        ax.set_xlim(x_min, x_max)
        ax.set_title("VMAF Score Verlauf", color=text_color, fontsize=12, pad=12)
        ax.set_xlabel(x_label, color=text_color, fontsize=9)
        ax.set_ylabel("VMAF Score", color=text_color, fontsize=9)
        ax.grid(True, color=grid_color, alpha=0.4)
        ax.legend(fontsize=8, facecolor=bg_color, labelcolor=text_color,
                  loc='lower right')

        for spine in ax.spines.values():
            spine.set_color(grid_color)
        ax.tick_params(axis='x', colors=text_color)
        ax.tick_params(axis='y', colors=text_color)

        plt.tight_layout()
        plt.savefig(output_path, dpi=110, facecolor=bg_color)
        plt.close()

        print(f"VMAF Graph gespeichert: {output_path}")
        return output_path

    except Exception as e:
        print(f"VMAF Graph Fehler: {e}")
        return ""

if __name__ == "__main__":
    pass
