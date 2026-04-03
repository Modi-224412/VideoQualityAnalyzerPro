import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import json
import os

from modules.path_utils import APP_PATH

def create_vmaf_graph(log_path=None, dark_mode=False):
    """
    Erstellt einen VMAF-Zeitverlauf-Graph aus dem VMAF JSON-Log.
    FIX: Korrekter Log-Pfad, Dark Mode Support, kein marker='o' bei langen Videos.
    
    Args:
        log_path: Pfad zur vmaf.json – falls None wird Standard-Pfad genutzt
        dark_mode: True für dunklen Hintergrund
    Returns:
        Pfad zum gespeicherten Graph oder leerer String bei Fehler
    """
    # FIX: Korrekter Standard-Pfad (war vmaf_log.json, korrekt ist vmaf.json)
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

        # Scores einlesen – ungültige Werte (None, <= 0.0) werden als NaN gesetzt
        # damit sie im Graph als Lücke erscheinen statt als falsche Ausreißer nach unten.
        # Ursache: libvmaf hat einen Warmup-Effekt der erste Frames mit Score 0.0 liefert.
        frame_numbers = []
        vmaf_scores   = []
        for i, f in enumerate(frames):
            score = f.get("metrics", {}).get("vmaf")
            frame_numbers.append(f.get("frameNum", i))
            vmaf_scores.append(float('nan') if (score is None or score <= 0.0) else score)

        valid_scores = [s for s in vmaf_scores if s == s]  # NaN-frei (NaN != NaN)
        if not valid_scores:
            print("VMAF Graph: Keine gültigen VMAF-Werte im Log.")
            return ""

        # Theme-Farben
        bg_color = '#1e1e1e' if dark_mode else '#ffffff'
        grid_color = '#444444' if dark_mode else '#dddddd'
        text_color = '#f0f0f0' if dark_mode else '#2c3e50'
        line_color = '#3498db'

        plt.figure(figsize=(10, 4), facecolor=bg_color)
        ax = plt.axes()
        ax.set_facecolor(bg_color)

        # NaN-Werte werden von matplotlib automatisch als Lücken gerendert
        plt.plot(frame_numbers, vmaf_scores, color=line_color, linewidth=1.2)

        # Durchschnittslinie (nur über gültige Scores)
        avg = sum(valid_scores) / len(valid_scores)
        plt.axhline(y=avg, color='#2ecc71', linewidth=1.0, linestyle='--', label=f'Ø {avg:.2f}')

        plt.ylim(0, 105)
        plt.title("VMAF Score pro Frame", color=text_color, fontsize=11, pad=10)
        plt.xlabel("Frame", color=text_color, fontsize=9)
        plt.ylabel("VMAF Score", color=text_color, fontsize=9)
        plt.grid(True, color=grid_color, alpha=0.4)
        plt.legend(fontsize=8, facecolor=bg_color, labelcolor=text_color)

        ax.spines['bottom'].set_color(grid_color)
        ax.spines['left'].set_color(grid_color)
        ax.spines['top'].set_color(grid_color)
        ax.spines['right'].set_color(grid_color)
        ax.tick_params(axis='x', colors=text_color)
        ax.tick_params(axis='y', colors=text_color)

        plt.tight_layout()
        plt.savefig(output_path, dpi=100, facecolor=bg_color)
        plt.close()

        print(f"VMAF Graph gespeichert: {output_path}")
        return output_path

    except Exception as e:
        print(f"VMAF Graph Fehler: {e}")
        return ""

if __name__ == "__main__":
    pass