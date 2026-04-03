import os
import platform
import threading
import tkinter as tk
from tkinter import messagebox

from modules.player.player_window import PlayerWindow
from modules.player.comparison_window import ComparisonWindow

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


class PlayerEngine:
    def __init__(self, ffplay_path, ffmpeg_path=None, screenshot_dir=None):
        """
        Args:
            ffplay_path:    Pfad zu ffplay.exe (für Kompatibilität behalten)
            ffmpeg_path:    Pfad zu ffmpeg.exe (für Audio-Extraktion)
            screenshot_dir: Zielordner für Screenshots aus dem Player
        """
        self.ffplay_path    = ffplay_path
        self.ffmpeg_path    = ffmpeg_path or ffplay_path.replace("ffplay", "ffmpeg")
        self.screenshot_dir = screenshot_dir
        self._windows       = []  # Alle offenen Fenster tracken

    # ─────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────

    def play_single(self, video_path, parent=None):
        """
        Öffnet einen einzelnen PlayerWindow für eine Videodatei.
        """
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("Fehler", f"Datei nicht gefunden:\n{video_path}")
            return

        title = f"▶ {os.path.basename(video_path)}"

        def _create():
            win = PlayerWindow(
                parent         = parent,
                video_path     = video_path,
                ffmpeg_path    = self.ffmpeg_path,
                title          = title,
                screenshot_dir = self.screenshot_dir
            )
            self._windows.append(win)

        if parent:
            parent.after(0, _create)
        else:
            _create()

    def play_comparison(self, original, encoded, parent=None,
                        offset_sec=0.0, offset_callback=None):
        """
        Öffnet ein einzelnes ComparisonWindow mit beiden Videos
        nebeneinander – perfekt synchron über einen gemeinsamen Video-Loop.
        offset_sec:       Initialer Video-Versatz in Sekunden
        offset_callback:  Wird aufgerufen wenn der Versatz im Player geändert wird
        """
        if not original or not os.path.exists(original):
            messagebox.showerror("Fehler", f"Original nicht gefunden:\n{original}")
            return

        if not encoded or not os.path.exists(encoded):
            messagebox.showerror("Fehler", f"Encoded nicht gefunden:\n{encoded}")
            return

        def _create():
            win = ComparisonWindow(
                parent           = parent,
                original_path    = original,
                encoded_path     = encoded,
                ffmpeg_path      = self.ffmpeg_path,
                screenshot_dir   = self.screenshot_dir,
                offset_sec       = offset_sec,
                offset_callback  = offset_callback,
            )
            self._windows.append(win)

        if parent:
            parent.after(0, _create)
        else:
            _create()

    def close_all(self):
        """Schließt alle offenen Player-Fenster sauber."""
        for win in self._windows:
            try:
                win.close()
            except Exception:
                pass
        self._windows.clear()