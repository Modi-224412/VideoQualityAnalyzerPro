import tkinter as tk
from tkinter import scrolledtext
from tkinter.ttk import Progressbar
import os
import platform
from modules.path_utils import BASE_PATH


def build_ui(app):
    # Icon setzen – verhindert das Standard-Feder-Icon in der Taskleiste
    _apply_icon(app)
    _build_header(app)
    _build_tab_bar(app)

    # ── Analyse-Inhalt in eigenem Container ──────────────────────────────
    app.analyse_frame = tk.Frame(app.root)
    app.analyse_frame.pack(fill=tk.X)

    _build_file_card(app, app.analyse_frame)
    _build_player_card(app, app.analyse_frame)
    _build_metrics_card(app, app.analyse_frame)
    _build_access_card(app, app.analyse_frame)
    _build_options_card(app, app.analyse_frame)
    _build_actions(app, app.analyse_frame)

    # ── Queue-Inhalt (startet versteckt) ─────────────────────────────────
    from modules.ui.queue_builder import build_queue_ui
    build_queue_ui(app)

    # ── Immer sichtbar: Progress + Console ───────────────────────────────
    _build_progress(app)
    _build_console(app)


def _apply_icon(app):
    """Setzt icon.ico als Fenster- und Taskleisten-Icon."""
    try:
        icon_path = os.path.join(BASE_PATH, "icon.ico")
        if os.path.exists(icon_path) and platform.system() == "Windows":
            app.root.iconbitmap(default=icon_path)
    except Exception:
        pass  # Icon ist kosmetisch – Fehler nie crashen lassen


def _build_header(app):
    app.header_frame = tk.Frame(app.root, height=60)
    app.header_frame.pack(fill=tk.X, pady=(0, 0))

    app.title_label = tk.Label(
        app.header_frame,
        text="VIDEO QUALITY ANALYZER PRO",
        font=('Helvetica', 18, 'bold')
    )
    app.title_label.pack(side=tk.LEFT, padx=30, pady=15)

    app.theme_btn = tk.Button(
        app.header_frame,
        command=app.toggle_theme,
        relief="flat", padx=10,
        font=('Arial', 8, 'bold'),
        cursor="hand2",
        width=18,
        anchor="center"
    )
    app.theme_btn.pack(side=tk.RIGHT, padx=30, pady=15)


def _build_tab_bar(app):
    """Tab-Navigationsleiste zwischen Header und Inhalt."""
    app.tab_bar = tk.Frame(app.root, height=38)
    app.tab_bar.pack(fill=tk.X, padx=25, pady=(4, 0))

    app._active_tab  = "analyse"
    app._tab_buttons = {}

    tab_specs = [
        ("analyse", "🔬  ANALYSE"),
        ("queue",   "📋  MEHRFACHANALYSE"),
    ]
    for tab_id, label in tab_specs:
        btn = tk.Button(
            app.tab_bar,
            text=label,
            font=('Arial', 9, 'bold'),
            relief="flat",
            padx=16, pady=6,
            cursor="hand2",
            command=lambda t=tab_id: app.switch_tab(t),
        )
        btn.pack(side=tk.LEFT, padx=(0, 4))
        app._tab_buttons[tab_id] = btn

    # Trennlinie unter der Tab-Bar
    app.tab_separator = tk.Frame(app.root, height=1)
    app.tab_separator.pack(fill=tk.X, padx=25, pady=(4, 4))


def _build_file_card(app, parent):
    app.file_card = tk.Frame(parent, padx=20, pady=10, highlightthickness=1)
    app.file_card.pack(pady=5, padx=25, fill=tk.X)

    app.lbl_orig = tk.Label(
        app.file_card,
        text="Reference Video (Original)",
        font=('Arial', 9, 'bold')
    )
    app.lbl_orig.pack(anchor=tk.W)

    app.orig_inner = tk.Frame(app.file_card)
    app.orig_inner.pack(fill=tk.X, pady=(2, 5))
    app.original = tk.Entry(app.orig_inner, width=90, relief="flat", font=('Consolas', 9))
    app.original.pack(side=tk.LEFT, ipady=3)
    app.btn_b1 = tk.Button(
        app.orig_inner, text="Browse...", relief="flat", padx=10,
        command=lambda: app.browse(app.original)
    )
    app.btn_b1.pack(side=tk.LEFT, padx=10)

    app.lbl_enco = tk.Label(
        app.file_card,
        text="Test Video (Encoded)",
        font=('Arial', 9, 'bold')
    )
    app.lbl_enco.pack(anchor=tk.W, pady=(5, 0))

    app.enco_inner = tk.Frame(app.file_card)
    app.enco_inner.pack(fill=tk.X, pady=(2, 2))
    app.encoded = tk.Entry(app.enco_inner, width=90, relief="flat", font=('Consolas', 9))
    app.encoded.pack(side=tk.LEFT, ipady=3)
    app.btn_b2 = tk.Button(
        app.enco_inner, text="Browse...", relief="flat", padx=10,
        command=lambda: app.browse(app.encoded)
    )
    app.btn_b2.pack(side=tk.LEFT, padx=10)

    # Solo-Scan Zeile
    app.solo_row = tk.Frame(app.file_card)
    app.solo_row.pack(fill=tk.X, pady=(10, 4))

    app.solo_hint = tk.Label(
        app.solo_row,
        text="Kein Original? →",
        font=('Arial', 8)
    )
    app.solo_hint.pack(side=tk.LEFT)

    app.btn_solo = tk.Button(
        app.solo_row,
        text="🔍  SOLO-SCAN  (referenzlos)",
        command=app.start_solo_scan,
        relief="flat",
        font=('Arial', 8, 'bold'),
        padx=12, pady=3,
        cursor="hand2"
    )
    app.btn_solo.pack(side=tk.LEFT, padx=(6, 0))

    app.solo_desc = tk.Label(
        app.solo_row,
        text="  –  misst Bitrate, Artefakte, Frame-Drops & Audio direkt am Encode",
        font=('Arial', 7)
    )
    app.solo_desc.pack(side=tk.LEFT)


def _build_player_card(app, parent):
    app.player_card = tk.Frame(parent, padx=20, pady=10, highlightthickness=1)
    app.player_card.pack(pady=5, padx=25, fill=tk.X)

    app.lbl_player = tk.Label(
        app.player_card,
        text="INDIVIDUAL PLAYER CONTROL",
        font=('Arial', 9, 'bold')
    )
    app.lbl_player.pack(anchor=tk.W, pady=(0, 5))

    app.play_btn_frame = tk.Frame(app.player_card)
    app.play_btn_frame.pack(fill=tk.X)

    app.btn_play_orig = tk.Button(
        app.play_btn_frame, text="▶ PLAY REFERENCE", width=20,
        relief="flat", font=('Arial', 8, 'bold'),
        command=lambda: app.player.play_single(
            app.original.get(), parent=app.root
        )
    )
    app.btn_play_orig.pack(side=tk.LEFT, padx=5)

    app.btn_play_enco = tk.Button(
        app.play_btn_frame, text="▶ PLAY ENCODED", width=20,
        relief="flat", font=('Arial', 8, 'bold'),
        command=lambda: app.player.play_single(
            app.encoded.get(), parent=app.root
        )
    )
    app.btn_play_enco.pack(side=tk.LEFT, padx=5)

    app.btn_player = tk.Button(
        app.play_btn_frame, text="📺 COMPARISON PLAYER", width=25,
        relief="flat", font=('Arial', 8, 'bold'),
        command=lambda: app.player.play_comparison(
            app.original.get(), app.encoded.get(), parent=app.root,
            offset_sec=app.offset_var.get(),
            offset_callback=app._on_player_offset_update,
        )
    )
    app.btn_player.pack(side=tk.RIGHT, padx=5)


def _build_metrics_card(app, parent):
    from modules.ui.metric_info_popup import MetricInfoPopup
    app.method_card = tk.Frame(parent, padx=20, pady=10, highlightthickness=1)
    app.method_card.pack(pady=5, padx=25, fill=tk.X)

    app.lbl_metrics = tk.Label(
        app.method_card,
        text="ACTIVE METRICS OVERVIEW",
        font=('Arial', 10, 'bold')
    )
    app.lbl_metrics.pack(anchor=tk.W, pady=(0, 8))

    app.status_frame = tk.Frame(app.method_card)
    app.status_frame.pack(fill=tk.X)

    # Speichert alle ? Buttons für Theme-Updates
    app.info_buttons = []

    for text in ["VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"]:
        # Äußerer Container pro Metrik
        container = tk.Frame(app.status_frame, padx=8, pady=4)
        container.pack(side=tk.LEFT, padx=(0, 10))

        # Badge-Bereich (●  LABEL) – klickbar zum Aktivieren/Deaktivieren
        badge_area = tk.Frame(container)
        badge_area.pack(side=tk.LEFT)

        dot = tk.Label(badge_area, text="●", font=('Arial', 8))
        dot.pack(side=tk.LEFT)

        lbl = tk.Label(badge_area, text=f" {text}", font=('Arial', 8, 'bold'))
        lbl.pack(side=tk.LEFT)

        app.badges.append((container, dot, lbl))

        for widget in (container, badge_area, dot, lbl):
            widget.bind("<Button-1>", lambda e, m=text: app.toggle_metric(m))
            widget.config(cursor="hand2")

        # ? Info-Button – kleiner, dezent, separates Binding
        info_btn = tk.Button(
            container,
            text="?",
            font=('Arial', 7, 'bold'),
            width=2,
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=2, pady=0,
            command=lambda m=text: MetricInfoPopup(
                app.root, m, app.theme.get()
            )
        )
        info_btn.pack(side=tk.LEFT, padx=(3, 0))
        app.info_buttons.append(info_btn)


def _build_access_card(app, parent):
    from modules.ui.metric_info_popup import HeatmapInfoPopup

    app.access_card = tk.Frame(parent, padx=20, pady=10, highlightthickness=1)
    app.access_card.pack(pady=5, padx=25, fill=tk.X)

    app.lbl_access = tk.Label(
        app.access_card,
        text="QUICK ACCESS",
        font=('Arial', 9, 'bold')
    )
    app.lbl_access.pack(anchor=tk.W, pady=(0, 5))

    app.nav_btn_frame = tk.Frame(app.access_card)
    app.nav_btn_frame.pack(fill=tk.X)

    btn_data = [
        ("📂 Reports",     "reports"),
        ("📸 Screenshots", "screenshots"),
        ("🔥 Heatmaps",    "heatmaps"),
        ("🗑️ Clear Cache", "clear"),
    ]
    for t, key in btn_data:
        if key == "heatmaps":
            heatmap_box = tk.Frame(app.nav_btn_frame, padx=0, pady=0)
            heatmap_box.pack(side=tk.LEFT, padx=5)
            app.heatmap_box = heatmap_box

            heatmap_btn = tk.Button(
                heatmap_box, text=t, width=12,
                command=lambda: app.open_dir("heatmaps"),
                relief="flat", font=('Arial', 9)
            )
            heatmap_btn.pack(side=tk.LEFT)
            app.nav_btns.append((heatmap_btn, key))

            app.heatmap_info_btn = tk.Button(
                heatmap_box,
                text="?",
                font=('Arial', 7, 'bold'),
                width=2,
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=1, pady=0,
                command=lambda: HeatmapInfoPopup(app.root, app.theme.get())
            )
            app.heatmap_info_btn.pack(side=tk.LEFT, padx=(0, 0))
        else:
            cmd = app.clear_cache if key == "clear" else (lambda k=key: app.open_dir(k))
            btn = tk.Button(
                app.nav_btn_frame, text=t, width=15,
                command=cmd, relief="flat", font=('Arial', 9)
            )
            btn.pack(side=tk.RIGHT if key == "clear" else tk.LEFT, padx=5)
            app.nav_btns.append((btn, key))


def _build_options_card(app, parent):
    app.option_card = tk.Frame(parent, padx=20, pady=15, highlightthickness=1)
    app.option_card.pack(pady=5, padx=25, fill=tk.X)

    # ── Einzige Zeile: GPU + Subsampling + Artefakt-Frames ────────────────
    app.gpu_row = tk.Frame(app.option_card)
    app.gpu_row.pack(fill=tk.X)
    app.opt_grid = app.gpu_row   # Alias – theme_engine und andere nutzen opt_grid

    app.gpu_lbl = tk.Label(
        app.gpu_row,
        text="⚡ GPU:",
        font=('Arial', 8, 'bold')
    )
    app.gpu_lbl.pack(side=tk.LEFT)

    app.gpu_var = tk.StringVar(value="🖥️  Kein GPU  (CPU)")
    app.gpu_menu = tk.OptionMenu(app.gpu_row, app.gpu_var, "🖥️  Kein GPU  (CPU)")
    app.gpu_menu.config(font=('Arial', 8), relief="flat", width=42, anchor="w")
    app.gpu_menu.pack(side=tk.LEFT, padx=(6, 0))

    app.sub_label = tk.Label(
        app.gpu_row,
        text=" | VMAF SUBSAMPLING:",
        font=('Arial', 8)
    )
    app.sub_label.pack(side=tk.LEFT, padx=(10, 5))

    app.subsample_var = tk.StringVar(value="1")
    app.sub_menu = tk.OptionMenu(app.opt_grid, app.subsample_var, "1", "2", "4", "8")
    app.sub_menu.pack(side=tk.LEFT)

    # ? Info-Button für Subsampling
    from modules.ui.metric_info_popup import SubsampleInfoPopup
    app.sub_info_btn = tk.Button(
        app.opt_grid,
        text="?",
        font=('Arial', 7, 'bold'),
        width=2,
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=2, pady=0,
        command=lambda: SubsampleInfoPopup(app.root, app.theme.get())
    )
    app.sub_info_btn.pack(side=tk.LEFT, padx=(4, 0))
    app.info_buttons.append(app.sub_info_btn)

    # Artefakt-Scan Frames
    app.art_frames_label = tk.Label(
        app.opt_grid,
        text=" | ARTEFAKT-FRAMES:",
        font=('Arial', 8)
    )
    app.art_frames_label.pack(side=tk.LEFT, padx=(10, 5))

    _saved_frames = str(app.config_mgr.load().get("artifact_frames", 1000))
    app.art_frames_var = tk.StringVar(value=_saved_frames)

    app.art_frames_entry = tk.Entry(
        app.opt_grid,
        textvariable=app.art_frames_var,
        width=6,
        relief="flat",
        font=('Consolas', 9),
        justify=tk.CENTER
    )
    app.art_frames_entry.pack(side=tk.LEFT)

    app.art_frames_hint = tk.Label(
        app.opt_grid,
        text="(0 = alle)",
        font=('Arial', 7),
    )
    app.art_frames_hint.pack(side=tk.LEFT, padx=(4, 0))

    def _save_art_frames(*_):
        val = app.art_frames_var.get()
        if val.isdigit():
            cfg = app.config_mgr.load()
            cfg["artifact_frames"] = int(val)
            app.config_mgr.save(cfg)

    app.art_frames_var.trace_add("write", _save_art_frames)

    # Video-Versatz: nur im Comparison-Player einstellbar
    app.offset_var = tk.DoubleVar(value=0.0)


def _build_actions(app, parent):
    app.main_actions = tk.Frame(parent)
    app.main_actions.pack(pady=10, padx=25, fill=tk.X)

    app.btn_start = tk.Button(
        app.main_actions,
        text="🚀 START ANALYSIS",
        command=app.start_analysis,
        height=2,
        width=20,
        font=('Arial', 11, 'bold'),
        relief="flat"
    )
    app.btn_start.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

    app.btn_abort = tk.Button(
        app.main_actions,
        text="🛑 STOP",
        command=app.stop_analysis,
        height=2,
        width=20,
        font=('Arial', 11, 'bold'),
        relief="flat"
    )
    app.btn_abort.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))


def _build_progress(app):
    app.progress_frame = tk.Frame(app.root)
    app.progress_frame.pack(pady=5, padx=25, fill=tk.X)

    app.progress = Progressbar(
        app.progress_frame, length=700, mode='determinate'
    )
    app.progress.pack(fill=tk.X)

    app.progress_label = tk.Label(
        app.progress_frame,
        text="Engine Status: Idle",
        font=('Arial', 9)
    )
    app.progress_label.pack()


def _build_console(app):
    app.console_frame = tk.Frame(app.root, highlightthickness=1)
    app.console_frame.pack(pady=5, padx=25, fill=tk.BOTH, expand=True)

    # Kopfzeile: Label links, Copy-Button rechts
    app.console_header = tk.Frame(app.console_frame)
    app.console_header.pack(fill=tk.X, padx=4, pady=(4, 0))

    tk.Label(
        app.console_header,
        text="ENGINE LOG",
        font=('Arial', 8, 'bold')
    ).pack(side=tk.LEFT)

    app.copy_log_btn = tk.Button(
        app.console_header,
        text="📋 Copy Log",
        command=app.copy_log_to_clipboard,
        relief="flat", bd=0, highlightthickness=0,
        font=('Arial', 8),
        padx=6, pady=1,
        cursor="hand2"
    )
    app.copy_log_btn.pack(side=tk.RIGHT)

    app.console = scrolledtext.ScrolledText(
        app.console_frame, width=125, height=6,
        font=('Consolas', 9), relief="flat",
        state='disabled', cursor="arrow"
    )
    app.console.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
    # Selektion visuell deaktivieren
    app.console.bind("<Double-Button-1>", lambda e: "break")
    app.console.bind("<Triple-Button-1>", lambda e: "break")
    app.console.bind("<B1-Motion>", lambda e: "break")
