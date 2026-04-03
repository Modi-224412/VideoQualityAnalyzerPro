"""
QueueJob Datenklasse + JobDialog – fügt/bearbeitet einzelne Queue-Jobs.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

ALL_METRICS = ["VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"]


class QueueJob:
    _id_counter = 0

    def __init__(self, original="", encoded="", solo_mode=False,
                 metrics=None, subsample="1", artifact_frames=1000,
                 gpu_var="🖥️  Kein GPU  (CPU)"):
        QueueJob._id_counter += 1
        self.id             = QueueJob._id_counter
        self.original       = original
        self.encoded        = encoded
        self.solo_mode      = solo_mode
        self.metrics        = set(metrics) if metrics is not None else set(ALL_METRICS)
        self.subsample      = subsample
        self.artifact_frames = artifact_frames
        self.gpu_var        = gpu_var
        self.status         = "pending"   # pending | running | done | error | aborted

    def mode_str(self):
        return "Solo" if self.solo_mode else "Vergleich"

    def status_icon(self):
        return {
            "pending":  "⏳ Wartend",
            "running":  "⚙️ Läuft",
            "done":     "✅ Fertig",
            "error":    "❌ Fehler",
            "aborted":  "🛑 Abgebrochen",
        }.get(self.status, self.status)

    def status_tag(self):
        return {
            "pending": "tag_pending",
            "running": "tag_running",
            "done":    "tag_done",
            "error":   "tag_error",
            "aborted": "tag_error",
        }.get(self.status, "tag_pending")


class JobDialog(tk.Toplevel):
    """Dialog zum Hinzufügen oder Bearbeiten eines Queue-Jobs."""

    def __init__(self, parent, colors, gpu_options, result_callback,
                 job=None, default_gpu=None):
        super().__init__(parent)
        self._cb          = result_callback
        self._colors      = colors
        self._gpu_opt     = gpu_options or ["🖥️  Kein GPU  (CPU)"]
        self._default_gpu = default_gpu

        self.title("Job bearbeiten" if job else "Job hinzufügen")
        self.geometry("770x510")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=colors["bg"])

        self._build(job)

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # ─────────────────────────────────────────
    # BUILD
    # ─────────────────────────────────────────

    def _build(self, job):
        c    = self._colors
        main = tk.Frame(self, bg=c["bg"], padx=20, pady=14)
        main.pack(fill=tk.BOTH, expand=True)

        # ── DATEIEN ──────────────────────────────────────────────────────
        tk.Label(main, text="DATEIEN", font=('Arial', 9, 'bold'),
                 bg=c["bg"], fg=c["fg"]).pack(anchor=tk.W)

        fcard = tk.Frame(main, bg=c["card"], padx=14, pady=10,
                         highlightthickness=1, highlightbackground=c["border"])
        fcard.pack(fill=tk.X, pady=(3, 8))

        # Original
        tk.Label(fcard, text="Reference Video (Original)",
                 font=('Arial', 8, 'bold'), bg=c["card"], fg=c["fg"]).pack(anchor=tk.W)
        orig_row = tk.Frame(fcard, bg=c["card"])
        orig_row.pack(fill=tk.X, pady=(2, 5))
        self._orig = tk.Entry(orig_row, width=74, relief="flat", font=('Consolas', 8),
                              bg=c["entry_bg"], fg=c["fg"], insertbackground=c["fg"],
                              bd=0, highlightthickness=0)
        self._orig.pack(side=tk.LEFT, ipady=3)
        if job and job.original:
            self._orig.insert(0, job.original)
        tk.Button(orig_row, text="Browse…", relief="flat", padx=8, pady=2,
                  bg=c["btn_secondary"], fg=c["btn_fg"], cursor="hand2",
                  activebackground=c["act_secondary"], bd=0,
                  command=lambda: self._browse(self._orig)).pack(side=tk.LEFT, padx=(8, 0))

        # Encoded
        tk.Label(fcard, text="Test Video (Encoded)",
                 font=('Arial', 8, 'bold'), bg=c["card"], fg=c["fg"]).pack(anchor=tk.W)
        enco_row = tk.Frame(fcard, bg=c["card"])
        enco_row.pack(fill=tk.X, pady=(2, 5))
        self._enco = tk.Entry(enco_row, width=74, relief="flat", font=('Consolas', 8),
                              bg=c["entry_bg"], fg=c["fg"], insertbackground=c["fg"],
                              bd=0, highlightthickness=0)
        self._enco.pack(side=tk.LEFT, ipady=3)
        if job and job.encoded:
            self._enco.insert(0, job.encoded)
        tk.Button(enco_row, text="Browse…", relief="flat", padx=8, pady=2,
                  bg=c["btn_secondary"], fg=c["btn_fg"], cursor="hand2",
                  activebackground=c["act_secondary"], bd=0,
                  command=lambda: self._browse(self._enco)).pack(side=tk.LEFT, padx=(8, 0))

        # Solo-Scan
        solo_row = tk.Frame(fcard, bg=c["card"])
        solo_row.pack(fill=tk.X, pady=(2, 0))
        self._solo = tk.BooleanVar(value=job.solo_mode if job else False)
        tk.Checkbutton(
            solo_row,
            text="Solo-Scan  (kein Original nötig – VMAF / SSIM / PSNR werden übersprungen)",
            variable=self._solo, bg=c["card"], fg=c["fg"],
            selectcolor=c["entry_bg"], activebackground=c["card"],
            font=('Arial', 8), cursor="hand2",
            command=self._on_solo_toggle,
        ).pack(side=tk.LEFT)

        # ── METRIKEN ─────────────────────────────────────────────────────
        tk.Label(main, text="METRIKEN", font=('Arial', 9, 'bold'),
                 bg=c["bg"], fg=c["fg"]).pack(anchor=tk.W, pady=(4, 0))

        mcard = tk.Frame(main, bg=c["card"], padx=14, pady=8,
                         highlightthickness=1, highlightbackground=c["border"])
        mcard.pack(fill=tk.X, pady=(3, 8))

        active_m = job.metrics if job else set(ALL_METRICS)
        self._mvars = {}
        mrow = tk.Frame(mcard, bg=c["card"])
        mrow.pack(fill=tk.X)
        for m in ALL_METRICS:
            var = tk.BooleanVar(value=(m in active_m))
            self._mvars[m] = var
            tk.Checkbutton(mrow, text=m, variable=var,
                           bg=c["card"], fg=c["fg"], selectcolor=c["entry_bg"],
                           activebackground=c["card"], font=('Arial', 8),
                           cursor="hand2").pack(side=tk.LEFT, padx=(0, 12))

        # ── OPTIONEN ─────────────────────────────────────────────────────
        tk.Label(main, text="OPTIONEN", font=('Arial', 9, 'bold'),
                 bg=c["bg"], fg=c["fg"]).pack(anchor=tk.W)

        ocard = tk.Frame(main, bg=c["card"], padx=14, pady=8,
                         highlightthickness=1, highlightbackground=c["border"])
        ocard.pack(fill=tk.X, pady=(3, 10))

        orow = tk.Frame(ocard, bg=c["card"])
        orow.pack(fill=tk.X)

        # GPU
        tk.Label(orow, text="⚡ GPU:", font=('Arial', 8, 'bold'),
                 bg=c["card"], fg=c["fg"]).pack(side=tk.LEFT)
        gpu_val = job.gpu_var if job else (self._default_gpu or self._gpu_opt[0])
        self._gpu = tk.StringVar(value=gpu_val)
        gm = tk.OptionMenu(orow, self._gpu, *self._gpu_opt)
        gm.config(font=('Arial', 8), relief="flat", bg=c["btn_secondary"],
                  fg=c["btn_fg"], width=28, anchor="w",
                  highlightthickness=0, bd=0, activebackground=c["act_secondary"])
        gm["menu"].config(bg=c["entry_bg"], fg=c["fg"], relief="flat",
                          tearoff=0, activebackground=c["accent_green"],
                          activeforeground="white")
        gm.pack(side=tk.LEFT, padx=(5, 14))

        # Subsampling
        tk.Label(orow, text="Subsampling:", font=('Arial', 8),
                 bg=c["card"], fg=c["fg"]).pack(side=tk.LEFT)
        self._sub = tk.StringVar(value=job.subsample if job else "1")
        sm = tk.OptionMenu(orow, self._sub, "1", "2", "4", "8")
        sm.config(font=('Arial', 8), relief="flat", bg=c["btn_secondary"],
                  fg=c["btn_fg"], highlightthickness=0, bd=0,
                  activebackground=c["act_secondary"])
        sm["menu"].config(bg=c["entry_bg"], fg=c["fg"], relief="flat",
                          tearoff=0, activebackground=c["accent_green"],
                          activeforeground="white")
        sm.pack(side=tk.LEFT, padx=(5, 14))

        # Artefakt-Frames
        tk.Label(orow, text="Artefakt-Frames:", font=('Arial', 8),
                 bg=c["card"], fg=c["fg"]).pack(side=tk.LEFT)
        self._art = tk.StringVar(value=str(job.artifact_frames if job else 1000))
        tk.Entry(orow, textvariable=self._art, width=6, relief="flat",
                 font=('Consolas', 8), justify=tk.CENTER,
                 bg=c["entry_bg"], fg=c["fg"], bd=0,
                 highlightthickness=0).pack(side=tk.LEFT, padx=(5, 4))
        tk.Label(orow, text="(0 = alle)", font=('Arial', 7),
                 bg=c["card"], fg=c["sub_lbl"]).pack(side=tk.LEFT)

        # ── SAVE / CANCEL ─────────────────────────────────────────────────
        brow = tk.Frame(main, bg=c["bg"])
        brow.pack(fill=tk.X)
        tk.Button(brow, text="✅  Speichern", relief="flat", padx=15, pady=6,
                  font=('Arial', 9, 'bold'), bg=c["accent_green"], fg="white",
                  activebackground=c["act_green"], bd=0,
                  cursor="hand2", command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(brow, text="Abbrechen", relief="flat", padx=15, pady=6,
                  font=('Arial', 9), bg=c["btn_secondary"], fg=c["btn_fg"],
                  activebackground=c["act_secondary"], bd=0,
                  cursor="hand2", command=self.destroy).pack(side=tk.LEFT)

        self._on_solo_toggle()

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _on_solo_toggle(self):
        self._orig.config(state="disabled" if self._solo.get() else "normal")

    def _browse(self, entry):
        f = filedialog.askopenfilename(
            filetypes=[
                ("Video-Dateien", "*.mp4 *.mkv *.avi *.mov *.ts *.m2ts *.wmv *.flv *.webm *.m4v"),
                ("Alle Dateien",  "*.*"),
            ]
        )
        if f:
            entry.config(state="normal")
            entry.delete(0, tk.END)
            entry.insert(0, os.path.normpath(f))

    def _save(self):
        enco = self._enco.get().strip()
        orig = self._orig.get().strip()
        solo = self._solo.get()

        if not enco or not os.path.exists(enco):
            messagebox.showwarning("Kein Encode",
                                   "Bitte eine gültige Encoded-Datei auswählen.", parent=self)
            return
        if not solo and (not orig or not os.path.exists(orig)):
            messagebox.showwarning("Kein Original",
                                   "Bitte eine gültige Original-Datei auswählen\n"
                                   "oder Solo-Scan aktivieren.", parent=self)
            return

        active_m = {m for m, v in self._mvars.items() if v.get()}
        if not active_m:
            messagebox.showwarning("Keine Metrik",
                                   "Mindestens eine Metrik auswählen.", parent=self)
            return

        art = 1000
        if self._art.get().isdigit():
            art = int(self._art.get())

        self._cb([{
            "original":        orig if not solo else "",
            "encoded":         enco,
            "solo_mode":       solo,
            "metrics":         active_m,
            "subsample":       self._sub.get(),
            "artifact_frames": art,
            "gpu_var":         self._gpu.get(),
        }])
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────

class BatchAddDialog(tk.Toplevel):
    """
    Mehrere Jobs auf einmal hinzufügen:
    Wähle N Originals + N Encodes → werden der Reihe nach gepaart.
    """

    _FILETYPES = [
        ("Video-Dateien", "*.mp4 *.mkv *.avi *.mov *.ts *.m2ts *.wmv *.flv *.webm *.m4v"),
        ("Alle Dateien",  "*.*"),
    ]

    def __init__(self, parent, colors, gpu_options, result_callback, default_gpu=None):
        super().__init__(parent)
        self._cb          = result_callback
        self._colors      = colors
        self._gpu_opt     = gpu_options or ["🖥️  Kein GPU  (CPU)"]
        self._default_gpu = default_gpu
        self._orig_files  = []   # Liste voller Pfade
        self._enco_files  = []

        self.title("Jobs hinzufügen  (Mehrfachauswahl)")
        self.geometry("820x600")
        self.resizable(True, True)
        self.minsize(700, 520)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=colors["bg"])

        self._build()

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # ─────────────────────────────────────────
    # BUILD
    # ─────────────────────────────────────────

    def _build(self):
        c    = self._colors
        main = tk.Frame(self, bg=c["bg"], padx=20, pady=14)
        main.pack(fill=tk.BOTH, expand=True)

        # ── SOLO-TOGGLE (oben, beeinflusst die Datei-Sektion) ────────────
        solo_top = tk.Frame(main, bg=c["bg"])
        solo_top.pack(fill=tk.X, pady=(0, 6))
        self._solo = tk.BooleanVar(value=False)
        tk.Checkbutton(
            solo_top,
            text="Solo-Scan  (kein Original nötig – VMAF / SSIM / PSNR werden übersprungen)",
            variable=self._solo, bg=c["bg"], fg=c["fg"],
            selectcolor=c["entry_bg"], activebackground=c["bg"],
            font=('Arial', 8), cursor="hand2",
            command=self._on_solo_toggle,
        ).pack(side=tk.LEFT)

        # ── DATEILISTEN nebeneinander ─────────────────────────────────────
        tk.Label(main, text="DATEIEN", font=('Arial', 9, 'bold'),
                 bg=c["bg"], fg=c["fg"]).pack(anchor=tk.W)

        lists_card = tk.Frame(main, bg=c["card"], padx=14, pady=10,
                              highlightthickness=1, highlightbackground=c["border"])
        lists_card.pack(fill=tk.BOTH, expand=True, pady=(3, 6))

        # Zwei Spalten
        lists_card.columnconfigure(0, weight=1)
        lists_card.columnconfigure(1, weight=1)

        # Original-Spalte
        self._orig_frame = tk.Frame(lists_card, bg=c["card"])
        self._orig_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Label(self._orig_frame, text="Reference Videos (Original)",
                 font=('Arial', 8, 'bold'), bg=c["card"], fg=c["fg"]).pack(anchor=tk.W)

        orig_list_frame = tk.Frame(self._orig_frame, bg=c["card"])
        orig_list_frame.pack(fill=tk.BOTH, expand=True, pady=(3, 0))

        self._orig_lb = tk.Listbox(
            orig_list_frame, height=7, relief="flat", selectmode=tk.SINGLE,
            font=('Consolas', 8), bg=c["entry_bg"], fg=c["fg"],
            selectbackground=c["accent_green"], selectforeground="white",
            bd=0, highlightthickness=0, activestyle="none"
        )
        orig_vsb = tk.Scrollbar(orig_list_frame, orient=tk.VERTICAL,
                                command=self._orig_lb.yview)
        self._orig_lb.configure(yscrollcommand=orig_vsb.set)
        self._orig_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        orig_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        orig_btn_row = tk.Frame(self._orig_frame, bg=c["card"])
        orig_btn_row.pack(fill=tk.X, pady=(4, 0))
        self._orig_browse_btn = tk.Button(
            orig_btn_row, text="📂  Browse…", relief="flat", padx=8, pady=2,
            font=('Arial', 8), cursor="hand2",
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"], bd=0,
            command=lambda: self._browse_multi(self._orig_files, self._orig_lb)
        )
        self._orig_browse_btn.pack(side=tk.LEFT)
        tk.Button(
            orig_btn_row, text="✕ Leeren", relief="flat", padx=6, pady=2,
            font=('Arial', 8), cursor="hand2",
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"], bd=0,
            command=lambda: self._clear_list(self._orig_files, self._orig_lb)
        ).pack(side=tk.LEFT, padx=(6, 0))

        # Encoded-Spalte
        enco_frame = tk.Frame(lists_card, bg=c["card"])
        enco_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        tk.Label(enco_frame, text="Test Videos (Encoded)",
                 font=('Arial', 8, 'bold'), bg=c["card"], fg=c["fg"]).pack(anchor=tk.W)

        enco_list_frame = tk.Frame(enco_frame, bg=c["card"])
        enco_list_frame.pack(fill=tk.BOTH, expand=True, pady=(3, 0))

        self._enco_lb = tk.Listbox(
            enco_list_frame, height=7, relief="flat", selectmode=tk.SINGLE,
            font=('Consolas', 8), bg=c["entry_bg"], fg=c["fg"],
            selectbackground=c["accent_green"], selectforeground="white",
            bd=0, highlightthickness=0, activestyle="none"
        )
        enco_vsb = tk.Scrollbar(enco_list_frame, orient=tk.VERTICAL,
                                command=self._enco_lb.yview)
        self._enco_lb.configure(yscrollcommand=enco_vsb.set)
        self._enco_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        enco_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        enco_btn_row = tk.Frame(enco_frame, bg=c["card"])
        enco_btn_row.pack(fill=tk.X, pady=(4, 0))
        tk.Button(
            enco_btn_row, text="📂  Browse…", relief="flat", padx=8, pady=2,
            font=('Arial', 8), cursor="hand2",
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"], bd=0,
            command=lambda: self._browse_multi(self._enco_files, self._enco_lb)
        ).pack(side=tk.LEFT)
        tk.Button(
            enco_btn_row, text="✕ Leeren", relief="flat", padx=6, pady=2,
            font=('Arial', 8), cursor="hand2",
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"], bd=0,
            command=lambda: self._clear_list(self._enco_files, self._enco_lb)
        ).pack(side=tk.LEFT, padx=(6, 0))

        # Paar-Status-Zeile
        self._pair_lbl = tk.Label(
            main, text="", font=('Arial', 8, 'bold'), bg=c["bg"], fg=c["sub_lbl"]
        )
        self._pair_lbl.pack(anchor=tk.W, pady=(2, 0))

        # ── METRIKEN ─────────────────────────────────────────────────────
        tk.Label(main, text="METRIKEN", font=('Arial', 9, 'bold'),
                 bg=c["bg"], fg=c["fg"]).pack(anchor=tk.W, pady=(6, 0))

        mcard = tk.Frame(main, bg=c["card"], padx=14, pady=7,
                         highlightthickness=1, highlightbackground=c["border"])
        mcard.pack(fill=tk.X, pady=(3, 6))

        self._mvars = {}
        mrow = tk.Frame(mcard, bg=c["card"])
        mrow.pack(fill=tk.X)
        for m in ALL_METRICS:
            var = tk.BooleanVar(value=True)
            self._mvars[m] = var
            tk.Checkbutton(mrow, text=m, variable=var,
                           bg=c["card"], fg=c["fg"], selectcolor=c["entry_bg"],
                           activebackground=c["card"], font=('Arial', 8),
                           cursor="hand2").pack(side=tk.LEFT, padx=(0, 12))

        # ── OPTIONEN ─────────────────────────────────────────────────────
        tk.Label(main, text="OPTIONEN", font=('Arial', 9, 'bold'),
                 bg=c["bg"], fg=c["fg"]).pack(anchor=tk.W)

        ocard = tk.Frame(main, bg=c["card"], padx=14, pady=7,
                         highlightthickness=1, highlightbackground=c["border"])
        ocard.pack(fill=tk.X, pady=(3, 8))

        orow = tk.Frame(ocard, bg=c["card"])
        orow.pack(fill=tk.X)

        tk.Label(orow, text="⚡ GPU:", font=('Arial', 8, 'bold'),
                 bg=c["card"], fg=c["fg"]).pack(side=tk.LEFT)
        self._gpu = tk.StringVar(value=self._default_gpu or self._gpu_opt[0])
        gm = tk.OptionMenu(orow, self._gpu, *self._gpu_opt)
        gm.config(font=('Arial', 8), relief="flat", bg=c["btn_secondary"],
                  fg=c["btn_fg"], width=28, anchor="w",
                  highlightthickness=0, bd=0, activebackground=c["act_secondary"])
        gm["menu"].config(bg=c["entry_bg"], fg=c["fg"], relief="flat", tearoff=0,
                          activebackground=c["accent_green"], activeforeground="white")
        gm.pack(side=tk.LEFT, padx=(5, 14))

        tk.Label(orow, text="Subsampling:", font=('Arial', 8),
                 bg=c["card"], fg=c["fg"]).pack(side=tk.LEFT)
        self._sub = tk.StringVar(value="1")
        sm = tk.OptionMenu(orow, self._sub, "1", "2", "4", "8")
        sm.config(font=('Arial', 8), relief="flat", bg=c["btn_secondary"],
                  fg=c["btn_fg"], highlightthickness=0, bd=0,
                  activebackground=c["act_secondary"])
        sm["menu"].config(bg=c["entry_bg"], fg=c["fg"], relief="flat", tearoff=0,
                          activebackground=c["accent_green"], activeforeground="white")
        sm.pack(side=tk.LEFT, padx=(5, 14))

        tk.Label(orow, text="Artefakt-Frames:", font=('Arial', 8),
                 bg=c["card"], fg=c["fg"]).pack(side=tk.LEFT)
        self._art = tk.StringVar(value="1000")
        tk.Entry(orow, textvariable=self._art, width=6, relief="flat",
                 font=('Consolas', 8), justify=tk.CENTER,
                 bg=c["entry_bg"], fg=c["fg"], bd=0,
                 highlightthickness=0).pack(side=tk.LEFT, padx=(5, 4))
        tk.Label(orow, text="(0 = alle)", font=('Arial', 7),
                 bg=c["card"], fg=c["sub_lbl"]).pack(side=tk.LEFT)

        # ── SAVE / CANCEL ─────────────────────────────────────────────────
        self._save_btn_var = tk.StringVar(value="✅  Hinzufügen")
        brow = tk.Frame(main, bg=c["bg"])
        brow.pack(fill=tk.X, pady=(0, 0))
        self._save_btn = tk.Button(
            brow, textvariable=self._save_btn_var,
            relief="flat", padx=15, pady=6,
            font=('Arial', 9, 'bold'), bg=c["accent_green"], fg="white",
            activebackground=c["act_green"], bd=0,
            cursor="hand2", command=self._save
        )
        self._save_btn.pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(brow, text="Abbrechen", relief="flat", padx=15, pady=6,
                  font=('Arial', 9), bg=c["btn_secondary"], fg=c["btn_fg"],
                  activebackground=c["act_secondary"], bd=0,
                  cursor="hand2", command=self.destroy).pack(side=tk.LEFT)

        self._update_pair_info()

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _browse_multi(self, file_list, listbox):
        """Öffnet Mehrfachauswahl-Dialog und füllt die Listbox."""
        files = filedialog.askopenfilenames(filetypes=self._FILETYPES)
        if not files:
            return
        file_list.clear()
        # Reihenfolge: alphabetisch nach Dateiname (konsistent mit Dateisystem-Sortierung)
        file_list.extend(sorted(files, key=lambda p: os.path.basename(p).lower()))
        listbox.delete(0, tk.END)
        for f in file_list:
            listbox.insert(tk.END, os.path.basename(f))
        self._update_pair_info()

    def _clear_list(self, file_list, listbox):
        file_list.clear()
        listbox.delete(0, tk.END)
        self._update_pair_info()

    def _on_solo_toggle(self):
        """Blendet den Original-Bereich bei Solo-Scan aus."""
        if self._solo.get():
            self._orig_frame.grid_remove()
        else:
            self._orig_frame.grid()
        self._update_pair_info()

    def _update_pair_info(self):
        """Aktualisiert die Paar-Status-Anzeige und den Save-Button-Text."""
        c    = self._colors
        solo = self._solo.get()
        n_e  = len(self._enco_files)
        n_o  = len(self._orig_files)

        if n_e == 0:
            self._pair_lbl.config(text="Noch keine Dateien ausgewählt.", fg=c["sub_lbl"])
            self._save_btn_var.set("✅  Hinzufügen")
            return

        if solo:
            self._pair_lbl.config(
                text=f"✅  {n_e} Solo-Job{'s' if n_e != 1 else ''} werden hinzugefügt.",
                fg=c["accent_green"]
            )
            self._save_btn_var.set(f"✅  {n_e} Job{'s' if n_e != 1 else ''} hinzufügen")
        elif n_o == n_e:
            self._pair_lbl.config(
                text=f"✅  {n_e} Paar{'e' if n_e != 1 else ''} werden hinzugefügt  "
                     f"(Original 1↔Encoded 1, Original 2↔Encoded 2 …)",
                fg=c["accent_green"]
            )
            self._save_btn_var.set(f"✅  {n_e} Job{'s' if n_e != 1 else ''} hinzufügen")
        else:
            self._pair_lbl.config(
                text=f"⚠️  Anzahl stimmt nicht überein – "
                     f"{n_o} Original{'s' if n_o != 1 else ''} / "
                     f"{n_e} Encoded",
                fg=c["accent_red"]
            )
            self._save_btn_var.set("✅  Hinzufügen")

    def _save(self):
        solo = self._solo.get()
        n_e  = len(self._enco_files)
        n_o  = len(self._orig_files)

        if n_e == 0:
            messagebox.showwarning("Keine Encoded",
                                   "Bitte mind. eine Encoded-Datei auswählen.", parent=self)
            return
        if not solo and n_o == 0:
            messagebox.showwarning("Keine Originals",
                                   "Bitte Original-Dateien auswählen\n"
                                   "oder Solo-Scan aktivieren.", parent=self)
            return
        if not solo and n_o != n_e:
            messagebox.showwarning(
                "Anzahl stimmt nicht",
                f"Es müssen gleich viele Originals ({n_o}) und\n"
                f"Encoded-Dateien ({n_e}) ausgewählt sein.", parent=self
            )
            return

        active_m = {m for m, v in self._mvars.items() if v.get()}
        if not active_m:
            messagebox.showwarning("Keine Metrik",
                                   "Mindestens eine Metrik auswählen.", parent=self)
            return

        art = 1000
        if self._art.get().isdigit():
            art = int(self._art.get())

        jobs = []
        for i, enco in enumerate(self._enco_files):
            jobs.append({
                "original":        "" if solo else self._orig_files[i],
                "encoded":         enco,
                "solo_mode":       solo,
                "metrics":         active_m,
                "subsample":       self._sub.get(),
                "artifact_frames": art,
                "gpu_var":         self._gpu.get(),
            })

        self._cb(jobs)
        self.destroy()
