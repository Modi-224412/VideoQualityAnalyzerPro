"""
path_utils.py – Zentrale Pfad-Logik für Script- und EXE-Modus.

Regeln:
  base_path  = wo die gebündelten Ressourcen liegen (sys._MEIPASS oder Projektwurzel)
  app_path   = wo die EXE / main_gui.py liegt  →  Arbeitsverzeichnis für Reports, Temp, etc.
  get_tool   = gibt absoluten Pfad zu ffmpeg / ffprobe / ffplay zurück
"""

import os
import sys
import platform


def _detect_paths():
    if getattr(sys, 'frozen', False):
        # PyInstaller EXE: Ressourcen in _MEIPASS, Arbeitsverzeichnis neben der EXE
        base = sys._MEIPASS
        app  = os.path.dirname(sys.executable)
    else:
        # Script-Modus: Projektwurzel = 2 Ebenen über modules/
        # Funktioniert egal aus welchem Unterordner importiert wird
        this_file = os.path.abspath(__file__)
        # Aufsteigen bis wir die Wurzel finden (enthält main_gui.py)
        candidate = os.path.dirname(this_file)
        for _ in range(5):
            if os.path.exists(os.path.join(candidate, "main_gui.py")):
                break
            candidate = os.path.dirname(candidate)
        base = candidate
        app  = candidate

    return base, app


BASE_PATH, APP_PATH = _detect_paths()


def get_tool(name: str) -> str:
    """
    Gibt den Pfad zu einem FFmpeg-Tool zurück.
    Sucht zuerst neben der EXE / im Projektordner, fällt auf System-PATH zurück.

    Args:
        name: 'ffmpeg', 'ffprobe' oder 'ffplay'
    """
    exe_name = f"{name}.exe" if platform.system() == "Windows" else name

    # 1. Neben der EXE / im Projektordner
    local = os.path.join(APP_PATH, exe_name)
    if os.path.exists(local):
        return local

    # 2. In _MEIPASS (PyInstaller Bundle)
    bundled = os.path.join(BASE_PATH, exe_name)
    if os.path.exists(bundled):
        return bundled

    # 3. System-PATH als letzter Ausweg
    return name