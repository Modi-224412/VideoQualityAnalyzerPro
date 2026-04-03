import platform
import tkinter as tk
from tkinter.ttk import Style


# Plattformgerechte Schriftarten – Fallback für Linux Mint / Ubuntu
def _resolve_fonts():
    """Gibt (sans, mono) als Schriftfamilien zurück, die auf der aktuellen Plattform verfügbar sind."""
    if platform.system() == "Linux":
        return "DejaVu Sans", "DejaVu Sans Mono"
    return "Arial", "Consolas"

FONT_SANS, FONT_MONO = _resolve_fonts()


class ThemeEngine:
    def __init__(self):
        self.dark_mode = False
        self.colors = {
            "dark": {
                "bg":           "#1e1e1e",
                "card":         "#2d2d2d",
                "header":       "#181818",
                "fg":           "#f0f0f0",
                "entry_bg":     "#3d3d3d",
                "accent_green": "#2ecc71",
                "accent_blue":  "#3498db",
                "accent_red":   "#e74c3c",
                "border":       "#444",
                "select":       "#333",
                "console_bg":   "#121212",
                "console_fg":   "#00ff00",
                "btn_secondary":"#444",
                "btn_fg":       "white",
                "act_green":    "#219150",
                "act_red":      "#a93226",
                "act_secondary":"#555",
                "title_color":  "#2ecc71",
                "sub_lbl":      "#888888",
            },
            "light": {
                "bg":           "#f0f2f5",
                "card":         "#ffffff",
                "header":       "#ffffff",
                "fg":           "#2c3e50",
                "entry_bg":     "#e9ecef",
                "accent_green": "#27ae60",
                "accent_blue":  "#2980b9",
                "accent_red":   "#c0392b",
                "border":       "#dcdde1",
                "select":       "#ffffff",
                "console_bg":   "#ffffff",
                "console_fg":   "#2c3e50",
                "btn_secondary":"#e0e0e0",
                "btn_fg":       "#2c3e50",
                "act_green":    "#219150",
                "act_red":      "#a93226",
                "act_secondary":"#d5d8dc",
                "title_color":  "#2c3e50",
                "sub_lbl":      "#888888",
            }
        }

    # ─────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────

    def toggle(self):
        self.dark_mode = not self.dark_mode

    def get(self):
        return self.colors["dark"] if self.dark_mode else self.colors["light"]

    def update_ttk_styles(self, style_obj):
        c = self.get()
        try:
            style_obj.theme_use('clam')
        except Exception:
            pass

        # Progressbars
        style_obj.configure(
            "Green.Horizontal.TProgressbar",
            foreground=c["accent_green"],
            background=c["accent_green"],
            troughcolor=c["entry_bg"],
            bordercolor=c["bg"],
            thickness=15
        )
        style_obj.configure(
            "Red.Horizontal.TProgressbar",
            foreground=c["accent_red"],
            background=c["accent_red"],
            troughcolor=c["entry_bg"],
            bordercolor=c["bg"],
            thickness=15
        )
        style_obj.configure(
            "Blue.Horizontal.TProgressbar",
            foreground=c["accent_blue"],
            background=c["accent_blue"],
            troughcolor=c["entry_bg"],
            bordercolor=c["bg"],
            thickness=15
        )

        # Scrollbars – sorgt für konsistentes Aussehen auf Linux (sonst GTK-Theme)
        for orientation in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style_obj.configure(
                orientation,
                background=c["btn_secondary"],
                troughcolor=c["bg"],
                bordercolor=c["bg"],
                arrowcolor=c["fg"],
                relief="flat",
                borderwidth=0,
            )
            style_obj.map(
                orientation,
                background=[("active", c["act_secondary"]), ("disabled", c["bg"])],
            )

        # Scale – wird im Player genutzt (Timeline)
        style_obj.configure(
            "Horizontal.TScale",
            background=c["bg"],
            troughcolor=c["entry_bg"],
            bordercolor=c["bg"],
        )

    def apply(self, app):
        from modules.ui.queue_builder import apply_queue_theme
        c  = self.get()
        fg = c["fg"]

        # Root & Header
        app.root.configure(bg=c["bg"])
        app.header_frame.configure(bg=c["header"])
        app.title_label.configure(bg=c["header"], fg=c["title_color"])

        # Theme Button
        btn_text = "☀️ LIGHT MODE" if self.dark_mode else "🌙  DARK MODE"
        app.theme_btn.configure(
            text=btn_text,
            bg=c["btn_secondary"], fg=c["btn_fg"],
            activebackground=c["act_secondary"],
            bd=0, highlightthickness=0,
        )

        # Main Actions Frame
        app.main_actions.configure(bg=c["bg"])

        # Cards
        for card in [
            app.file_card, app.player_card, app.method_card,
            app.access_card, app.option_card, app.console_frame
        ]:
            card.configure(bg=c["card"], highlightbackground=c["border"])

        # Inner Frames
        for inner in [
            app.orig_inner, app.enco_inner, app.play_btn_frame,
            app.status_frame, app.nav_btn_frame, app.opt_grid
        ]:
            inner.configure(bg=c["card"])

        # Labels
        for lbl in [app.lbl_orig, app.lbl_enco, app.lbl_player,
                    app.lbl_metrics, app.lbl_access]:
            lbl.configure(bg=c["card"], fg=fg)

        # Sub-Label
        app.sub_label.configure(bg=c["card"], fg=c["sub_lbl"])

        # Artefakt-Frames Label, Entry & Hint
        if hasattr(app, 'art_frames_label'):
            app.art_frames_label.configure(bg=c["card"], fg=c["sub_lbl"])
        if hasattr(app, 'art_frames_hint'):
            app.art_frames_hint.configure(bg=c["card"], fg=c["sub_lbl"])
        if hasattr(app, 'art_frames_entry'):
            app.art_frames_entry.configure(
                bg=c["entry_bg"], fg=c["fg"], insertbackground=c["fg"],
                bd=0, highlightthickness=0,
            )

        # Solo-Scan Zeile
        if hasattr(app, 'solo_row'):
            app.solo_row.configure(bg=c["card"])
        if hasattr(app, 'solo_hint'):
            app.solo_hint.configure(bg=c["card"], fg=c["sub_lbl"])
        if hasattr(app, 'solo_desc'):
            app.solo_desc.configure(bg=c["card"], fg=c["sub_lbl"])
        if hasattr(app, 'btn_solo'):
            app.btn_solo.configure(
                bg="#8e44ad", fg="white",
                activebackground="#7d3c98",
                bd=0, highlightthickness=0,
            )

        # Badges
        for container, dot, lbl in app.badges:
            container.configure(bg=c["entry_bg"])
            dot.configure(bg=c["entry_bg"], fg=c["accent_green"])
            lbl.configure(bg=c["entry_bg"], fg=fg)

        # Info-Buttons (?)
        sub_btn_bg = c["card"] if self.dark_mode else c["console_bg"]
        for btn in getattr(app, 'info_buttons', []):
            is_sub = btn is getattr(app, 'sub_info_btn', None)
            bg = sub_btn_bg if is_sub else c["entry_bg"]
            btn.configure(
                bg=bg, fg=c["accent_green"],
                activebackground=bg, activeforeground=c["accent_green"],
                bd=0, highlightthickness=0,
            )

        # Nav Buttons
        for btn, key in app.nav_btns:
            is_clear = key == "clear"
            btn.configure(
                bg="#f39c12" if is_clear else c["btn_secondary"],
                fg="white" if is_clear else c["btn_fg"],
                activebackground="#d35400" if is_clear else c["act_secondary"],
                bd=0, highlightthickness=0,
            )

        # Heatmap ? Button
        if hasattr(app, 'heatmap_info_btn'):
            app.heatmap_info_btn.configure(
                bg=c["btn_secondary"],
                fg=c["accent_green"],
                activebackground=c["btn_secondary"],
                activeforeground=c["accent_green"],
                bd=0, highlightthickness=0,
            )
        if hasattr(app, 'heatmap_box'):
            app.heatmap_box.configure(bg=c["btn_secondary"])

        # Player Buttons
        for btn in [app.btn_play_orig, app.btn_play_enco, app.btn_b1, app.btn_b2]:
            btn.configure(
                bg=c["btn_secondary"],
                fg=c["btn_fg"],
                activebackground=c["act_secondary"],
                bd=0, highlightthickness=0,
            )

        # Haupt-Aktions-Buttons
        app.btn_player.configure(
            bg=c["accent_blue"], fg="white",
            activebackground="#21618c",
            bd=0, highlightthickness=0,
        )
        app.btn_start.configure(
            bg=c["accent_green"], fg="white",
            activebackground=c["act_green"],
            bd=0, highlightthickness=0,
        )
        app.btn_abort.configure(
            bg=c["accent_red"], fg="white",
            activebackground=c["act_red"],
            bd=0, highlightthickness=0,
        )

        # Eingabefelder
        for entry in [app.original, app.encoded]:
            entry.configure(
                bg=c["entry_bg"], fg=fg, insertbackground=fg,
                bd=0, highlightthickness=0,
            )

        # GPU Auswahl
        if hasattr(app, 'gpu_lbl'):
            app.gpu_lbl.configure(bg=c["card"], fg=fg)
        if hasattr(app, 'gpu_menu'):
            app.gpu_menu.configure(
                bg=c["btn_secondary"], fg=c["btn_fg"],
                activebackground=c["act_secondary"],
                highlightthickness=0, bd=0, relief="flat"
            )
            app.gpu_menu["menu"].config(
                bg=c["entry_bg"], fg=fg,
                activebackground=c["accent_green"],
                activeforeground="white",
                relief="flat", borderwidth=0, tearoff=0
            )

        # Progress Frame
        app.progress_frame.configure(bg=c["bg"])
        app.progress_label.configure(bg=c["bg"], fg="#aaa")

        # Konsole
        app.console.configure(
            bg=c["console_bg"],
            fg=c["console_fg"],
            insertbackground=c["console_fg"],
            selectbackground=c["console_bg"],
            selectforeground=c["console_fg"]
        )

        # Dropdown Fix
        self._fix_dropdown(app, c, fg)

        # Tab-Bar
        if hasattr(app, 'tab_bar'):
            app.tab_bar.configure(bg=c["bg"])
        if hasattr(app, 'tab_separator'):
            app.tab_separator.configure(bg=c["border"])
        if hasattr(app, 'analyse_frame'):
            app.analyse_frame.configure(bg=c["bg"])
        if hasattr(app, '_update_tab_buttons'):
            app._update_tab_buttons()

        # Queue-Theme
        apply_queue_theme(app, c)

        # Plattformspezifische Schriften
        self._apply_platform_fonts(app)

    def _fix_dropdown(self, app, c, fg):
        app.sub_menu.config(
            bg=c["entry_bg"], fg=c["btn_fg"],
            activebackground=c["act_secondary"],
            highlightthickness=0, bd=0,
            relief="flat", width=3
        )
        app.sub_menu["menu"].config(
            bg=c["entry_bg"], fg=fg,
            activebackground=c["accent_green"],
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            activeborderwidth=0,
            tearoff=0
        )

    def _apply_platform_fonts(self, app):
        """Setzt plattformgerechte Schriften – nur auf Linux nötig, da Arial/Consolas dort fehlen."""
        if platform.system() != "Linux":
            return
        for entry in [app.original, app.encoded]:
            entry.configure(font=(FONT_MONO, 9))
        if hasattr(app, 'art_frames_entry'):
            app.art_frames_entry.configure(font=(FONT_MONO, 9))
        app.console.configure(font=(FONT_MONO, 9))
        app.title_label.configure(font=(FONT_SANS, 18, 'bold'))
