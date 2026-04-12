import tkinter as tk


# ─────────────────────────────────────────────────────────────────────────────
# Technische Metrik-Definitionen
# ─────────────────────────────────────────────────────────────────────────────
METRIC_INFO = {
    "VMAF": {
        "full_name": "Video Multi-Method Assessment Fusion",
        "origin":    "Entwickelt von Netflix (2016), basiert auf Machine Learning.",
        "how":       "Kombiniert drei Bildqualitäts-Features (VIF, DLM, Motion) "
                     "mittels eines trainierten SVM-Modells zu einem Gesamtscore.",
        "scale": [
            ("≥ 93",  "Transparent – kein wahrnehmbarer Qualitätsverlust",  "#2ecc71"),
            ("80–92", "Excellent – minimale Artefakte, Broadcast-Qualität",  "#27ae60"),
            ("60–79", "Good – leichte Kompressionsartefakte sichtbar",       "#f39c12"),
            ("40–59", "Fair – deutliche Degradierung, Blockiness möglich",   "#e67e22"),
            ("<  40",  "Poor – starke Artefakte, inakzeptable Qualität",      "#e74c3c"),
        ],
        "note": "Höher ist besser. VMAF ist kalibriert auf menschliche Wahrnehmung "
                "und gilt als zuverlässigste objektive Metrik für Streaming-Inhalte.",
    },
    "SSIM": {
        "full_name": "Structural Similarity Index Measure",
        "origin":    "Wang et al., 2004 (IEEE). Weit verbreiteter akademischer Standard.",
        "how":       "Vergleicht Luminanz, Kontrast und Strukturinformation zwischen "
                     "zwei Frames pixelweise. Ergebnis ist ein Wert zwischen 0 und 1.",
        "scale": [
            ("≥ 0.98", "Exzellent – strukturell nahezu identisch",           "#2ecc71"),
            ("0.95–0.97", "Gut – geringe strukturelle Abweichungen",          "#27ae60"),
            ("0.90–0.94", "Akzeptabel – merkliche Unschärfe/Ringing möglich", "#f39c12"),
            ("0.80–0.89", "Schwach – sichtbare strukturelle Degradierung",    "#e67e22"),
            ("< 0.80",    "Schlecht – starke strukturelle Verfälschungen",    "#e74c3c"),
        ],
        "note": "Höher ist besser (Max = 1.0). SSIM reagiert sensitiv auf "
                "Blurring und Ringing, unterschätzt aber Farbfehler.",
    },
    "PSNR": {
        "full_name": "Peak Signal-to-Noise Ratio",
        "origin":    "Klassische Telekommunikations-Metrik, seit Jahrzehnten Standard.",
        "how":       "Berechnet das Verhältnis zwischen maximalem Signalpegel und "
                     "dem mittleren quadratischen Fehler (MSE) in Dezibel (dB).",
        "scale": [
            ("≥ 50 dB", "Transparent – rein mathematisch kaum Unterschied",  "#2ecc71"),
            ("40–49 dB", "Excellent – visuell verlustlos für die meisten Inhalte", "#27ae60"),
            ("35–39 dB", "Good – Broadcast-Standard, leichte Verluste",       "#f39c12"),
            ("30–34 dB", "Fair – sichtbare Qualitätseinbußen",                "#e67e22"),
            ("< 30 dB",  "Poor – starke Degradierung",                        "#e74c3c"),
        ],
        "note": "Höher ist besser. PSNR korreliert schlecht mit menschlicher "
                "Wahrnehmung – gilt als veraltet, aber ist universell verbreitet.",
    },
    "BITRATE": {
        "full_name": "Datendurchsatz (kbps / Mbps)",
        "origin":    "Grundlegende Streaming- und Codierungsmetrik.",
        "how":       "Misst Durchschnitts-Bitrate (Dateigröße ÷ Dauer) und "
                     "Peak-Bitrate (maximale Bits pro Sekunde) via Packet-Scan.",
        "scale": [
            ("> 20 Mbps",  "UHD / 4K Referenz-Qualität (z.B. Blu-ray)",      "#2ecc71"),
            ("8–20 Mbps",  "HD / FHD Broadcast-Qualität",                     "#27ae60"),
            ("4–8 Mbps",   "Streaming-Standard (Netflix, Disney+)",           "#f39c12"),
            ("1–4 Mbps",   "Mobile / Web – sichtbare Kompression",            "#e67e22"),
            ("< 1 Mbps",   "Sehr niedrig – starke Artefakte zu erwarten",     "#e74c3c"),
        ],
        "note": "Bitrate allein sagt nichts über Qualität aus – ein effizienter "
                "Codec (H.265, AV1) liefert bei halber Bitrate gleiche Qualität wie H.264.",
    },
    "ARTIFACTS": {
        "full_name": "Blocking & Blur Artifact Detection",
        "origin":    "FFmpeg blurdetect-Filter, analysiert lokale Frequenzinhalte.",
        "how":       "Scannt die ersten 500 Frames auf unnatürliche Unschärfe-Muster "
                     "(Ø Blur-Score). Werte > 0.15 gelten als Blocking-Artefakt.",
        "scale": [
            ("0 Frames",    "Keine Artefakte erkannt",                        "#2ecc71"),
            ("1–5 Frames",  "Vereinzelte Artefakte – unkritisch",             "#27ae60"),
            ("6–10 Frames", "Leichte Blocking-Tendenz – prüfen empfohlen",   "#f39c12"),
            ("11–30 Frames","Signifikantes Blocking sichtbar",                "#e67e22"),
            ("> 30 Frames", "Kritische Artefaktdichte – Bitrate zu niedrig",  "#e74c3c"),
        ],
        "note": "Erkennt primär Blocking (Makroblock-Grenzen) und Blur. "
                "Ringing- oder Banding-Artefakte werden separat in der Heatmap visualisiert.",
    },
    "FRAME DROPS": {
        "full_name": "Frame Drop & Duplicate Detection",
        "origin":    "Analyse via FFprobe Packet-Timing.",
        "how":       "Vergleicht die Dauer jedes Frames mit dem Median aller Frames. "
                     "Ratio > 1.8× → Drop (Frame fehlt). Ratio < 0.2× → Duplikat.",
        "scale": [
            ("0 Drops",   "Perfekte Framerate – keine Unterbrechungen",       "#2ecc71"),
            ("1–2 Drops", "Isolierte Drops – meist im Seek-Bereich normal",   "#27ae60"),
            ("3–5 Drops", "Leichte Framerate-Instabilität",                   "#f39c12"),
            ("6–15 Drops","Spürbares Stottern bei Wiedergabe",                "#e67e22"),
            ("> 15 Drops","Kritisch – Encoding-Fehler oder Bitrate-Problem",  "#e74c3c"),
        ],
        "note": "Drops im Original-Video sind codec-unabhängig. Neue Drops "
                "im Encoded-Video deuten auf Encoder-Fehler oder zu niedrige Bitrate hin.",
    },
    "AUDIO": {
        "full_name": "Audio Stream Analyzer & Vergleich",
        "origin":    "FFprobe Stream-Analyse beider Dateien (Original & Encoded).",
        "how":       "Liest Codec, Sample-Rate, Kanal-Layout und Bitrate via ffprobe aus. "
                     "Vergleicht Original gegen Encoded und meldet Downmix, "
                     "Sample-Rate-Änderungen oder Bitrate-Verluste.",
        "scale": [
            ("Unauffällig",       "Kein Audio-Problem – Stream vollständig übertragen", "#2ecc71"),
            ("Änderung erkannt",  "Kanal-Downmix oder Sample-Rate-Änderung",            "#f39c12"),
            ("Bitrate-Drop",      "Audio-Bitrate um > 50 % reduziert",                  "#e67e22"),
            ("Stream fehlt",      "Encoded hat keinen Audio-Track mehr",                 "#e74c3c"),
            ("Kein Audio",        "Beide Dateien haben keinen Audio-Stream",             "#95a5a6"),
        ],
        "note": "Prüft ausschließlich Codec-Metadaten – keine Klangqualitätsmessung (PEAQ/ViSQOL). "
                "Für Ton-Qualität empfiehlt sich ein separates Audiotool.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Popup-Klasse
# ─────────────────────────────────────────────────────────────────────────────
class MetricInfoPopup:
    """
    Stylevolles Info-Popup für eine Metrik.
    Öffnet sich neben dem auslösenden Widget, passt sich dem Dark/Light Mode an.
    """

    def __init__(self, parent, metric_name: str, colors: dict):
        info = METRIC_INFO.get(metric_name)
        if not info:
            return

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)   # Kein OS-Fensterrahmen
        self.win.attributes("-topmost", True)

        c = colors
        bg      = c.get("card",    "#2d2d2d")
        fg      = c.get("fg",      "#f0f0f0")
        border  = c.get("accent_green", "#2ecc71")
        sub_fg  = c.get("sub_lbl", "#888888")
        entry   = c.get("entry_bg","#3d3d3d")

        # ── Äußerer Rahmen (farbiger Border-Trick via Frame-in-Frame) ────────
        outer = tk.Frame(self.win, bg=border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(outer, bg=bg, padx=18, pady=14)
        inner.pack(fill=tk.BOTH, expand=True)

        # ── Header-Zeile ─────────────────────────────────────────────────────
        hdr = tk.Frame(inner, bg=bg)
        hdr.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            hdr, text=metric_name,
            font=('Helvetica', 13, 'bold'),
            bg=bg, fg=border
        ).pack(side=tk.LEFT)

        tk.Button(
            hdr, text="✕", font=('Arial', 9, 'bold'),
            bg=bg, fg=sub_fg, relief="flat",
            activebackground=bg, activeforeground=fg,
            cursor="hand2", bd=0,
            command=self.win.destroy
        ).pack(side=tk.RIGHT)

        # ── Full Name ─────────────────────────────────────────────────────────
        tk.Label(
            inner, text=info["full_name"],
            font=('Arial', 8, 'italic'),
            bg=bg, fg=sub_fg
        ).pack(anchor=tk.W, pady=(0, 8))

        # ── Divider ───────────────────────────────────────────────────────────
        tk.Frame(inner, bg=border, height=1).pack(fill=tk.X, pady=(0, 10))

        # ── Origin & How ──────────────────────────────────────────────────────
        for label, key in [("ORIGIN", "origin"), ("METHOD", "how")]:
            tk.Label(
                inner, text=label,
                font=('Arial', 7, 'bold'),
                bg=bg, fg=border
            ).pack(anchor=tk.W)
            tk.Label(
                inner, text=info[key],
                font=('Arial', 8),
                bg=bg, fg=fg,
                wraplength=380, justify=tk.LEFT
            ).pack(anchor=tk.W, pady=(1, 8))

        # ── Bewertungsskala ───────────────────────────────────────────────────
        tk.Label(
            inner, text="RATING SCALE",
            font=('Arial', 7, 'bold'),
            bg=bg, fg=border
        ).pack(anchor=tk.W)

        scale_frame = tk.Frame(inner, bg=bg)
        scale_frame.pack(fill=tk.X, pady=(4, 8))

        for value, desc, color in info["scale"]:
            row = tk.Frame(scale_frame, bg=entry, padx=6, pady=3)
            row.pack(fill=tk.X, pady=1)

            tk.Label(
                row, text="●", font=('Arial', 7),
                bg=entry, fg=color
            ).pack(side=tk.LEFT)

            tk.Label(
                row, text=f"  {value}",
                font=('Consolas', 8, 'bold'),
                width=12, anchor=tk.W,
                bg=entry, fg=color
            ).pack(side=tk.LEFT)

            tk.Label(
                row, text=desc,
                font=('Arial', 8),
                bg=entry, fg=fg, anchor=tk.W
            ).pack(side=tk.LEFT, padx=(6, 0))

        # ── Note ──────────────────────────────────────────────────────────────
        tk.Frame(inner, bg=border, height=1).pack(fill=tk.X, pady=(2, 8))

        tk.Label(
            inner, text=info["note"],
            font=('Arial', 7, 'italic'),
            bg=bg, fg=sub_fg,
            wraplength=380, justify=tk.LEFT
        ).pack(anchor=tk.W)

        # ── Schließen bei Klick außerhalb ─────────────────────────────────────
        self.win.bind("<FocusOut>", lambda e: self.win.destroy())

        # ── Positionierung: Maus-Position + kleiner Offset ───────────────────
        self.win.update_idletasks()
        x = parent.winfo_pointerx() + 12
        y = parent.winfo_pointery() + 12

        # Fenster nicht aus dem Bildschirm schieben
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w  = self.win.winfo_width()
        h  = self.win.winfo_height()
        if x + w > sw - 10:
            x = sw - w - 10
        if y + h > sh - 10:
            y = sh - h - 10

        self.win.geometry(f"+{x}+{y}")
        self.win.focus_set()

# ─────────────────────────────────────────────────────────────────────────────
# Subsampling Info Popup
# ─────────────────────────────────────────────────────────────────────────────
class SubsampleInfoPopup:
    """
    Info-Popup für VMAF Subsampling – gleicher Stil wie MetricInfoPopup.
    """

    ROWS = [
        ("1", "Jeden Frame analysieren",    "Höchste Genauigkeit – empfohlen für kurze Videos (<5 min)", "#2ecc71"),
        ("2", "Jeden 2. Frame analysieren", "Guter Kompromiss – ~2× schneller, minimaler Qualitätsverlust",  "#27ae60"),
        ("4", "Jeden 4. Frame analysieren", "Schnell – empfohlen für lange Episoden oder Filme",            "#f39c12"),
        ("8", "Jeden 8. Frame analysieren", "Sehr schnell – VMAF-Genauigkeit leicht reduziert",             "#e67e22"),
    ]

    def __init__(self, parent, colors: dict):
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        c       = colors
        bg      = c.get("card",         "#2d2d2d")
        fg      = c.get("fg",           "#f0f0f0")
        border  = c.get("accent_green", "#2ecc71")
        sub_fg  = c.get("sub_lbl",      "#888888")
        entry   = c.get("entry_bg",     "#3d3d3d")

        # Rahmen (Border-Trick)
        outer = tk.Frame(self.win, bg=border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(outer, bg=bg, padx=18, pady=14)
        inner.pack(fill=tk.BOTH, expand=True)

        # Header
        hdr = tk.Frame(inner, bg=bg)
        hdr.pack(fill=tk.X, pady=(0, 4))

        tk.Label(hdr, text="VMAF SUBSAMPLING",
                 font=('Helvetica', 13, 'bold'),
                 bg=bg, fg=border).pack(side=tk.LEFT)

        tk.Button(hdr, text="✕", font=('Arial', 9, 'bold'),
                  bg=bg, fg=sub_fg, relief="flat",
                  activebackground=bg, activeforeground=fg,
                  cursor="hand2", bd=0,
                  command=self.win.destroy).pack(side=tk.RIGHT)

        tk.Label(inner, text="Analyse-Geschwindigkeit vs. Genauigkeit",
                 font=('Arial', 8, 'italic'), bg=bg, fg=sub_fg
                 ).pack(anchor=tk.W, pady=(0, 8))

        # Divider
        tk.Frame(inner, bg=border, height=1).pack(fill=tk.X, pady=(0, 10))

        # Erklärung
        tk.Label(inner, text="METHOD",
                 font=('Arial', 7, 'bold'), bg=bg, fg=border).pack(anchor=tk.W)
        tk.Label(inner,
                 text="Subsampling legt fest, wie viele Frames VMAF tatsächlich berechnet.\n"
                      "Nicht analysierte Frames werden interpoliert. Höhere Werte = schneller,\n"
                      "aber geringfügig ungenauere Ergebnisse.",
                 font=('Arial', 8), bg=bg, fg=fg,
                 wraplength=390, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 10))

        # Tabelle
        tk.Label(inner, text="RATING SCALE",
                 font=('Arial', 7, 'bold'), bg=bg, fg=border).pack(anchor=tk.W)

        scale_frame = tk.Frame(inner, bg=bg)
        scale_frame.pack(fill=tk.X, pady=(4, 8))

        for val, meaning, rec, color in self.ROWS:
            row = tk.Frame(scale_frame, bg=entry, padx=6, pady=3)
            row.pack(fill=tk.X, pady=1)

            tk.Label(row, text="●", font=('Arial', 7),
                     bg=entry, fg=color).pack(side=tk.LEFT)

            tk.Label(row, text=f"  {val}",
                     font=('Consolas', 8, 'bold'), width=4, anchor=tk.W,
                     bg=entry, fg=color).pack(side=tk.LEFT)

            tk.Label(row, text=meaning,
                     font=('Arial', 8), width=26, anchor=tk.W,
                     bg=entry, fg=fg).pack(side=tk.LEFT, padx=(6, 0))

            tk.Label(row, text=rec,
                     font=('Arial', 7), anchor=tk.W,
                     bg=entry, fg=sub_fg).pack(side=tk.LEFT, padx=(8, 0))

        # Note
        tk.Frame(inner, bg=border, height=1).pack(fill=tk.X, pady=(2, 8))
        tk.Label(inner,
                 text="💡 Faustregel: Wert 1 für kurze Videos, Wert 2–4 für lange Filme & Serien.",
                 font=('Arial', 7, 'italic'), bg=bg, fg=sub_fg,
                 wraplength=390, justify=tk.LEFT).pack(anchor=tk.W)

        # Positionierung
        self.win.update_idletasks()
        x = parent.winfo_pointerx() + 12
        y = parent.winfo_pointery() + 12
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w  = self.win.winfo_width()
        h  = self.win.winfo_height()
        if x + w > sw - 10:
            x = sw - w - 10
        if y + h > sh - 10:
            y = sh - h - 10

        self.win.geometry(f"+{x}+{y}")
        self.win.bind("<FocusOut>", lambda e: self.win.destroy())
        self.win.focus_set()

# ─────────────────────────────────────────────────────────────────────────────
# Heatmap Info Popup
# ─────────────────────────────────────────────────────────────────────────────
class HeatmapInfoPopup:
    """
    Info-Popup für die Artefakt-Heatmap – gleicher Stil wie MetricInfoPopup.
    Erklärt was die Heatmap zeigt, wie sie entsteht und wie man sie liest.
    """

    ROWS = [
        ("Hell / Weiß",      "Hohe Intensität",    "Banding, Blocking oder starke VMAF-Einbußen",  "#e74c3c"),
        ("Orange / Rot",     "Erhöht",             "Sichtbare Artefakte – prüfen empfohlen",       "#e67e22"),
        ("Lila / Pink",      "Mittel",             "Leichte Artefakte oder VMAF-Verluste",         "#9b59b6"),
        ("Dunkel / Schwarz", "Niedrig",            "Saubere Szene – kein nennenswerter Verlust",   "#2ecc71"),
    ]

    def __init__(self, parent, colors: dict):
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)

        c      = colors
        bg     = c.get("card",         "#2d2d2d")
        fg     = c.get("fg",           "#f0f0f0")
        border = c.get("accent_green", "#2ecc71")
        sub_fg = c.get("sub_lbl",      "#888888")
        entry  = c.get("entry_bg",     "#3d3d3d")

        # Rahmen (Border-Trick)
        outer = tk.Frame(self.win, bg=border, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(outer, bg=bg, padx=18, pady=14)
        inner.pack(fill=tk.BOTH, expand=True)

        # Header
        hdr = tk.Frame(inner, bg=bg)
        hdr.pack(fill=tk.X, pady=(0, 4))

        tk.Label(hdr, text="ARTEFAKT-HEATMAP",
                 font=('Helvetica', 13, 'bold'),
                 bg=bg, fg=border).pack(side=tk.LEFT)

        tk.Button(hdr, text="✕", font=('Arial', 9, 'bold'),
                  bg=bg, fg=sub_fg, relief="flat",
                  activebackground=bg, activeforeground=fg,
                  cursor="hand2", bd=0,
                  command=self.win.destroy).pack(side=tk.RIGHT)

        tk.Label(inner, text="Artifact & Banding Intensity Timeline",
                 font=('Arial', 8, 'italic'), bg=bg, fg=sub_fg
                 ).pack(anchor=tk.W, pady=(0, 8))

        # Divider
        tk.Frame(inner, bg=border, height=1).pack(fill=tk.X, pady=(0, 10))

        # Was ist die Heatmap?
        tk.Label(inner, text="WAS WIRD ANGEZEIGT",
                 font=('Arial', 7, 'bold'), bg=bg, fg=border).pack(anchor=tk.W)
        tk.Label(inner,
                 text="Die Heatmap visualisiert die Artefakt-Intensität über die gesamte\n"
                      "Videolänge. Jeder Pixel entspricht einem Frame – die Farbe zeigt,\n"
                      "wie stark dieser Frame von Qualitätsverlusten betroffen ist.",
                 font=('Arial', 8), bg=bg, fg=fg,
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 10))

        # Berechnung
        tk.Label(inner, text="BERECHNUNG",
                 font=('Arial', 7, 'bold'), bg=bg, fg=border).pack(anchor=tk.W)
        tk.Label(inner,
                 text="Quelle: CAMBI-Score (Banding-Erkennung) aus dem VMAF-Log.\n"
                      "Falls kein CAMBI vorhanden: invertierter VMAF-Score (100 − VMAF),\n"
                      "sodass niedrige Qualität = hohe Intensität = helle Farbe.",
                 font=('Arial', 8), bg=bg, fg=fg,
                 justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 10))

        # Farbskala
        tk.Label(inner, text="FARBSKALA (Magma-Palette)",
                 font=('Arial', 7, 'bold'), bg=bg, fg=border).pack(anchor=tk.W)

        scale_frame = tk.Frame(inner, bg=bg)
        scale_frame.pack(fill=tk.X, pady=(4, 8))

        for value, meaning, detail, color in self.ROWS:
            row = tk.Frame(scale_frame, bg=entry, padx=6, pady=3)
            row.pack(fill=tk.X, pady=1)

            tk.Label(row, text="●", font=('Arial', 7),
                     bg=entry, fg=color).pack(side=tk.LEFT)

            tk.Label(row, text=f"  {value}",
                     font=('Consolas', 8, 'bold'), width=20, anchor=tk.W,
                     bg=entry, fg=color).pack(side=tk.LEFT)

            tk.Label(row, text=meaning,
                     font=('Arial', 8, 'bold'), width=10, anchor=tk.W,
                     bg=entry, fg=fg).pack(side=tk.LEFT, padx=(6, 0))

            tk.Label(row, text=detail,
                     font=('Arial', 7), anchor=tk.W,
                     bg=entry, fg=sub_fg).pack(side=tk.LEFT, padx=(8, 0))

        # Hinweis
        tk.Frame(inner, bg=border, height=1).pack(fill=tk.X, pady=(2, 8))
        tk.Label(inner,
                 text="💡 Tipp: Helle Stellen mit den 'Kritischste Szenen' im Report\n"
                      "vergleichen – sie sollten zeitlich übereinstimmen.",
                 font=('Arial', 7, 'italic'), bg=bg, fg=sub_fg,
                 justify=tk.LEFT).pack(anchor=tk.W)

        # Positionierung
        self.win.update_idletasks()
        x = parent.winfo_pointerx() + 12
        y = parent.winfo_pointery() + 12
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w  = self.win.winfo_width()
        h  = self.win.winfo_height()
        if x + w > sw - 10:
            x = sw - w - 10
        if y + h > sh - 10:
            y = sh - h - 10

        self.win.geometry(f"+{x}+{y}")
        self.win.bind("<FocusOut>", lambda e: self.win.destroy())
        self.win.focus_set()