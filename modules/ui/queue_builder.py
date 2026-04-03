"""
Baut die Queue-Tab UI und stellt apply_queue_theme() bereit.
"""

import tkinter as tk
from tkinter import ttk


def build_queue_ui(app):
    """Erstellt queue_frame (zunächst versteckt) mit allen Queue-Widgets."""
    app.queue_frame = tk.Frame(app.root)
    # Startet versteckt – wird per switch_tab() eingeblendet

    _build_toolbar(app)
    _build_gpu_row(app)
    _build_list_card(app)
    _build_queue_actions(app)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_toolbar(app):
    app.queue_toolbar = tk.Frame(app.queue_frame, padx=18, pady=7,
                                 highlightthickness=1)
    app.queue_toolbar.pack(pady=(5, 0), padx=25, fill=tk.X)

    app.queue_toolbar_title = tk.Label(
        app.queue_toolbar, text="MEHRFACHANALYSE",
        font=('Arial', 10, 'bold')
    )
    app.queue_toolbar_title.pack(side=tk.LEFT, padx=(0, 18))

    btn_specs = [
        ("+ Hinzufügen", "add",    lambda: app.queue_add_job()),
        ("✎ Bearbeiten", "edit",   lambda: app.queue_edit_job()),
        ("✕ Entfernen",  "remove", lambda: app.queue_remove_job()),
        ("↑",            "up",     lambda: app.queue_move_up()),
        ("↓",            "down",   lambda: app.queue_move_down()),
        ("🗑 Leeren",    "clear",  lambda: app.queue_clear()),
    ]
    app.queue_toolbar_btns = []
    for text, key, cmd in btn_specs:
        btn = tk.Button(
            app.queue_toolbar, text=text, relief="flat",
            padx=9, pady=3, font=('Arial', 8, 'bold'),
            cursor="hand2", command=cmd
        )
        btn.pack(side=tk.LEFT, padx=(0, 4))
        app.queue_toolbar_btns.append((btn, key))

    app.queue_count_label = tk.Label(
        app.queue_toolbar, text="0 Jobs", font=('Arial', 8)
    )
    app.queue_count_label.pack(side=tk.RIGHT)


def _build_gpu_row(app):
    """GPU-Auswahlzeile direkt im Queue-Tab (teilt app.gpu_var mit Analyse-Tab)."""
    app.queue_gpu_card = tk.Frame(app.queue_frame, padx=18, pady=8,
                                   highlightthickness=1)
    app.queue_gpu_card.pack(pady=(0, 0), padx=25, fill=tk.X)

    app.queue_gpu_lbl = tk.Label(
        app.queue_gpu_card, text="⚡ GPU:",
        font=('Arial', 8, 'bold')
    )
    app.queue_gpu_lbl.pack(side=tk.LEFT)

    # Nutzt dieselbe gpu_var wie der Analyse-Tab → bleibt automatisch synchron
    app.queue_gpu_menu = tk.OptionMenu(
        app.queue_gpu_card, app.gpu_var, "🖥️  Kein GPU  (CPU)"
    )
    app.queue_gpu_menu.config(
        font=('Arial', 8), relief="flat", width=42, anchor="w"
    )
    app.queue_gpu_menu.pack(side=tk.LEFT, padx=(6, 14))

    app.queue_gpu_apply_btn = tk.Button(
        app.queue_gpu_card,
        text="↻  Auf alle Jobs anwenden",
        relief="flat", padx=10, pady=2,
        font=('Arial', 8, 'bold'),
        cursor="hand2",
        command=lambda: app.queue_apply_gpu_to_all(),
    )
    app.queue_gpu_apply_btn.pack(side=tk.LEFT)

    app.queue_gpu_hint = tk.Label(
        app.queue_gpu_card,
        text="  (neue Jobs übernehmen die Auswahl automatisch)",
        font=('Arial', 7)
    )
    app.queue_gpu_hint.pack(side=tk.LEFT, padx=(4, 0))


def _build_list_card(app):
    app.queue_list_card = tk.Frame(app.queue_frame, padx=8, pady=8,
                                   highlightthickness=1)
    app.queue_list_card.pack(pady=5, padx=25, fill=tk.X)

    cols = ("nr", "encoded", "original", "modus", "metriken", "status")
    app.queue_tree = ttk.Treeview(
        app.queue_list_card, columns=cols, show="headings",
        height=9, selectmode="browse"
    )

    app.queue_tree.heading("nr",       text="#",        anchor=tk.W)
    app.queue_tree.heading("encoded",  text="Encoded",  anchor=tk.W)
    app.queue_tree.heading("original", text="Original", anchor=tk.W)
    app.queue_tree.heading("modus",    text="Modus",    anchor=tk.CENTER)
    app.queue_tree.heading("metriken", text="Metriken", anchor=tk.W)
    app.queue_tree.heading("status",   text="Status",   anchor=tk.CENTER)

    app.queue_tree.column("nr",       width=32,  minwidth=28,  stretch=False)
    app.queue_tree.column("encoded",  width=210, minwidth=90)
    app.queue_tree.column("original", width=190, minwidth=90)
    app.queue_tree.column("modus",    width=80,  minwidth=60,  stretch=False)
    app.queue_tree.column("metriken", width=310, minwidth=100)
    app.queue_tree.column("status",   width=115, minwidth=80,  stretch=False)

    vsb = ttk.Scrollbar(app.queue_list_card, orient=tk.VERTICAL,
                         command=app.queue_tree.yview)
    app.queue_tree.configure(yscrollcommand=vsb.set)
    app.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    app.queue_tree.bind("<Double-Button-1>", lambda _e: app.queue_edit_job())


def _build_queue_actions(app):
    app.queue_actions_frame = tk.Frame(app.queue_frame)
    app.queue_actions_frame.pack(pady=(4, 8), padx=25, fill=tk.X)

    app.btn_queue_start = tk.Button(
        app.queue_actions_frame,
        text="🚀  MEHRFACHANALYSE STARTEN",
        command=app.queue_start,
        height=2, font=('Arial', 11, 'bold'), relief="flat"
    )
    app.btn_queue_start.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

    app.btn_queue_stop = tk.Button(
        app.queue_actions_frame,
        text="🛑 STOP",
        command=app.queue_stop,
        height=2, font=('Arial', 11, 'bold'), relief="flat"
    )
    app.btn_queue_stop.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))


# ─────────────────────────────────────────────────────────────────────────────
# THEME
# ─────────────────────────────────────────────────────────────────────────────

def apply_queue_theme(app, c):
    """Wendet das aktuelle Theme auf alle Queue-Widgets an."""
    if not hasattr(app, 'queue_frame'):
        return

    app.queue_frame.configure(bg=c["bg"])

    # Toolbar
    app.queue_toolbar.configure(bg=c["card"], highlightbackground=c["border"])
    app.queue_toolbar_title.configure(bg=c["card"], fg=c["fg"])
    app.queue_count_label.configure(bg=c["card"], fg=c["sub_lbl"])

    for btn, key in app.queue_toolbar_btns:
        if key == "add":
            btn.configure(bg=c["accent_green"], fg="white",
                          activebackground=c["act_green"], bd=0, highlightthickness=0)
        elif key == "clear":
            btn.configure(bg=c["accent_red"], fg="white",
                          activebackground=c["act_red"], bd=0, highlightthickness=0)
        else:
            btn.configure(bg=c["btn_secondary"], fg=c["btn_fg"],
                          activebackground=c["act_secondary"], bd=0, highlightthickness=0)

    # GPU-Zeile
    if hasattr(app, 'queue_gpu_card'):
        app.queue_gpu_card.configure(bg=c["card"], highlightbackground=c["border"])
        app.queue_gpu_lbl.configure(bg=c["card"], fg=c["fg"])
        app.queue_gpu_hint.configure(bg=c["card"], fg=c["sub_lbl"])
        app.queue_gpu_apply_btn.configure(
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"], bd=0, highlightthickness=0
        )
        app.queue_gpu_menu.configure(
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"],
            highlightthickness=0, bd=0, relief="flat"
        )
        app.queue_gpu_menu["menu"].config(
            bg=c["entry_bg"], fg=c["fg"],
            activebackground=c["accent_green"],
            activeforeground="white",
            relief="flat", borderwidth=0, tearoff=0
        )

    # List card
    app.queue_list_card.configure(bg=c["card"], highlightbackground=c["border"])

    # Treeview style
    style = ttk.Style()
    style.configure("Queue.Treeview",
                    background=c["entry_bg"],
                    fieldbackground=c["entry_bg"],
                    foreground=c["fg"],
                    rowheight=24,
                    borderwidth=0,
                    relief="flat")
    style.configure("Queue.Treeview.Heading",
                    background=c["card"],
                    foreground=c["fg"],
                    relief="flat",
                    borderwidth=0)
    style.map("Queue.Treeview",
              background=[("selected", c["accent_green"])],
              foreground=[("selected", "white")])
    app.queue_tree.configure(style="Queue.Treeview")

    # Row tags für Status-Farben
    app.queue_tree.tag_configure("tag_pending",
                                 foreground=c["fg"])
    app.queue_tree.tag_configure("tag_running",
                                 foreground=c["accent_blue"])
    app.queue_tree.tag_configure("tag_done",
                                 foreground=c["accent_green"])
    app.queue_tree.tag_configure("tag_error",
                                 foreground=c["accent_red"])

    # Queue actions
    app.queue_actions_frame.configure(bg=c["bg"])
    app.btn_queue_start.configure(bg=c["accent_green"], fg="white",
                                   activebackground=c["act_green"],
                                   bd=0, highlightthickness=0)
    app.btn_queue_stop.configure(bg=c["accent_red"], fg="white",
                                  activebackground=c["act_red"],
                                  bd=0, highlightthickness=0)
