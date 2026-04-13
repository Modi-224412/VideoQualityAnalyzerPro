import sys
import os
import shutil
import platform
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.ttk import Style

# --- MODULE IMPORTS ---
try:
    from modules.ui.console_manager   import console
    from modules.ui.theme_engine      import ThemeEngine
    from modules.ui.ui_builder        import build_ui
    from modules.app.config_manager   import ConfigManager
    from modules.app.gpu_manager      import GpuManager
    from modules.app.analysis_runner  import AnalysisRunner
    from modules.player.player_engine import PlayerEngine
    from modules.path_utils           import BASE_PATH, APP_PATH, get_tool
except ImportError as e:
    print(f"Kritischer Module Import Fehler: {e}")
    sys.exit(1)

def resource_path(relative_path):
    return os.path.join(BASE_PATH, relative_path)

app_path = APP_PATH


class VideoAnalyzerApp:

    ALL_METRICS = ["VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"]

    def __init__(self, root):
        self.root = root
        self.root.title("Video Quality Analyzer PRO - Beta")
        self.root.geometry("1000x960")
        self.root.resizable(True, True)
        self.root.minsize(900, 700)
        self._apply_hidpi_scaling()

        # Fenster-Icon setzen
        try:
            icon_ico = resource_path("icon.ico")
            icon_png = resource_path("icon.png")
            if os.path.isfile(icon_ico) and platform.system() == "Windows":
                self.root.iconbitmap(icon_ico)
            elif os.path.isfile(icon_png):
                from PIL import Image, ImageTk
                img = Image.open(icon_png).resize((64, 64), Image.LANCZOS)
                self._app_icon = ImageTk.PhotoImage(img)
                self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass

        self.badges   = []
        self.nav_btns = []

        # Queue-State
        self._queue_jobs      = []
        self._queue_running   = False
        self._queue_stop_event = threading.Event()

        # --- Pfade --- get_tool() bevorzugt lokale statische Binaries (z.B. ffmpeg mit libvmaf)
        self.ffmpeg_path = get_tool("ffmpeg")
        self.ffplay_path = get_tool("ffplay")

        # --- FFmpeg libvmaf Check ---
        self.root.after(500, self._check_ffmpeg_vmaf)

        self.dirs = {
            "reports":     os.path.join(app_path, "reports"),
            "temp":        os.path.join(app_path, "temp"),
            "graphs":      os.path.join(app_path, "temp", "graphs"),
            "heatmaps":    os.path.join(app_path, "temp", "heatmaps"),
            "screenshots": os.path.join(app_path, "temp", "screenshots"),
        }
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)

        # --- Config laden ---
        self.config_mgr = ConfigManager(os.path.join(app_path, "config.json"))
        config          = self.config_mgr.load()

        # --- Metriken laden (Standard: alle aktiv) ---
        saved_metrics       = config.get("active_metrics", self.ALL_METRICS)
        self.active_metrics = set(saved_metrics)

        # --- Theme ---
        self.theme           = ThemeEngine()
        self.theme.dark_mode = config.get("dark_mode", False)

        self.style = Style()
        self.theme.update_ttk_styles(self.style)

        # --- Module ---
        self.player = PlayerEngine(
            ffplay_path    = self.ffplay_path,
            ffmpeg_path    = self.ffmpeg_path,
            screenshot_dir = self.dirs["screenshots"]
        )

        self.gpu_mgr = GpuManager(self.ffmpeg_path)

        self.runner = AnalysisRunner(
            ffmpeg_path  = self.ffmpeg_path,
            app_path     = app_path,
            dirs         = self.dirs,
            ui_callbacks = {
                "update_ui":           self._cb_update_ui,
                "set_progress_busy":   self._cb_set_progress_busy,
                "handle_abort_ui":     self._cb_handle_abort_ui,
                "on_done":             self._cb_on_done,
                "get_artifact_frames": lambda: (
                                           0 if self.art_frames_var.get() == "0"
                                           else max(50, int(self.art_frames_var.get()))
                                           if self.art_frames_var.get().isdigit()
                                           else 1000
                                       ),
            }
        )

        # --- UI bauen ---
        build_ui(self)
        self.theme.apply(self)

        # --- Badge-Farben setzen ---
        self._update_badge_colors()

        # --- Button-Zustände initialisieren (Stop ausgrauen bis etwas läuft) ---
        self._update_button_states()

        self._progress_line_index = None  # Index der letzten Progress-Zeile
        self._reset_timer_id      = None  # ID des pending _reset_progress-Timers

        # --- Konsole verknüpfen ---
        console.register_ui_callback(
            lambda msg: self.root.after(0, self._write_to_console, msg)
        )
        console.register_progress_callback(
            lambda msg: self.root.after(0, self._update_progress_line, msg)
        )

        # --- GPU prüfen ---
        self.gpu_mgr.initialize()
        self.gpu_mgr.apply_to_ui(self.gpu_var, self.gpu_menu)
        # Queue-GPU-Menü mit denselben Optionen befüllen (teilt gpu_var)
        self.gpu_mgr.apply_to_ui(self.gpu_var, self.queue_gpu_menu)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ─────────────────────────────────────────
    # METRIK TOGGLE
    # ─────────────────────────────────────────

    def _check_ffmpeg_vmaf(self):
        """Prüft ob das gefundene FFmpeg libvmaf unterstützt. Zeigt Warnung wenn nicht."""
        import subprocess
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-filters"],
                capture_output=True, text=True, timeout=10
            )
            if "libvmaf" not in result.stdout:
                messagebox.showwarning(
                    "FFmpeg ohne libvmaf",
                    "Das gefundene FFmpeg unterstützt kein libvmaf.\n\n"
                    "VMAF, SSIM und PSNR werden nicht funktionieren.\n\n"
                    "Lösung (im Projektordner ausführen):\n"
                    "  pip install static-ffmpeg\n"
                    "  python3 get_ffmpeg.py\n"
                    "  chmod +x ffmpeg ffprobe"
                )
        except Exception:
            pass

    def toggle_metric(self, metric):
        """Schaltet eine Metrik an/aus und aktualisiert Badge-Farbe."""
        if metric in self.active_metrics:
            if len(self.active_metrics) <= 1:
                messagebox.showwarning(
                    "Mindestens eine Metrik",
                    "Es muss mindestens eine Metrik ausgewählt sein!"
                )
                return
            self.active_metrics.discard(metric)
        else:
            self.active_metrics.add(metric)

        self._update_badge_colors()
        self._save_config()

    def _update_badge_colors(self):
        """Aktualisiert alle Badge-Farben je nach aktiv/inaktiv."""
        c = self.theme.get()
        for i, (container, dot, lbl) in enumerate(self.badges):
            metric = self.ALL_METRICS[i]
            active = metric in self.active_metrics

            dot.config(fg="#2ecc71" if active else "#8B0000")
            lbl.config(fg=c["fg"] if active else "#888888")
            for w in (container, dot, lbl):
                w.config(bg=c["entry_bg"])

    # ─────────────────────────────────────────
    # CALLBACKS für AnalysisRunner
    # ─────────────────────────────────────────

    def _cb_update_ui(self, perc, start_t):
        def _u():
            self.progress.stop()
            self.progress.config(mode='determinate', style="Green.Horizontal.TProgressbar")
            self.progress['value'] = perc
            diff = time.time() - start_t
            if perc > 0:
                rem  = ((diff / perc) * 100) - diff
                m, s = divmod(int(rem), 60)
                self.progress_label.config(
                    text=f"Progress: {perc:.1f}% | Remaining: {m:02d}:{s:02d} min",
                    fg="#aaa"
                )
            self.root.update_idletasks()
        self.root.after(0, _u)

    def _cb_set_progress_busy(self, text):
        def _u():
            self._cancel_reset_timer()
            self.progress.stop()
            self.progress.config(mode='indeterminate', style="Blue.Horizontal.TProgressbar")
            self.progress.start(15)
            self.progress_label.config(text=text, fg="#3498db")
        self.root.after(0, _u)

    def _cb_handle_abort_ui(self):
        def _u():
            self.progress.stop()
            self.progress.config(mode='determinate', style="Red.Horizontal.TProgressbar")
            self.progress['value'] = 100
            self.progress_label.config(text="ABORTED", fg="#e74c3c")
            self._reset_timer_id = self.root.after(5000, self._reset_progress)
            self._update_button_states()
        self.root.after(0, _u)

    def _cb_on_done(self):
        def _u():
            self.progress.stop()
            self.progress.config(mode='determinate', style="Green.Horizontal.TProgressbar")
            self.progress_label.config(text="DONE!", fg="#2ecc71")
            self._update_button_states()
        self.root.after(0, _u)

    def _cancel_reset_timer(self):
        if self._reset_timer_id is not None:
            self.root.after_cancel(self._reset_timer_id)
            self._reset_timer_id = None

    def _reset_progress(self):
        self._reset_timer_id = None
        self.progress['value'] = 0
        self.progress.config(mode='determinate', style="Green.Horizontal.TProgressbar")
        self.progress_label.config(text="Engine Status: Idle", fg="#aaa")

    def _write_to_console(self, msg):
        self._progress_line_index = None   # Normale Zeile → Progress-Index zurücksetzen
        self.console.config(state='normal')
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)
        self.console.config(state='disabled')

    def _update_progress_line(self, msg):
        """Ersetzt die letzte Progress-Zeile in-place statt eine neue anzuhängen."""
        self.console.config(state='normal')
        if self._progress_line_index is not None:
            self.console.delete(self._progress_line_index, tk.END)
        self.console.insert(tk.END, msg + "\n")
        self._progress_line_index = self.console.index("end-1c linestart")
        self.console.see(tk.END)
        self.console.config(state='disabled')

    def copy_log_to_clipboard(self):
        """Kopiert den gesamten Konsoleninhalt in die Zwischenablage."""
        text = self.console.get("1.0", tk.END).strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        # Kurzes visuelles Feedback am Button
        self.copy_log_btn.config(text="✅ Copied!")
        self.root.after(1500, lambda: self.copy_log_btn.config(text="📋 Copy Log"))

    # ─────────────────────────────────────────
    # AKTIONEN
    # ─────────────────────────────────────────

    def _update_button_states(self):
        """Graut Start/Stop-Buttons je nach laufendem Zustand aus."""
        c                = self.theme.get()
        dark             = self.theme.dark_mode
        analyse_running  = self.runner.is_running()
        queue_running    = self._queue_running
        anything_running = analyse_running or queue_running

        dis_bg = "#4a4a4a" if dark else "#c8c8c8"
        dis_fg = "#777777" if dark else "#999999"

        # ── Analyse-Tab ───────────────────────────────────────────────────
        if anything_running:
            self.btn_start.configure(state="disabled", bg=dis_bg, fg=dis_fg,
                                     cursor="arrow", bd=0, highlightthickness=0)
        else:
            self.btn_start.configure(state="normal", bg=c["accent_green"], fg="white",
                                     activebackground=c["act_green"],
                                     cursor="hand2", bd=0, highlightthickness=0)

        if analyse_running and not queue_running:
            self.btn_abort.configure(state="normal", bg=c["accent_red"], fg="white",
                                     activebackground=c["act_red"],
                                     cursor="hand2", bd=0, highlightthickness=0)
        else:
            self.btn_abort.configure(state="disabled", bg=dis_bg, fg=dis_fg,
                                     cursor="arrow", bd=0, highlightthickness=0)

        if hasattr(self, 'btn_solo'):
            if anything_running:
                self.btn_solo.configure(state="disabled", bg=dis_bg, fg=dis_fg,
                                        cursor="arrow", bd=0, highlightthickness=0)
            else:
                self.btn_solo.configure(state="normal", bg="#8e44ad", fg="white",
                                        activebackground="#7d3c98",
                                        cursor="hand2", bd=0, highlightthickness=0)

        # ── Queue-Tab ─────────────────────────────────────────────────────
        if hasattr(self, 'btn_queue_start'):
            if anything_running:
                self.btn_queue_start.configure(state="disabled", bg=dis_bg, fg=dis_fg,
                                               cursor="arrow", bd=0, highlightthickness=0)
            else:
                self.btn_queue_start.configure(state="normal", bg=c["accent_green"], fg="white",
                                               activebackground=c["act_green"],
                                               cursor="hand2", bd=0, highlightthickness=0)

        if hasattr(self, 'btn_queue_stop'):
            if queue_running:
                self.btn_queue_stop.configure(state="normal", bg=c["accent_red"], fg="white",
                                              activebackground=c["act_red"],
                                              cursor="hand2", bd=0, highlightthickness=0)
            else:
                self.btn_queue_stop.configure(state="disabled", bg=dis_bg, fg=dis_fg,
                                              cursor="arrow", bd=0, highlightthickness=0)

    def toggle_theme(self):
        self.theme.toggle()
        self.theme.update_ttk_styles(self.style)
        self.theme.apply(self)
        self._update_badge_colors()
        self._update_button_states()
        self._save_config()

    def _gpu_params(self):
        """Gibt (gpu_active, gpu_type, gpu_device) basierend auf der aktuellen GPU-Auswahl zurück."""
        selected           = self.gpu_var.get()
        accel, device_idx  = self.gpu_mgr.gpu_options.get(selected, (None, None))
        return (accel is not None), (accel or "cuda"), device_idx

    def start_solo_scan(self):
        """Startet einen referenzlosen Scan – nur Encoded wird benötigt."""
        enco = self.encoded.get()
        if not enco or not os.path.exists(enco):
            messagebox.showwarning(
                "Kein Encode ausgewählt",
                "Bitte zuerst eine Test-Video-Datei (Encoded) auswählen."
            )
            return

        gpu_active, gpu_type, gpu_device = self._gpu_params()
        self._cancel_reset_timer()
        self.progress.config(mode='determinate', style="Green.Horizontal.TProgressbar")
        self.progress['value'] = 0
        self.progress_label.config(text="Preparing Solo-Scan...", fg="#aaa")
        self.runner.start(
            orig           = enco,
            enco           = enco,
            subsample      = self.subsample_var.get(),
            gpu_active     = gpu_active,
            dark_mode      = self.theme.dark_mode,
            active_metrics = self.active_metrics,
            offset_sec     = 0.0,
            solo_mode      = True,
            gpu_type       = gpu_type,
            gpu_device     = gpu_device,
        )
        self._update_button_states()

    def _on_player_offset_update(self, offset_sec):
        """Callback: Player hat per Auto-Sync einen Versatz erkannt → in Hauptfenster übernehmen."""
        self.root.after(0, lambda: self.offset_var.set(offset_sec))

    def start_analysis(self):
        orig = self.original.get()
        enco = self.encoded.get()

        if not orig or not os.path.exists(orig):
            messagebox.showwarning(
                "Kein Original ausgewählt",
                "Bitte zuerst eine Original-Video-Datei auswählen."
            )
            return
        if not enco or not os.path.exists(enco):
            messagebox.showwarning(
                "Kein Encode ausgewählt",
                "Bitte zuerst eine Test-Video-Datei (Encoded) auswählen."
            )
            return
        if not self.active_metrics:
            messagebox.showwarning(
                "Keine Metrik ausgewählt",
                "Bitte mindestens eine Metrik auswählen\n"
                "bevor die Analyse gestartet wird!"
            )
            return

        gpu_active, gpu_type, gpu_device = self._gpu_params()
        self._cancel_reset_timer()
        self.progress.config(mode='determinate', style="Green.Horizontal.TProgressbar")
        self.progress['value'] = 0
        self.progress_label.config(text="Preparing...", fg="#aaa")
        self.runner.start(
            orig           = orig,
            enco           = enco,
            subsample      = self.subsample_var.get(),
            gpu_active     = gpu_active,
            dark_mode      = self.theme.dark_mode,
            active_metrics = self.active_metrics,
            offset_sec     = self.offset_var.get(),
            gpu_type       = gpu_type,
            gpu_device     = gpu_device,
        )
        self._update_button_states()

    def stop_analysis(self):
        self.runner.stop()
        self.root.after(100, self._update_button_states)

    # ─────────────────────────────────────────
    # TAB-SWITCHING
    # ─────────────────────────────────────────

    def switch_tab(self, tab_name):
        """Wechselt zwischen 'analyse' und 'queue' Tab."""
        if tab_name == "analyse":
            if hasattr(self, 'queue_frame'):
                self.queue_frame.pack_forget()
            self.analyse_frame.pack(fill=tk.X, before=self.progress_frame)
        elif tab_name == "queue":
            self.analyse_frame.pack_forget()
            if hasattr(self, 'queue_frame'):
                self.queue_frame.pack(fill=tk.X, before=self.progress_frame)
        self._active_tab = tab_name
        self._update_tab_buttons()

    def _update_tab_buttons(self):
        c = self.theme.get()
        for name, btn in self._tab_buttons.items():
            active = (name == getattr(self, '_active_tab', 'analyse'))
            btn.configure(
                bg=c["accent_green"] if active else c["btn_secondary"],
                fg="white"           if active else c["btn_fg"],
                activebackground=c["act_green"] if active else c["act_secondary"],
                bd=0, highlightthickness=0,
            )

    # ─────────────────────────────────────────
    # MEHRFACHANALYSE
    # ─────────────────────────────────────────

    def queue_apply_gpu_to_all(self):
        """Setzt die aktuell gewählte GPU für alle pending Jobs."""
        gpu_val = self.gpu_var.get()
        changed = 0
        for job in self._queue_jobs:
            if job.status == "pending":
                job.gpu_var = gpu_val
                changed += 1
        if changed:
            self._queue_refresh_list()

    def queue_add_job(self):
        """Öffnet den Batch-Dialog zum Hinzufügen eines oder mehrerer Jobs."""
        from modules.ui.job_dialog import BatchAddDialog, QueueJob
        gpu_options = list(self.gpu_mgr.gpu_options.keys()) or ["🖥️  Kein GPU  (CPU)"]

        def on_result(jobs_data):
            for data in jobs_data:
                self._queue_jobs.append(QueueJob(**data))
            self._queue_refresh_list()

        BatchAddDialog(self.root, self.theme.get(), gpu_options, on_result,
                       default_gpu=self.gpu_var.get())

    def queue_edit_job(self):
        """Öffnet den Dialog zum Bearbeiten des ausgewählten Jobs."""
        sel = self.queue_tree.selection()
        if not sel:
            return
        job_id = int(sel[0])
        job    = next((j for j in self._queue_jobs if j.id == job_id), None)
        if not job:
            return
        if job.status == "running":
            messagebox.showwarning("Job läuft",
                                   "Laufende Jobs können nicht bearbeitet werden.",
                                   parent=self.root)
            return

        from modules.ui.job_dialog import JobDialog
        gpu_options = list(self.gpu_mgr.gpu_options.keys()) or ["🖥️  Kein GPU  (CPU)"]

        def on_result(jobs_data):   # JobDialog gibt ebenfalls eine Liste zurück
            data            = jobs_data[0]
            job.original    = data["original"]
            job.encoded     = data["encoded"]
            job.solo_mode   = data["solo_mode"]
            job.metrics     = data["metrics"]
            job.subsample   = data["subsample"]
            job.artifact_frames = data["artifact_frames"]
            job.gpu_var     = data["gpu_var"]
            self._queue_refresh_list()

        JobDialog(self.root, self.theme.get(), gpu_options, on_result, job=job)

    def queue_remove_job(self):
        """Entfernt den ausgewählten Job aus der Mehrfachanalyse."""
        sel = self.queue_tree.selection()
        if not sel:
            return
        job_id = int(sel[0])
        job    = next((j for j in self._queue_jobs if j.id == job_id), None)
        if job and job.status == "running":
            messagebox.showwarning("Job läuft",
                                   "Laufende Jobs können nicht entfernt werden.",
                                   parent=self.root)
            return
        self._queue_jobs = [j for j in self._queue_jobs if j.id != job_id]
        self._queue_refresh_list()

    def queue_move_up(self):
        sel = self.queue_tree.selection()
        if not sel:
            return
        job_id = int(sel[0])
        idx    = next((i for i, j in enumerate(self._queue_jobs) if j.id == job_id), None)
        if idx is None or idx == 0:
            return
        self._queue_jobs[idx - 1], self._queue_jobs[idx] = \
            self._queue_jobs[idx], self._queue_jobs[idx - 1]
        self._queue_refresh_list()
        self.queue_tree.selection_set(str(job_id))

    def queue_move_down(self):
        sel = self.queue_tree.selection()
        if not sel:
            return
        job_id = int(sel[0])
        idx    = next((i for i, j in enumerate(self._queue_jobs) if j.id == job_id), None)
        if idx is None or idx >= len(self._queue_jobs) - 1:
            return
        self._queue_jobs[idx], self._queue_jobs[idx + 1] = \
            self._queue_jobs[idx + 1], self._queue_jobs[idx]
        self._queue_refresh_list()
        self.queue_tree.selection_set(str(job_id))

    def queue_clear(self):
        """Leert die gesamte Mehrfachanalyse (mit Bestätigung)."""
        if any(j.status == "running" for j in self._queue_jobs):
            messagebox.showwarning("Queue läuft",
                                   "Bitte erst die Queue stoppen.",
                                   parent=self.root)
            return
        if self._queue_jobs and messagebox.askyesno(
            "Mehrfachanalyse leeren", "Alle Jobs entfernen?", parent=self.root
        ):
            self._queue_jobs.clear()
            self._queue_refresh_list()

    def _queue_refresh_list(self):
        """Aktualisiert die Treeview-Anzeige der Mehrfachanalyse."""
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)

        for i, job in enumerate(self._queue_jobs, 1):
            enc_name  = os.path.basename(job.encoded)  if job.encoded  else "–"
            orig_name = "(Solo)"                        if job.solo_mode else \
                        os.path.basename(job.original)  if job.original else "–"
            metrics_str = ", ".join(sorted(job.metrics))
            self.queue_tree.insert(
                "", tk.END,
                iid=str(job.id),
                values=(i, enc_name, orig_name, job.mode_str(), metrics_str, job.status_icon()),
                tags=(job.status_tag(),),
            )

        count = len(self._queue_jobs)
        self.queue_count_label.config(
            text=f"{count} Job{'s' if count != 1 else ''}"
        )

    def queue_start(self):
        """Startet die sequenzielle Abarbeitung aller pending Jobs."""
        pending = [j for j in self._queue_jobs if j.status == "pending"]
        if not pending:
            messagebox.showinfo("Keine Jobs",
                                "Keine ausstehenden Jobs in der Mehrfachanalyse.",
                                parent=self.root)
            return
        if self._queue_running:
            return
        self._cancel_reset_timer()
        self._queue_running = True
        self._queue_stop_event.clear()
        self.root.after(0, lambda: (
            self.progress.stop(),
            self.progress.config(mode='determinate', style="Green.Horizontal.TProgressbar"),
            self.progress_label.config(text="Mehrfachanalyse wird gestartet…", fg="#aaa")
        ))
        self._update_button_states()
        threading.Thread(target=self._queue_process, daemon=True).start()

    def queue_stop(self):
        """Bricht die laufende Queue ab."""
        self._queue_stop_event.set()
        self.runner.stop()
        self._queue_running = False
        self.root.after(100, self._update_button_states)

    def _queue_gpu_params(self, gpu_var_str):
        """Löst GPU-Parameter aus einem gpu_var-String auf."""
        accel, device_idx = self.gpu_mgr.gpu_options.get(gpu_var_str, (None, None))
        return (accel is not None), (accel or "cuda"), device_idx

    def _queue_process(self):
        """Verarbeitet alle pending Jobs sequenziell in einem eigenen Thread."""
        pending = [j for j in self._queue_jobs if j.status == "pending"]
        total   = len(pending)

        # Originale Callbacks sichern
        orig_on_done  = self.runner.cb.get("on_done")
        orig_on_abort = self.runner.cb.get("handle_abort_ui")
        orig_art_cb   = self.runner.cb.get("get_artifact_frames")

        for idx, job in enumerate(pending):
            if self._queue_stop_event.is_set():
                break

            job.status = "running"
            self.root.after(0, self._queue_refresh_list)
            self.root.after(0, lambda i=idx + 1, t=total: (
                self.progress.config(mode='indeterminate',
                                     style="Blue.Horizontal.TProgressbar"),
                self.progress.start(15),
                self.progress_label.config(
                    text=f"Mehrfachanalyse: Job {i} / {t} …", fg="#3498db"
                )
            ))

            job_done = threading.Event()

            def _done(j=job, ev=job_done):
                j.status = "done"
                ev.set()

            def _abort(j=job, ev=job_done):
                j.status = "error"
                ev.set()
                if orig_on_abort:
                    orig_on_abort()

            self.runner.cb["on_done"]           = _done
            self.runner.cb["handle_abort_ui"]   = _abort
            self.runner.cb["get_artifact_frames"] = lambda j=job: j.artifact_frames

            gpu_active, gpu_type, gpu_device = self._queue_gpu_params(job.gpu_var)

            self.runner.start(
                orig           = job.original or job.encoded,
                enco           = job.encoded,
                subsample      = job.subsample,
                gpu_active     = gpu_active,
                dark_mode      = self.theme.dark_mode,
                active_metrics = job.metrics,
                offset_sec     = 0.0,
                solo_mode      = job.solo_mode,
                gpu_type       = gpu_type,
                gpu_device     = gpu_device,
            )

            job_done.wait()  # Warten bis Job fertig oder abgebrochen
            # Race Condition vermeiden: warten bis analysis_running = False gesetzt ist
            while self.runner.is_running():
                time.sleep(0.01)
            self.root.after(0, self._queue_refresh_list)

            if self._queue_stop_event.is_set():
                break

        # Callbacks wiederherstellen
        self.runner.cb["on_done"]             = orig_on_done
        self.runner.cb["handle_abort_ui"]     = orig_on_abort
        self.runner.cb["get_artifact_frames"] = orig_art_cb

        self._queue_running = False

        # Abgebrochene pending-Jobs markieren
        if self._queue_stop_event.is_set():
            for j in self._queue_jobs:
                if j.status == "pending":
                    j.status = "aborted"

        self.root.after(0, self._queue_refresh_list)
        self.root.after(0, self._update_button_states)
        self.root.after(0, lambda: (
            self.progress.stop(),
            self.progress.config(mode='determinate',
                                 style="Green.Horizontal.TProgressbar"),
            self.progress_label.config(
                text="Mehrfachanalyse abgeschlossen!" if not self._queue_stop_event.is_set()
                else "Mehrfachanalyse abgebrochen.",
                fg="#2ecc71" if not self._queue_stop_event.is_set() else "#e74c3c"
            )
        ))

    def browse(self, entry):
        f = filedialog.askopenfilename()
        if f:
            entry.delete(0, tk.END)
            entry.insert(0, os.path.normpath(f))

    def open_dir(self, key):
        path = self.dirs.get(key)
        if path and os.path.exists(path):
            if platform.system() == "Windows":
                os.startfile(path)
            else:
                import subprocess
                subprocess.run(["xdg-open", path])

    def clear_cache(self):
        if messagebox.askyesno("Clear Cache", "Delete all temporary data?"):
            try:
                shutil.rmtree(self.dirs["temp"])
                for sub in ["graphs", "heatmaps", "screenshots"]:
                    os.makedirs(os.path.join(self.dirs["temp"], sub), exist_ok=True)
                console.print_success("Cache erfolgreich geleert.")
            except Exception as e:
                console.print_error(f"Cache clear Fehler: {e}")

    # ─────────────────────────────────────────
    # CONFIG SPEICHERN
    # ─────────────────────────────────────────

    def _save_config(self):
        self.config_mgr.save({
            "dark_mode":       self.theme.dark_mode,
            "active_metrics":  list(self.active_metrics),
            "artifact_frames": (
                0 if self.art_frames_var.get() == "0"
                else max(50, int(self.art_frames_var.get()))
                if self.art_frames_var.get().isdigit()
                else 1000
            ),
        })

    # ─────────────────────────────────────────
    # CLEANUP
    # ─────────────────────────────────────────

    def _apply_hidpi_scaling(self):
        """Passt die tkinter-Skalierung automatisch an die Bildschirm-DPI an (Linux/HiDPI)."""
        if platform.system() != "Linux":
            return
        try:
            dpi = self.root.winfo_fpixels('1i')  # Pixel pro Zoll
            if dpi > 96:
                scale = round(dpi / 96.0, 2)
                self.root.tk.call('tk', 'scaling', scale)
        except Exception:
            pass

    def on_close(self):
        self.player.close_all()
        self._save_config()
        self.root.destroy()


if __name__ == "__main__":
    if platform.system() == "Windows":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VideoQualityAnalyzerPro")
    root = tk.Tk()
    app  = VideoAnalyzerApp(root)
    root.mainloop()
