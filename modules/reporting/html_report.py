import os
import base64
import datetime
from modules.path_utils import APP_PATH

def _embed_img(abs_path):
    """Liest eine Bilddatei und gibt einen Base64-Data-URI zurück.
    Fällt auf leeren String zurück wenn die Datei nicht existiert."""
    try:
        with open(abs_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        ext = os.path.splitext(abs_path)[1].lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png"}.get(ext, "png")
        return f"data:image/{mime};base64,{data}"
    except Exception:
        return ""

def generate_full_report(vmaf_log, bitrate_res, artifact_res, video_path, ssim, psnr,
                          vmaf_avg, vmaf_min, worst_scenes, hdr_info,
                          frame_drop_res=None, audio_res=None,
                          dark_mode=False, active_metrics=None, solo_mode=False,
                          vmaf_p5=None):
    """
    Generiert einen HTML-Qualitätsbericht.
    - FIX: APP_PATH statt dirname(dirname(dirname())) – Report landet neben der EXE
    - FIX: active_metrics steuert welche Sektionen als 'Nicht erhoben' markiert werden
    - FIX: Bilder werden als absolute file:// Pfade eingebettet – funktioniert in EXE
    """
    # Welche Metriken waren aktiv – Standard: alle
    if active_metrics is None:
        active_metrics = {"VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"}

    # FIX: APP_PATH = Ordner neben der EXE, nicht _MEIPASS
    base_dir   = APP_PATH
    report_dir = os.path.join(base_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)

    timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name  = os.path.basename(video_path)
    report_path = os.path.join(report_dir, f"Report_{timestamp}.html")

    # --- Theme ---
    if dark_mode:
        bg_color       = "#121212"
        container_bg   = "#1e1e1e"
        card_bg        = "#2d2d2d"
        box_bg         = "#252525"
        text_primary   = "#e0e0e0"
        text_secondary = "#aaa"
        border_color   = "#333"
        accent_color   = "#2ecc71"
        table_header   = "#333"
    else:
        bg_color       = "#f4f7f6"
        container_bg   = "#ffffff"
        card_bg        = "#f9f9f9"
        box_bg         = "#ffffff"
        text_primary   = "#2c3e50"
        text_secondary = "#7f8c8d"
        border_color   = "#dee2e6"
        accent_color   = "#27ae60"
        table_header   = "#ecf0f1"

    # Offline SVG Fallback
    fallback_img = (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='225'%3E"
        "%3Crect width='400' height='225' fill='%23333'/%3E"
        "%3Ctext x='50%25' y='50%25' fill='%23888' font-size='14' text-anchor='middle' "
        "dominant-baseline='middle'%3EBild nicht verfügbar%3C/text%3E%3C/svg%3E"
    )

    def _skipped(metric_name):
        """Einheitlicher 'Nicht erhoben'-Banner für deaktivierte Metriken."""
        return (
            f'<div style="display:flex;align-items:center;gap:14px;'
            f'background:{"#1a1a2e" if dark_mode else "#f0f4ff"};'
            f'border:1px solid {"#2c2c5e" if dark_mode else "#c5d0f0"};'
            f'border-left:4px solid #3498db;border-radius:8px;'
            f'padding:16px 20px;margin:8px 0;">'
            f'<span style="font-size:1.6em;">⏭</span>'
            f'<div>'
            f'<div style="font-weight:bold;color:#3498db;font-size:0.95em;">'
            f'{metric_name} &ndash; Nicht erhoben</div>'
            f'<div style="color:{"#8899bb" if dark_mode else "#5566aa"};'
            f'font-size:0.85em;margin-top:3px;">'
            f'Diese Metrik war zum Zeitpunkt der Analyse deaktiviert.</div>'
            f'</div></div>'
        )

    def _temp_img(subpath):
        """Liest Bild aus temp/ und gibt Base64-Data-URI zurück."""
        return _embed_img(os.path.join(base_dir, "temp", subpath))

    # Bildpfade (Base64-eingebettet – funktionieren offline, in EXE und Web)
    graph_abs   = _temp_img("graphs/vmaf_graph.png")
    heatmap_abs = _temp_img("heatmaps/heatmap_latest.png")

    # --- Szenen-Karten ---
    scenes_html = ""
    if not worst_scenes:
        scenes_html = (
            f"<p style='color: {text_secondary}; grid-column: 1/-1; "
            f"text-align: center; padding: 20px;'>Keine kritischen Szenen aufgezeichnet.</p>"
        )
    else:
        for i, scene in enumerate(worst_scenes):
            raw_sec   = scene.get('timestamp_raw', 0)
            ts_format = f"{int(raw_sec // 60):02d}:{int(raw_sec % 60):02d}"
            vmaf_val  = scene.get('vmaf', 0)
            img_name  = scene.get('screenshot', f"worst_scene_{i+1}.jpg")
            img_abs   = _temp_img(f"screenshots/{img_name}")

            scenes_html += f"""
            <div class="scene-card" style="background:{box_bg}; border:1px solid {border_color};">
                <img src="{img_abs}" alt="Scene {ts_format}"
                     onerror="this.src='{fallback_img}'">
                <div class="scene-info" style="background:{card_bg}; border-top:1px solid {border_color};">
                    <strong style="color:{text_primary};">Zeitstempel:</strong> {ts_format} |
                    <strong style="color:{text_primary};">VMAF:</strong>
                    <span style="color:#e74c3c; font-weight:bold;">{vmaf_val:.2f}</span>
                </div>
            </div>"""

    # --- HDR Badge ---
    pix_fmt           = hdr_info.get('pix_fmt', 'unbekannt')
    is_hdr_bool       = hdr_info.get('is_hdr') == "Ja"
    hdr_format_detail = hdr_info.get('hdr_format', 'SDR')
    badge_class       = "badge-hdr" if is_hdr_bool else "badge-sdr"
    hdr_label         = f"{pix_fmt} | {hdr_format_detail}" if is_hdr_bool else f"{pix_fmt} | SDR"

    # --- VMAF Farbe ---
    def vmaf_color(score):
        if score >= 90: return "#2ecc71"
        if score >= 75: return "#f39c12"
        return "#e74c3c"

    # --- NEU: Frame Drop Sektion HTML ---
    def _drop_color(drops):
        if drops == 0:   return "#2ecc71"
        if drops < 5:    return "#f39c12"
        return "#e74c3c"

    if frame_drop_res:
        orig_res = frame_drop_res.get("original", {})
        enco_res = frame_drop_res.get("encoded",  {})

        orig_drops  = orig_res.get("drops", 0)
        orig_dups   = orig_res.get("duplicates", 0)
        orig_frames = orig_res.get("total_frames", 0)
        orig_status = orig_res.get("status", "N/A")

        enco_drops  = enco_res.get("drops", 0)
        enco_dups   = enco_res.get("duplicates", 0)
        enco_frames = enco_res.get("total_frames", 0)
        enco_status = enco_res.get("status", "N/A")

        # Vergleichs-Delta – nur sinnvoll wenn beide Scans erfolgreich waren
        orig_timeout = "Timeout" in orig_status or "Übersprungen" in orig_status
        enco_timeout = "Timeout" in enco_status or "Übersprungen" in enco_status
        drop_delta   = enco_drops - orig_drops

        if orig_timeout or enco_timeout:
            delta_html = "<span style='color:#95a5a6;'>⏭ Kein Vergleich möglich – Analyse nicht abgeschlossen</span>"
        elif drop_delta > 0:
            delta_html = f"<span style='color:#e74c3c;'>+{drop_delta} durch Encoding hinzugekommen</span>"
        elif drop_delta < 0:
            delta_html = f"<span style='color:#2ecc71;'>{drop_delta} weniger als Original</span>"
        else:
            delta_html = f"<span style='color:#2ecc71;'>Kein Unterschied zum Original</span>"

        frame_drop_html = f"""
        <h2 class="section-title">Frame-Integrität</h2>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:15px;">

            <div style="background:{box_bg}; border:1px solid {border_color};
                        border-radius:8px; padding:20px;">
                <h3 style="color:{text_primary}; margin:0 0 15px 0; font-size:1em;">
                    📁 Original
                </h3>
                <table style="width:100%; border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Frame Drops</td>
                        <td style="padding:6px 0; font-weight:bold;
                                   color:{_drop_color(orig_drops)};">{orig_drops}x</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Duplikate</td>
                        <td style="padding:6px 0; font-weight:bold;
                                   color:{_drop_color(orig_dups)};">{orig_dups}x</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Frames gesamt</td>
                        <td style="padding:6px 0; color:{text_primary};">{orig_frames}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Status</td>
                        <td style="padding:6px 0;">{orig_status}</td>
                    </tr>
                </table>
            </div>

            <div style="background:{box_bg}; border:1px solid {border_color};
                        border-radius:8px; padding:20px;">
                <h3 style="color:{text_primary}; margin:0 0 15px 0; font-size:1em;">
                    🎬 Encoded
                </h3>
                <table style="width:100%; border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Frame Drops</td>
                        <td style="padding:6px 0; font-weight:bold;
                                   color:{_drop_color(enco_drops)};">{enco_drops}x</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Duplikate</td>
                        <td style="padding:6px 0; font-weight:bold;
                                   color:{_drop_color(enco_dups)};">{enco_dups}x</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Frames gesamt</td>
                        <td style="padding:6px 0; color:{text_primary};">{enco_frames}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0; color:{text_secondary};">Status</td>
                        <td style="padding:6px 0;">{enco_status}</td>
                    </tr>
                </table>
            </div>
        </div>

        <div style="background:{card_bg}; border:1px solid {border_color};
                    border-radius:8px; padding:15px; margin-top:15px;
                    text-align:center;">
            <span style="color:{text_secondary}; font-size:0.9em;">
                Encoding-Einfluss auf Frame-Drops:
            </span>
            <strong style="margin-left:10px; font-size:1em;">{delta_html}</strong>
        </div>
        """
    else:
        if "FRAME DROPS" not in active_metrics:
            frame_drop_html = f"""
        <h2 class="section-title">Frame-Integrität</h2>
        {_skipped("FRAME DROPS")}
        """
        else:
            frame_drop_html = f"""
        <h2 class="section-title">Frame-Integrität</h2>
        <p style="color:{text_secondary}; padding:15px;">
            Frame-Drop Analyse nicht verfügbar.
        </p>
        """

    # --- AUDIO SEKTION HTML ---
    def _audio_row(label, orig_val, enco_val, highlight=False):
        enco_style = f"color:#e74c3c;font-weight:bold;" if highlight else f"color:{text_primary};"
        return (
            f'<tr>'
            f'<td style="padding:6px 0;color:{text_secondary};">{label}</td>'
            f'<td style="padding:6px 0;color:{text_primary};">{orig_val}</td>'
            f'<td style="padding:6px 0;{enco_style}">{enco_val}</td>'
            f'</tr>'
        )

    if audio_res:
        orig_a = audio_res.get("original", {})
        enco_a = audio_res.get("encoded",  {})
        issues = audio_res.get("issues",   [])
        summary = audio_res.get("summary", "N/A")

        has_orig = orig_a.get("has_audio", False)
        has_enco = enco_a.get("has_audio", False)

        # Farbe des Summary-Banners
        if "❌" in summary:
            sum_color = "#e74c3c"
        elif "⚠️" in summary:
            sum_color = "#f39c12"
        else:
            sum_color = "#2ecc71"

        def _val(d, key, fallback="N/A"):
            v = d.get(key, fallback)
            return str(v) if v else fallback

        ch_changed  = has_orig and has_enco and orig_a.get("channels") != enco_a.get("channels")
        sr_changed  = has_orig and has_enco and orig_a.get("sample_rate") != enco_a.get("sample_rate")
        br_orig     = orig_a.get("bitrate_kbps", 0)
        br_enco     = enco_a.get("bitrate_kbps", 0)
        br_drop     = (br_orig > 0 and br_enco > 0 and (br_orig - br_enco) / br_orig > 0.5)

        orig_br_str = f"{br_orig:.0f} kbps" if br_orig > 0 else "N/A"
        enco_br_str = f"{br_enco:.0f} kbps" if br_enco > 0 else "N/A"

        audio_html = f"""
        <h2 class="section-title">Audio-Prüfung</h2>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:15px;">

            <div style="background:{box_bg}; border:1px solid {border_color};
                        border-radius:8px; padding:20px;">
                <h3 style="color:{text_primary}; margin:0 0 15px 0; font-size:1em;">📁 Original</h3>
                <table style="width:100%; border-collapse:collapse;">
                    {'<tr><td colspan="2" style="color:#2ecc71;">✅ Audio-Stream vorhanden</td></tr>' if has_orig
                     else '<tr><td colspan="2" style="color:#95a5a6;">Kein Audio-Stream</td></tr>'}
                    {''.join([
                        f'<tr><td style="padding:4px 0;color:{text_secondary};">{k}</td>'
                        f'<td style="padding:4px 0;color:{text_primary};">{v}</td></tr>'
                        for k, v in [
                            ("Codec",        _val(orig_a, "codec")),
                            ("Sample-Rate",  _val(orig_a, "sample_rate") + " Hz" if orig_a.get("sample_rate") not in ("N/A", None) else "N/A"),
                            ("Kanäle",       _val(orig_a, "channel_layout")),
                            ("Bitrate",      orig_br_str),
                            ("Bit-Tiefe",    _val(orig_a, "bit_depth")),
                            ("Streams",      str(orig_a.get("stream_count", 0))),
                        ]
                    ]) if has_orig else ""}
                </table>
            </div>

            <div style="background:{box_bg}; border:1px solid {border_color};
                        border-radius:8px; padding:20px;">
                <h3 style="color:{text_primary}; margin:0 0 15px 0; font-size:1em;">🎬 Encoded</h3>
                <table style="width:100%; border-collapse:collapse;">
                    {'<tr><td colspan="2" style="color:#2ecc71;">✅ Audio-Stream vorhanden</td></tr>' if has_enco
                     else '<tr><td colspan="2" style="color:#e74c3c;">❌ Kein Audio-Stream!</td></tr>'}
                    {''.join([
                        f'<tr><td style="padding:4px 0;color:{text_secondary};">{k}</td>'
                        f'<td style="padding:4px 0;{"color:#e74c3c;font-weight:bold;" if hi else "color:" + text_primary + ";"}">{v}</td></tr>'
                        for k, v, hi in [
                            ("Codec",        _val(enco_a, "codec"), False),
                            ("Sample-Rate",  _val(enco_a, "sample_rate") + " Hz" if enco_a.get("sample_rate") not in ("N/A", None) else "N/A", sr_changed),
                            ("Kanäle",       _val(enco_a, "channel_layout"), ch_changed),
                            ("Bitrate",      enco_br_str, br_drop),
                            ("Bit-Tiefe",    _val(enco_a, "bit_depth"), False),
                            ("Streams",      str(enco_a.get("stream_count", 0)), False),
                        ]
                    ]) if has_enco else ""}
                </table>
            </div>
        </div>

        <div style="background:{card_bg}; border:1px solid {border_color};
                    border-left:4px solid {sum_color};
                    border-radius:8px; padding:14px 20px; margin-top:15px;">
            <strong style="color:{sum_color};">{summary}</strong>
        </div>
        """
    else:
        if "AUDIO" not in active_metrics:
            audio_html = f"""
        <h2 class="section-title">Audio-Prüfung</h2>
        {_skipped("AUDIO")}
        """
        else:
            audio_html = f"""
        <h2 class="section-title">Audio-Prüfung</h2>
        <p style="color:{text_secondary}; padding:15px;">Audio-Analyse nicht verfügbar.</p>
        """

    # ─────────────────────────────────────────────────────────────────────────
    # BEWERTUNGSSEKTION – Laienverständliche Einschätzung pro Metrik
    # ─────────────────────────────────────────────────────────────────────────

    def _rating_row(icon, label, rating_text, detail_text, color):
        """Einzelne Bewertungszeile mit Icon, Label, farbiger Einschätzung und Erklärung."""
        return f"""
        <div style="display:flex; align-items:flex-start; gap:14px;
                    background:{card_bg}; border:1px solid {border_color};
                    border-left:5px solid {color}; border-radius:8px;
                    padding:14px 18px; margin-bottom:10px;">
            <span style="font-size:1.6em; line-height:1;">{icon}</span>
            <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
                    <span style="font-weight:bold; color:{text_primary}; font-size:0.95em;">{label}</span>
                    <span style="background:{color}22; color:{color}; border:1px solid {color}55;
                                 border-radius:20px; padding:2px 12px; font-size:0.82em; font-weight:bold;">
                        {rating_text}
                    </span>
                </div>
                <div style="color:{text_secondary}; font-size:0.88em; margin-top:5px; line-height:1.5;">
                    {detail_text}
                </div>
            </div>
        </div>"""

    assessment_rows = ""
    score_points  = 0
    score_total   = 0

    # ── VMAF ──────────────────────────────────────────────────────────────────
    if "VMAF" in active_metrics and vmaf_avg > 0:
        score_total += 1
        if vmaf_avg >= 93:
            assessment_rows += _rating_row("🏆", "Bildqualität (VMAF)",
                "Ausgezeichnet",
                f"Mit einem VMAF-Wert von {vmaf_avg:.1f} ist die Videoqualität hervorragend. "
                f"Selbst auf großen Bildschirmen sind kaum Qualitätsverluste gegenüber dem Original erkennbar.",
                "#2ecc71")
            score_points += 1
        elif vmaf_avg >= 85:
            assessment_rows += _rating_row("✅", "Bildqualität (VMAF)",
                "Gut",
                f"VMAF {vmaf_avg:.1f} – die Bildqualität ist gut. Auf normalen Bildschirmen "
                f"sind keine störenden Unterschiede zum Original sichtbar.",
                "#27ae60")
            score_points += 1
        elif vmaf_avg >= 75:
            assessment_rows += _rating_row("⚠️", "Bildqualität (VMAF)",
                "Akzeptabel",
                f"VMAF {vmaf_avg:.1f} – die Qualität ist noch akzeptabel, aber aufmerksame Zuschauer "
                f"könnten auf größeren Bildschirmen leichte Qualitätseinbußen bemerken.",
                "#f39c12")
        elif vmaf_avg >= 60:
            assessment_rows += _rating_row("⚠️", "Bildqualität (VMAF)",
                "Mäßig",
                f"VMAF {vmaf_avg:.1f} – die Bildqualität ist merklich reduziert. Unschärfen, "
                f"Blockartefakte oder Detailverlust können sichtbar sein.",
                "#e67e22")
        else:
            assessment_rows += _rating_row("❌", "Bildqualität (VMAF)",
                "Schlecht",
                f"VMAF {vmaf_avg:.1f} – die Qualität ist stark beeinträchtigt. Das Video ist "
                f"deutlich schlechter als das Original und Artefakte sind klar erkennbar.",
                "#e74c3c")

    # ── SSIM ──────────────────────────────────────────────────────────────────
    if "SSIM" in active_metrics and ssim > 0:
        score_total += 1
        if ssim >= 0.98:
            assessment_rows += _rating_row("✅", "Strukturtreue (SSIM)",
                "Sehr hoch",
                f"SSIM {ssim:.4f} – Kanten, Texturen und Details werden nahezu identisch zum "
                f"Original wiedergegeben. Kein wahrnehmbarer Strukturverlust.",
                "#2ecc71")
            score_points += 1
        elif ssim >= 0.95:
            assessment_rows += _rating_row("✅", "Strukturtreue (SSIM)",
                "Hoch",
                f"SSIM {ssim:.4f} – die Bildstrukturen sind gut erhalten. Feine Details "
                f"werden sauber übertragen.",
                "#27ae60")
            score_points += 1
        elif ssim >= 0.90:
            assessment_rows += _rating_row("⚠️", "Strukturtreue (SSIM)",
                "Mittel",
                f"SSIM {ssim:.4f} – leichte Verluste in feinen Strukturen und Texturen. "
                f"Bei ruhigen Szenen kaum, bei Detailreichtum eher erkennbar.",
                "#f39c12")
        else:
            assessment_rows += _rating_row("❌", "Strukturtreue (SSIM)",
                "Niedrig",
                f"SSIM {ssim:.4f} – deutlicher Strukturverlust. Kanten wirken unscharf "
                f"und Texturen verlieren erkennbar an Detailtreue.",
                "#e74c3c")

    # ── PSNR ──────────────────────────────────────────────────────────────────
    if "PSNR" in active_metrics and psnr > 0:
        score_total += 1
        if psnr >= 45:
            assessment_rows += _rating_row("✅", "Rauschfreiheit (PSNR)",
                "Sehr gut",
                f"{psnr:.1f} dB – das Signal ist sehr sauber. Rauschen oder digitales "
                f"Bildrauschen ist praktisch nicht vorhanden.",
                "#2ecc71")
            score_points += 1
        elif psnr >= 38:
            assessment_rows += _rating_row("✅", "Rauschfreiheit (PSNR)",
                "Gut",
                f"{psnr:.1f} dB – übliche Qualität für gut encodierte Videos. "
                f"Kein störendes Rauschen sichtbar.",
                "#27ae60")
            score_points += 1
        elif psnr >= 30:
            assessment_rows += _rating_row("⚠️", "Rauschfreiheit (PSNR)",
                "Akzeptabel",
                f"{psnr:.1f} dB – leichtes Bildrauschen oder Kompressionsartefakte "
                f"können in dunklen oder ruhigen Szenen sichtbar sein.",
                "#f39c12")
        else:
            assessment_rows += _rating_row("❌", "Rauschfreiheit (PSNR)",
                "Schlecht",
                f"{psnr:.1f} dB – deutliches Bildrauschen oder starke Kompressionsartefakte. "
                f"Die Bildqualität ist merklich beeinträchtigt.",
                "#e74c3c")

    # ── BITRATE ───────────────────────────────────────────────────────────────
    if "BITRATE" in active_metrics:
        avg_br = bitrate_res.get('avg_bitrate', 0)
        if avg_br > 0:
            score_total += 1
            if avg_br >= 8000:
                assessment_rows += _rating_row("✅", "Bitrate (Datenmenge)",
                    "Hoch – sehr gute Qualität",
                    f"Ø {avg_br:.0f} kbps – die Datenmenge pro Sekunde ist hoch. "
                    f"Das Video hat viel Spielraum für komplexe Szenen ohne Qualitätsverlust.",
                    "#2ecc71")
                score_points += 1
            elif avg_br >= 4000:
                assessment_rows += _rating_row("✅", "Bitrate (Datenmenge)",
                    "Ausreichend",
                    f"Ø {avg_br:.0f} kbps – solide Bitrate für 1080p. "
                    f"Für die meisten Inhalte ist das vollkommen ausreichend.",
                    "#27ae60")
                score_points += 1
            elif avg_br >= 2000:
                assessment_rows += _rating_row("⚠️", "Bitrate (Datenmenge)",
                    "Niedrig",
                    f"Ø {avg_br:.0f} kbps – die Bitrate ist für 1080p eher niedrig. "
                    f"Bei actionreichen oder detailreichen Szenen können Artefakte entstehen.",
                    "#f39c12")
            else:
                assessment_rows += _rating_row("❌", "Bitrate (Datenmenge)",
                    "Sehr niedrig",
                    f"Ø {avg_br:.0f} kbps – die Bitrate ist sehr niedrig. "
                    f"Deutliche Qualitätsverluste bei schnellen Bewegungen sind zu erwarten.",
                    "#e74c3c")

    # ── ARTEFAKTE ─────────────────────────────────────────────────────────────
    if "ARTIFACTS" in active_metrics:
        art_result = artifact_res.get('result', '')
        art_count  = artifact_res.get('total_count', 0)
        if art_result.startswith('✅'):
            score_total += 1
            score_points += 1
            assessment_rows += _rating_row("✅", "Artefakte (Bildfehler)",
                "Keine erkannt",
                f"Es wurden keine Blocking-Artefakte oder störende Bildfehler gefunden. "
                f"Das Video wirkt sauber und ohne sichtbare Compression-Fehler.",
                "#2ecc71")
        elif art_result.startswith('⚠'):
            score_total += 1
            assessment_rows += _rating_row("⚠️", "Artefakte (Bildfehler)",
                f"{art_count} Frames betroffen",
                f"In {art_count} Frames wurden Blocking-Artefakte erkannt – sichtbare "
                f"Klötzchen oder Unschärfen, meist in schnellen oder dunklen Szenen.",
                "#e67e22")
        else:
            # Keine verwertbaren Daten → nicht in Gesamtwertung
            assessment_rows += _rating_row("ℹ️", "Artefakte (Bildfehler)",
                "Nicht geprüft",
                (art_result if art_result else "Keine Artefakt-Daten verfügbar.")
                + " Dieser Wert wird nicht in die Gesamtbewertung eingerechnet.",
                "#95a5a6")

    # ── FRAME DROPS ───────────────────────────────────────────────────────────
    if "FRAME DROPS" in active_metrics and frame_drop_res:
        enco  = frame_drop_res.get("encoded", {})
        drops = enco.get("drops", 0)
        total = enco.get("total_frames", 0)
        if enco.get("status", "").startswith("Timeout"):
            # Timeout → nicht in Gesamtwertung
            assessment_rows += _rating_row("ℹ️", "Frame-Drops (Ruckler)",
                "Zeitüberschreitung",
                "Das Video ist zu lang für einen vollständigen Frame-Scan. "
                "Dieser Wert wird nicht in die Gesamtbewertung eingerechnet.",
                "#95a5a6")
        elif drops == 0:
            score_total += 1
            score_points += 1
            assessment_rows += _rating_row("✅", "Frame-Drops (Ruckler)",
                "Keine Ruckler",
                "Es wurden keine fehlenden Frames festgestellt. "
                "Die Wiedergabe sollte flüssig und ohne Ruckler sein.",
                "#2ecc71")
        elif drops <= 5:
            score_total += 1
            assessment_rows += _rating_row("⚠️", "Frame-Drops (Ruckler)",
                f"{drops} Frames fehlen",
                f"Vereinzelte fehlende Frames ({drops}x). In der Praxis kaum wahrnehmbar.",
                "#f39c12")
        else:
            score_total += 1
            pct = (drops / total * 100) if total > 0 else 0
            assessment_rows += _rating_row("❌", "Frame-Drops (Ruckler)",
                f"{drops} Frames fehlen ({pct:.1f}%)",
                f"{drops} fehlende Frames bei {total} Frames gesamt. "
                f"Ruckler oder Sprünge in der Wiedergabe sind wahrscheinlich.",
                "#e74c3c")

    # ── AUDIO ─────────────────────────────────────────────────────────────────
    if "AUDIO" in active_metrics and audio_res:
        issues = audio_res.get("issues", [])
        summary = audio_res.get("summary", "")
        has_enco = audio_res.get("encoded", {}).get("has_audio", False)
        enco_a   = audio_res.get("encoded", {})
        if not audio_res.get("original", {}).get("has_audio", False) and not has_enco:
            # Kein Audio in beiden – neutral
            assessment_rows += _rating_row("🔇", "Audio-Stream",
                "Kein Audio",
                "Beide Dateien enthalten keinen Audio-Stream. "
                "Das ist für reine Video-Dateien normal.",
                "#95a5a6")
        elif not has_enco:
            score_total += 1
            assessment_rows += _rating_row("❌", "Audio-Stream",
                "Fehlt im Encoded!",
                "Das Original hat einen Audio-Stream, das Encoded-Video jedoch nicht. "
                "Der Audio-Track wurde beim Encoding verloren.",
                "#e74c3c")
        elif issues:
            score_total += 1
            assessment_rows += _rating_row("⚠️", "Audio-Qualität",
                "Änderungen erkannt",
                " · ".join(issues),
                "#f39c12")
        else:
            score_total += 1
            score_points += 1
            codec  = enco_a.get("codec", "N/A")
            layout = enco_a.get("channel_layout", "N/A")
            sr     = enco_a.get("sample_rate", "N/A")
            assessment_rows += _rating_row("🔊", "Audio-Qualität",
                "Unauffällig",
                f"Audio-Stream korrekt übertragen: {codec}, {layout}, {sr} Hz. "
                f"Keine Downmix-, Sample-Rate- oder Bitrate-Probleme erkannt.",
                "#2ecc71")

    # ── GESAMTNOTE ────────────────────────────────────────────────────────────
    # Mindestens 2 Metriken nötig – sonst ist die Gesamtbewertung irreführend
    if score_total >= 2:
        overall_pct = int(score_points / score_total * 100)
        ratio = score_points / score_total
        if ratio >= 0.85:
            overall_grade   = "Sehr gut"
            overall_color   = "#2ecc71"
            overall_icon    = "🏆"
            overall_detail  = "Dieses Video hat eine hervorragende Qualität. Es eignet sich gut für Streaming, Archivierung oder Weitergabe."
        elif ratio >= 0.65:
            overall_grade   = "Gut"
            overall_color   = "#27ae60"
            overall_icon    = "✅"
            overall_detail  = "Die Qualität ist insgesamt gut. Kleinere Schwächen in einzelnen Bereichen beeinträchtigen das Seherlebnis kaum."
        elif ratio >= 0.45:
            overall_grade   = "Akzeptabel"
            overall_color   = "#f39c12"
            overall_icon    = "⚠️"
            overall_detail  = "Die Qualität ist noch brauchbar, aber in mehreren Bereichen gibt es Einschränkungen, die je nach Verwendungszweck störend sein können."
        else:
            overall_grade   = "Verbesserungsbedarf"
            overall_color   = "#e74c3c"
            overall_icon    = "❌"
            overall_detail  = "Mehrere Qualitätsmerkmale sind beeinträchtigt. Eine Neu-Encodierung mit besseren Einstellungen wird empfohlen."

        overall_html = f"""
        <div style="background:{overall_color}18; border:2px solid {overall_color};
                    border-radius:12px; padding:20px 24px; margin-bottom:24px;">
            <div style="display:flex; align-items:center; gap:20px; margin-bottom:20px;">
                <span style="font-size:2.8em; line-height:1;">{overall_icon}</span>
                <div>
                    <div style="font-size:0.82em; color:{text_secondary}; text-transform:uppercase;
                                letter-spacing:1px; margin-bottom:4px;">Gesamtbewertung</div>
                    <div style="font-size:1.9em; font-weight:bold; color:{overall_color}; line-height:1.1;">
                        {overall_grade}
                    </div>
                    <div style="font-size:0.9em; color:{text_secondary}; margin-top:6px; line-height:1.5;">
                        {overall_detail}
                    </div>
                </div>
            </div>
            <div style="background:{border_color}; border-radius:99px; height:12px; overflow:hidden; max-width:400px; margin:0 0 6px 0;">
                <div style="background:{overall_color}; width:{overall_pct}%; height:100%; border-radius:99px;"></div>
            </div>
            <div style="font-size:0.8em; color:{text_secondary}; margin-bottom:20px;">
                {score_points} von {score_total} Kriterien erfüllt
                {"&nbsp;·&nbsp;<em>Nicht bewertbare Kriterien wurden ausgeschlossen.</em>" if score_total < len(active_metrics) else ""}
            </div>

            <!-- Referenztabelle -->
            <div style="font-size:0.82em; color:{text_secondary}; margin-bottom:8px; font-weight:bold;
                        text-transform:uppercase; letter-spacing:0.5px;">
                📊 Bewertungsskala – so werden die Werte eingeschätzt
            </div>
            <table style="width:100%; border-collapse:collapse; font-size:0.83em;
                          background:{container_bg}; border-radius:8px; overflow:hidden;">
                <thead>
                    <tr style="background:{table_header};">
                        <th style="padding:8px 12px; text-align:left; color:{text_secondary}; font-weight:600;">Metrik</th>
                        <th style="padding:8px 12px; text-align:center; color:#2ecc71; font-weight:600;">🟢 Gut</th>
                        <th style="padding:8px 12px; text-align:center; color:#f39c12; font-weight:600;">🟡 Akzeptabel</th>
                        <th style="padding:8px 12px; text-align:center; color:#e74c3c; font-weight:600;">🔴 Schlecht</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-top:1px solid {border_color};">
                        <td style="padding:7px 12px; color:{text_primary}; font-weight:500;">Bildqualität (VMAF)</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">≥ 85</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">75 – 84</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">&lt; 75</td>
                    </tr>
                    <tr style="border-top:1px solid {border_color}; background:{card_bg};">
                        <td style="padding:7px 12px; color:{text_primary}; font-weight:500;">Detailtreue (SSIM)</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">≥ 0.95</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">0.90 – 0.94</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">&lt; 0.90</td>
                    </tr>
                    <tr style="border-top:1px solid {border_color};">
                        <td style="padding:7px 12px; color:{text_primary}; font-weight:500;">Rauschfreiheit (PSNR)</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">≥ 38 dB</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">30 – 37 dB</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">&lt; 30 dB</td>
                    </tr>
                    <tr style="border-top:1px solid {border_color}; background:{card_bg};">
                        <td style="padding:7px 12px; color:{text_primary}; font-weight:500;">Bitrate (1080p)</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">≥ 6.000 kbps</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">3.000 – 5.999 kbps</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">&lt; 3.000 kbps</td>
                    </tr>
                    <tr style="border-top:1px solid {border_color};">
                        <td style="padding:7px 12px; color:{text_primary}; font-weight:500;">Artefakte</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">Keine</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">1 – 10 Frames</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">&gt; 10 Frames</td>
                    </tr>
                    <tr style="border-top:1px solid {border_color}; background:{card_bg};">
                        <td style="padding:7px 12px; color:{text_primary}; font-weight:500;">Frame-Drops</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">0</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">1 – 5</td>
                        <td style="padding:7px 12px; text-align:center; color:{text_secondary};">&gt; 5</td>
                    </tr>
                </tbody>
            </table>
        </div>"""
    else:
        if score_total == 1:
            overall_html = f"""
        <div style="display:flex; align-items:center; gap:14px;
                    background:{'#1a1a2e' if dark_mode else '#f0f4ff'};
                    border:1px solid {'#2c2c5e' if dark_mode else '#c5d0f0'};
                    border-left:4px solid #3498db; border-radius:8px;
                    padding:16px 20px; margin-bottom:16px;">
            <span style="font-size:1.6em;">ℹ️</span>
            <div>
                <div style="font-weight:bold; color:#3498db; font-size:0.95em;">
                    Gesamtbewertung nicht verfügbar</div>
                <div style="color:{'#8899bb' if dark_mode else '#5566aa'};
                            font-size:0.85em; margin-top:3px;">
                    Für eine aussagekräftige Gesamtbewertung werden mindestens
                    2 aktive Metriken benötigt.
                </div>
            </div>
        </div>"""
        else:
            overall_html = ""

    assessment_html = f"""
    <h2 class="section-title">🔍 Qualitätsbewertung</h2>
    {overall_html}
    {assessment_rows if assessment_rows else
     f"<p style='color:{text_secondary}; padding:15px;'>Keine aktiven Metriken für Bewertung verfügbar.</p>"}
    """

    # ── Laien-Tab: Ampelkarten ─────────────────────────────────────────────────
    def _ampel_card(icon, title, ampel, text, recommendation, orig_val, enc_val):
        """Große Ampelkarte für den Laien-Tab."""
        color_map = {
            "gruen":  ("#2ecc71", "#1a5c35", "✅ Gut"),
            "gelb":   ("#f39c12", "#7d5000", "⚠️ Akzeptabel"),
            "rot":    ("#e74c3c", "#7b1a14", "❌ Schlecht"),
            "grau":   ("#95a5a6", "#3d4d4e", "ℹ️ Keine Daten"),
        }
        c, dark_c, label = color_map.get(ampel, color_map["grau"])
        comp_html = ""
        if orig_val and enc_val:
            comp_html = f"""
            <div style="display:flex; gap:12px; margin-top:14px;">
                <div style="flex:1; background:{card_bg}; border:1px solid {border_color};
                            border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:0.75em; color:{text_secondary}; margin-bottom:4px;">📁 ORIGINAL</div>
                    <div style="font-weight:bold; color:{text_primary};">{orig_val}</div>
                </div>
                <div style="flex:1; background:{card_bg}; border:1px solid {border_color};
                            border-radius:8px; padding:10px; text-align:center;">
                    <div style="font-size:0.75em; color:{text_secondary}; margin-bottom:4px;">🎬 ENCODED</div>
                    <div style="font-weight:bold; color:{text_primary};">{enc_val}</div>
                </div>
            </div>"""
        rec_html = f"""
            <div style="margin-top:12px; background:{c}18; border-left:3px solid {c};
                        border-radius:0 6px 6px 0; padding:10px 14px;">
                <span style="font-size:0.82em; color:{text_secondary};">💡 </span>
                <span style="font-size:0.88em; color:{text_secondary};">{recommendation}</span>
            </div>""" if recommendation else ""
        return f"""
        <div style="background:{container_bg}; border:1px solid {border_color};
                    border-radius:12px; overflow:hidden; margin-bottom:16px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">
            <div style="background:{c}; padding:14px 20px;
                        display:flex; align-items:center; gap:14px;">
                <span style="font-size:2em; line-height:1;">{icon}</span>
                <div>
                    <div style="font-weight:bold; color:#fff; font-size:1.05em;">{title}</div>
                    <div style="color:#ffffffcc; font-size:0.85em;">{label}</div>
                </div>
            </div>
            <div style="padding:16px 20px;">
                <p style="margin:0 0 0 0; color:{text_primary}; line-height:1.6; font-size:0.95em;">{text}</p>
                {comp_html}
                {rec_html}
            </div>
        </div>"""

    # Laien-Karten zusammenbauen
    laien_cards = ""

    # Gesamtscore als große Kopf-Box
    if score_total >= 2:
        pct = int(score_points / score_total * 100)
        bar_color = "#2ecc71" if pct >= 75 else "#f39c12" if pct >= 45 else "#e74c3c"
        laien_cards += f"""
        <div style="background:{container_bg}; border:2px solid {bar_color};
                    border-radius:14px; padding:24px; margin-bottom:24px;
                    text-align:center;">
            <div style="font-size:0.85em; color:{text_secondary}; text-transform:uppercase;
                        letter-spacing:1.5px; margin-bottom:8px;">Gesamtbewertung</div>
            <div style="font-size:3.5em; font-weight:900; color:{bar_color}; line-height:1;">
                {pct}%
            </div>
            <div style="font-size:1.1em; font-weight:bold; color:{text_primary}; margin:8px 0 4px;">
                {overall_grade}
            </div>
            <div style="color:{text_secondary}; font-size:0.9em; max-width:600px; margin:0 auto 16px;">
                {overall_detail}
            </div>
            <div style="background:{border_color}; border-radius:99px; height:12px; overflow:hidden; max-width:400px; margin:0 auto;">
                <div style="background:{bar_color}; width:{pct}%; height:100%; border-radius:99px;
                            transition:width 0.6s ease;"></div>
            </div>
            <div style="font-size:0.8em; color:{text_secondary}; margin-top:6px;">
                {score_points} von {score_total} Kriterien erfüllt
            </div>
        </div>"""
    elif score_total == 1:
        laien_cards += f"""
        <div style="display:flex; align-items:center; gap:14px;
                    background:{'#1a1a2e' if dark_mode else '#f0f4ff'};
                    border:1px solid {'#2c2c5e' if dark_mode else '#c5d0f0'};
                    border-left:4px solid #3498db; border-radius:8px;
                    padding:16px 20px; margin-bottom:16px;">
            <span style="font-size:1.6em;">ℹ️</span>
            <div>
                <div style="font-weight:bold; color:#3498db; font-size:0.95em;">
                    Gesamtbewertung nicht verfügbar</div>
                <div style="color:{'#8899bb' if dark_mode else '#5566aa'};
                            font-size:0.85em; margin-top:3px;">
                    Für eine aussagekräftige Gesamtbewertung werden mindestens
                    2 aktive Metriken benötigt.
                </div>
            </div>
        </div>"""

    # VMAF
    if "VMAF" in active_metrics and vmaf_avg > 0:
        if vmaf_avg >= 85:
            laien_cards += _ampel_card("🎥", "Bildqualität", "gruen",
                f"Das Video sieht sehr gut aus. Mit einem Qualitätswert von {vmaf_avg:.1f} von 100 "
                f"sind selbst auf großen Bildschirmen kaum Unterschiede zum Original erkennbar.",
                "Dieses Video ist gut für Streaming, Archivierung und Weitergabe geeignet.",
                None, None)
        elif vmaf_avg >= 75:
            laien_cards += _ampel_card("🎥", "Bildqualität", "gelb",
                f"Die Bildqualität ist in Ordnung. Wert: {vmaf_avg:.1f}/100. Auf normalen Bildschirmen "
                f"fällt der Unterschied zum Original kaum auf, auf sehr großen Displays eventuell schon.",
                "Für normale Wiedergabe geeignet. Für Archivierung empfiehlt sich ein besserer Encoder-Preset.",
                None, None)
        else:
            laien_cards += _ampel_card("🎥", "Bildqualität", "rot",
                f"Die Bildqualität ist deutlich schlechter als das Original. Wert: {vmaf_avg:.1f}/100. "
                f"Unschärfen oder Klötzchen-Artefakte können sichtbar sein.",
                "Eine Neu-Encodierung mit höherer Bitrate oder besserem Preset wird empfohlen.",
                None, None)

    # BITRATE
    if "BITRATE" in active_metrics:
        avg_br = bitrate_res.get('avg_bitrate', 0)
        if avg_br >= 6000:
            laien_cards += _ampel_card("📊", "Datenmenge (Bitrate)", "gruen",
                f"Mit {avg_br:.0f} kbps steckt viel Videodaten pro Sekunde im File. "
                f"Das Video hat genug Reserve um auch schnelle Szenen klar und scharf darzustellen.",
                "Optimal für hochauflösende Inhalte und komplexe Szenen.",
                None, None)
        elif avg_br >= 3000:
            laien_cards += _ampel_card("📊", "Datenmenge (Bitrate)", "gelb",
                f"Die Datenmenge von {avg_br:.0f} kbps ist für die meisten Inhalte ausreichend. "
                f"Bei sehr schnellen Bewegungen oder Detailreichtum kann die Qualität etwas leiden.",
                "Für normalen Gebrauch in Ordnung. Bei Actionfilmen oder Sport könnte mehr helfen.",
                None, None)
        elif avg_br > 0:
            laien_cards += _ampel_card("📊", "Datenmenge (Bitrate)", "rot",
                f"Die Datenmenge von {avg_br:.0f} kbps ist sehr niedrig. "
                f"Das Video wurde stark komprimiert, was zu sichtbaren Qualitätseinbußen führt.",
                "Neu-Encodierung mit höherer Bitrate empfohlen.",
                None, None)

    # ARTEFAKTE
    if "ARTIFACTS" in active_metrics:
        art_result = artifact_res.get('result', '')
        art_count  = artifact_res.get('total_count', 0)
        if art_result.startswith('✅'):
            laien_cards += _ampel_card("🔍", "Bildfehler (Artefakte)", "gruen",
                "Es wurden keine störenden Bildfehler gefunden. "
                "Das Video zeigt keine sichtbaren Klötzchen, Unschärfen oder andere Kompressionsschäden.",
                "Sehr gut – das Video ist frei von Encoding-Fehlern.",
                None, None)
        elif art_result.startswith('⚠'):
            laien_cards += _ampel_card("🔍", "Bildfehler (Artefakte)", "gelb",
                f"In {art_count} Bildern wurden Unschärfen oder Blocking-Fehler gefunden. "
                f"Das sind sichtbare Klötzchen oder unscharfe Bereiche, meist in dunklen oder schnellen Szenen.",
                "Für normale Wiedergabe meist noch akzeptabel. Bei hohen Qualitätsansprüchen neu encodieren.",
                None, None)
        else:
            laien_cards += _ampel_card("🔍", "Bildfehler (Artefakte)", "grau",
                "Die Artefakt-Prüfung konnte nicht abgeschlossen werden. "
                "Das passiert manchmal bei bestimmten Videoformaten.",
                "Kein Handlungsbedarf – die anderen Werte zeigen trotzdem die Qualität an.",
                None, None)

    # FRAME DROPS
    if "FRAME DROPS" in active_metrics and frame_drop_res:
        orig_r = frame_drop_res.get("original", {})
        enco_r = frame_drop_res.get("encoded",  {})
        o_drops = orig_r.get("drops", 0)
        e_drops = enco_r.get("drops", 0)
        o_stat  = orig_r.get("status", "")
        e_stat  = enco_r.get("status", "")
        orig_disp = o_stat if o_stat else f"{o_drops} Drops"
        enco_disp = e_stat if e_stat else f"{e_drops} Drops"
        if "Timeout" in e_stat:
            laien_cards += _ampel_card("🎞️", "Ruckler (Frame-Drops)", "grau",
                "Das Video ist sehr lang, daher konnte die Ruckler-Prüfung nicht vollständig abgeschlossen werden.",
                "Kein Handlungsbedarf – bei normalen Videos zeigt dieser Test ob Bilder fehlen.",
                None, None)
        elif e_drops == 0:
            laien_cards += _ampel_card("🎞️", "Ruckler (Frame-Drops)", "gruen",
                "Kein einziges Bild fehlt im Video. Die Wiedergabe sollte absolut flüssig sein – "
                "keine Ruckler, keine Sprünge.",
                "Perfekt – das Video läuft ohne Unterbrechungen.",
                orig_disp, enco_disp)
        elif e_drops <= 5:
            laien_cards += _ampel_card("🎞️", "Ruckler (Frame-Drops)", "gelb",
                f"Es fehlen {e_drops} Einzelbilder im Video. Das ist sehr wenig und in der Praxis "
                f"kaum wahrnehmbar.",
                "Für normale Wiedergabe kein Problem.",
                orig_disp, enco_disp)
        else:
            laien_cards += _ampel_card("🎞️", "Ruckler (Frame-Drops)", "rot",
                f"Es fehlen {e_drops} Bilder im Video. Bei der Wiedergabe könnten sichtbare Ruckler "
                f"oder kurze Sprünge auftreten.",
                "Neu-Encodierung empfohlen, da der Encoder Frames verloren hat.",
                orig_disp, enco_disp)

    # AUDIO
    if "AUDIO" in active_metrics and audio_res:
        has_orig = audio_res.get("original", {}).get("has_audio", False)
        has_enco = audio_res.get("encoded",  {}).get("has_audio", False)
        issues   = audio_res.get("issues", [])
        enco_a   = audio_res.get("encoded", {})
        orig_a   = audio_res.get("original", {})
        if not has_orig and not has_enco:
            pass  # Beide ohne Audio → keine Karte nötig
        elif not has_enco:
            laien_cards += _ampel_card("🔇", "Audio-Track", "rot",
                "Das Original-Video hat einen Ton-Track, das encodierte Video jedoch nicht. "
                "Der Ton ist beim Encoding verloren gegangen!",
                "Neu encodieren und sicherstellen, dass die Audio-Spur mit '-c:a copy' oder neuem Codec mitgenommen wird.",
                None, None)
        elif issues:
            detail_txt = " · ".join(issues)
            laien_cards += _ampel_card("🔊", "Audio-Track", "gelb",
                f"Der Ton wurde übertragen, aber es gibt Änderungen: {detail_txt}",
                "Prüfe ob die Audio-Einstellungen im Encoder korrekt gesetzt sind.",
                orig_a.get("status", "N/A"), enco_a.get("status", "N/A"))
        else:
            laien_cards += _ampel_card("🔊", "Audio-Track", "gruen",
                f"Der Ton wurde sauber übertragen. "
                f"Codec: {enco_a.get('codec','N/A')}, "
                f"Kanäle: {enco_a.get('channel_layout','N/A')}, "
                f"{enco_a.get('sample_rate','N/A')} Hz – alles wie erwartet.",
                "Der Audio-Track ist vollständig und korrekt encodiert.",
                orig_a.get("status", "N/A"), enco_a.get("status", "N/A"))

    # SSIM & PSNR – kompakt zusammengefasst für Laien
    if ("SSIM" in active_metrics and ssim > 0) or ("PSNR" in active_metrics and psnr > 0):
        ssim_ok  = ssim >= 0.95 if ssim > 0 else None
        psnr_ok  = psnr >= 38   if psnr > 0 else None
        both_gut = (ssim_ok is not False) and (psnr_ok is not False)
        any_gut  = ssim_ok or psnr_ok
        ampel    = "gruen" if both_gut else "gelb" if any_gut else "rot"
        detail   = []
        if ssim > 0:
            detail.append(f"Detailtreue (SSIM): {'sehr hoch' if ssim>=0.98 else 'gut' if ssim>=0.95 else 'mittel' if ssim>=0.90 else 'niedrig'} ({ssim:.4f})")
        if psnr > 0:
            detail.append(f"Rauschfreiheit (PSNR): {'sehr gut' if psnr>=45 else 'gut' if psnr>=38 else 'akzeptabel' if psnr>=30 else 'schlecht'} ({psnr:.1f} dB)")
        laien_cards += _ampel_card("📐", "Technische Präzision", ampel,
            "Diese Werte messen wie genau das encodierte Video dem Original entspricht. " +
            " · ".join(detail) + ".",
            "Diese Werte bestätigen die VMAF-Einschätzung zur Bildqualität.",
            None, None)

    laien_tab_html = f"""
    <div id="tab-laien" class="tab-content" style="display:none;">
        <div style="margin-bottom:20px;">
            <h1 style="color:{accent_color}; border-bottom:2px solid {border_color};
                       padding-bottom:10px; margin-top:0;">
                Qualitätsbewertung
            </h1>
            <p style="color:{text_secondary};">
                Datei: <strong style="color:{text_primary};">{file_name}</strong>
            </p>
        </div>
        {laien_cards if laien_cards else
         f"<p style='color:{text_secondary};'>Keine aktiven Metriken für Bewertung verfügbar.</p>"}
        <div style="margin-top:30px; padding:16px 20px; background:{card_bg};
                    border:1px solid {border_color}; border-radius:10px;
                    font-size:0.82em; color:{text_secondary}; line-height:1.6;">
            <strong>ℹ️ Hinweis:</strong> Diese Bewertung richtet sich an Nicht-Techniker und
            fasst die Messergebnisse verständlich zusammen. Die genauen Messwerte findest du
            im Tab <strong>„Technischer Report"</strong>.
        </div>
    </div>"""
    html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Video Quality Report - {file_name}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: {bg_color};
            color: {text_primary};
            margin: 0; padding: 20px;
        }}
        .container {{
            max-width: 1100px; margin: auto;
            background: {container_bg};
            padding: 30px; border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }}
        h1 {{
            color: {accent_color};
            border-bottom: 2px solid {border_color};
            padding-bottom: 10px; margin-top: 0;
        }}
        h2.section-title {{
            background: {table_header}; color: #3498db;
            padding: 10px 15px; border-radius: 4px;
            margin-top: 30px; font-size: 1.2em;
            border-left: 5px solid #3498db;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; margin: 20px 0;
        }}
        .metric-card {{
            background: {card_bg}; padding: 20px;
            border-radius: 8px; text-align: center;
            border: 1px solid {border_color};
        }}
        .vmaf-main {{ font-size: 48px; font-weight: bold; display: block; }}
        .label {{
            font-size: 12px; color: {text_secondary};
            text-transform: uppercase; letter-spacing: 1px;
        }}
        .visual-container {{
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 20px; margin-top: 20px;
        }}
        .img-box {{
            background: {box_bg}; padding: 15px;
            border-radius: 8px; border: 1px solid {border_color};
            text-align: center;
        }}
        .img-box img {{
            max-width: 100%; border-radius: 4px;
            border: 1px solid {border_color}; margin-top: 10px;
            cursor: zoom-in; transition: opacity 0.2s;
        }}
        .img-box img:hover {{ opacity: 0.88; }}
        table {{
            width: 100%; border-collapse: collapse;
            margin-top: 10px; background: {box_bg};
            border-radius: 8px; overflow: hidden;
        }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid {border_color}; }}
        th {{
            background: {table_header}; color: {text_secondary};
            text-transform: uppercase; font-size: 11px;
        }}
        .scene-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px; margin-top: 15px;
        }}
        .scene-card {{ border-radius: 8px; overflow: hidden; transition: 0.3s; }}
        .scene-card:hover {{
            transform: translateY(-5px);
            border-color: #3498db !important;
        }}
        .scene-card img {{ width: 100%; height: auto; display: block; background: #000; cursor: zoom-in; }}
        .scene-info {{ padding: 10px; font-size: 0.9em; }}
        .badge {{
            padding: 8px 15px; border-radius: 4px;
            font-size: 13px; font-weight: bold; display: inline-block;
        }}
        .badge-hdr {{ background: #f1c40f; color: #000; }}
        .badge-sdr {{ background: #7f8c8d; color: #fff; }}

        /* ── Tab Navigation ── */
        .tab-nav {{
            display: flex; gap: 0;
            border-bottom: 2px solid {border_color};
            margin-bottom: 28px; margin-top: 16px;
        }}
        .tab-btn {{
            padding: 11px 26px; cursor: pointer;
            background: none; border: none;
            font-size: 0.95em; font-weight: 600;
            color: {text_secondary};
            border-bottom: 3px solid transparent;
            margin-bottom: -2px; transition: all 0.2s;
            font-family: inherit; border-radius: 0;
        }}
        .tab-btn:hover {{ color: #3498db; }}
        .tab-btn.active {{
            color: #3498db;
            border-bottom: 3px solid #3498db;
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
    </style>
</head>
<body>
<div class="container">

    <h1>Video Quality Report</h1>
    <p style="color:{text_secondary}; margin-bottom:0;">
        Datei: <strong style="color:{text_primary};">{file_name}</strong>
        {"&nbsp;&nbsp;<span style='background:#8e44ad;color:#fff;font-size:0.78em;font-weight:bold;padding:3px 10px;border-radius:12px;letter-spacing:0.5px;'>🔍 SOLO-SCAN – REFERENZLOS</span>" if solo_mode else ""}
    </p>
    {f'''<div style="background:{"#1e0a2e" if dark_mode else "#f5eeff"};border:1px solid {"#6c2e9e" if dark_mode else "#c39bd3"};border-left:4px solid #8e44ad;border-radius:8px;padding:12px 18px;margin-top:12px;font-size:0.88em;color:{text_secondary};">
        <strong style="color:#8e44ad;">ℹ️ Referenzloser Scan</strong> &nbsp;–&nbsp;
        Dieser Report wurde ohne Original-Referenz erstellt. Gemessen wurden ausschließlich
        absolute Qualitätsmerkmale des Encodes (Bitrate, Artefakte, Frame-Drops, Audio).
        Vergleichsmetriken wie VMAF, SSIM und PSNR sind nicht verfügbar.
    </div>''' if solo_mode else ""}

    <!-- TAB NAVIGATION -->
    <div class="tab-nav">
        <button class="tab-btn active" onclick="switchTab('laien')">🔍 Qualitätsbewertung</button>
        <button class="tab-btn"        onclick="switchTab('technik')">🛠 Technischer Report</button>
    </div>

    <!-- ═══ TAB: LAIEN ═══ -->
    {laien_tab_html}

    <!-- ═══ TAB: TECHNIK ═══ -->
    <div id="tab-technik" class="tab-content">

    <!-- METRIKEN -->
    <div class="metric-grid">
        <div class="metric-card">
            <span class="label">Durchschnitt VMAF</span>
            {"<span class='vmaf-main' style='color:" + vmaf_color(vmaf_avg) + ";'>" + f"{vmaf_avg:.2f}" + "</span>"
              if "VMAF" in active_metrics else _skipped("VMAF")}
        </div>
        <div class="metric-card">
            <span class="label">Minimum VMAF</span>
            {"<span class='vmaf-main' style='font-size:36px; color:" + vmaf_color(vmaf_min) + ";'>" + f"{vmaf_min:.2f}" + "</span>"
              if "VMAF" in active_metrics else _skipped("VMAF")}
        </div>
        <div class="metric-card">
            <span class="label">VMAF P5 <span style="font-size:11px;color:#888;">(schlechteste 5%)</span></span>
            {"<span class='vmaf-main' style='font-size:36px; color:" + vmaf_color(vmaf_p5 or 0) + ";'>" + f"{vmaf_p5:.2f}" + "</span>"
              if ("VMAF" in active_metrics and vmaf_p5 is not None) else _skipped("VMAF P5")}
        </div>
        <div class="metric-card">
            <span class="label">SSIM (Struktur)</span>
            {"<span class='vmaf-main' style='font-size:32px; color:#3498db;'>" + f"{ssim:.4f}" + "</span>"
              if "SSIM" in active_metrics else _skipped("SSIM")}
        </div>
        <div class="metric-card">
            <span class="label">PSNR (Signal/Rausch)</span>
            {"<span class='vmaf-main' style='font-size:32px; color:#9b59b6;'>" + f"{psnr:.2f} dB" + "</span>"
              if "PSNR" in active_metrics else _skipped("PSNR")}
        </div>
        <div class="metric-card">
            <span class="label">HDR / Farbraum</span>
            <div style="margin-top:15px;">
                <span class="badge {badge_class}">{hdr_label}</span>
            </div>
        </div>
    </div>

    <!-- VISUELLE ANALYSE -->
    <h2 class="section-title">Visuelle Analyse &amp; Artefakte</h2>
    <div class="visual-container">
        <div class="img-box">
            <p class="label">VMAF Verlauf</p>
            {"<img src='" + graph_abs + "' alt='VMAF Graph' onerror=\"this.src='" + fallback_img + "'\">"
              if "VMAF" in active_metrics else _skipped("VMAF Graph")}
        </div>
        <div class="img-box">
            <p class="label">Artefakt-Heatmap</p>
            {"<img src='" + heatmap_abs + "' alt='Heatmap' onerror=\"this.src='" + fallback_img + "'\">"
              if "VMAF" in active_metrics else _skipped("Artefakt-Heatmap")}
        </div>
    </div>

    <!-- KRITISCHE SZENEN -->
    <h2 class="section-title">Kritischste Szenen (Low VMAF)</h2>
    {"<div class='scene-grid'>" + scenes_html + "</div>"
      if "VMAF" in active_metrics else _skipped("Kritische Szenen / VMAF")}

    <!-- FRAME INTEGRITÄT -->
    {frame_drop_html}

    <!-- AUDIO PRÜFUNG -->
    {audio_html}

    <!-- TECHNISCHE DATEN -->
    <h2 class="section-title">Bitraten-Profil &amp; Technische Daten</h2>
    <table>
        <thead>
            <tr>
                <th>Metrik</th>
                <th>Wert</th>
                <th>Zusatz-Info</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Durchschnittliche Bitrate</td>
                <td>{"%.2f kbps" % bitrate_res.get('avg_bitrate', 0) if "BITRATE" in active_metrics else _skipped("BITRATE")}</td>
                <td>Gesamt-Mittelwert</td>
            </tr>
            <tr>
                <td>Peak Bitrate</td>
                <td>{"%.2f kbps" % bitrate_res.get('peak_bitrate', 0) if "BITRATE" in active_metrics else _skipped("BITRATE")}</td>
                <td>Höchste gemessene Spitze</td>
            </tr>
            <tr>
                <td>Codec Profil</td>
                <td>{bitrate_res.get('profile', 'Unknown') if "BITRATE" in active_metrics else _skipped("BITRATE")}</td>
                <td>Stream-Profil</td>
            </tr>
            <tr>
                <td>PSNR</td>
                <td>{"%.2f dB" % psnr if "PSNR" in active_metrics else _skipped("PSNR")}</td>
                <td>Signal-Rausch-Verhältnis</td>
            </tr>
            <tr>
                <td>Artefakt-Check</td>
                <td>{
                    _skipped("ARTIFACTS") if "ARTIFACTS" not in active_metrics
                    else ("<span style='color:#2ecc71;font-weight:bold;'>" + artifact_res.get('result', '–') + "</span>"
                          if artifact_res.get('result', '').startswith('✅')
                          else "<span style='color:#e67e22;font-weight:bold;'>" + artifact_res.get('result', '–') + "</span>"
                          if artifact_res.get('result', '').startswith('⚠')
                          else "<span style='color:#7f8c8d;'>" + artifact_res.get('result', 'Keine Daten') + "</span>")
                }</td>
                <td>blurdetect-basierte Erkennung</td>
            </tr>
            <tr>
                <td>Farbtiefe</td>
                <td>{hdr_info.get('bit_depth', 8)} Bit</td>
                <td>Komponenten-Tiefe</td>
            </tr>
            <tr>
                <td>Pixel Format</td>
                <td>{hdr_info.get('pix_fmt', 'N/A')}</td>
                <td>Internes Format</td>
            </tr>
        </tbody>
    </table>

    <div style="margin-top:50px; text-align:center; color:{text_secondary};
                font-size:11px; border-top:1px solid {border_color}; padding-top:20px;">
        Generiert am {datetime.datetime.now().strftime("%d.%m.%Y um %H:%M:%S")}
        | Video Quality Analyzer v0.15
    </div>

    </div><!-- end tab-technik -->

</div>
<style>
#lightbox {{
    display:none; position:fixed; inset:0; background:rgba(0,0,0,0.88);
    z-index:9999; align-items:center; justify-content:center; cursor:zoom-out;
}}
#lightbox.active {{ display:flex; }}
#lightbox img {{
    max-width:92vw; max-height:92vh; border-radius:6px;
    box-shadow:0 8px 40px rgba(0,0,0,0.7); object-fit:contain;
}}
#lightbox-close {{
    position:fixed; top:18px; right:24px; color:#fff; font-size:2em;
    cursor:pointer; line-height:1; user-select:none; opacity:0.8;
}}
#lightbox-close:hover {{ opacity:1; }}
</style>
<div id="lightbox" onclick="closeLightbox()">
    <span id="lightbox-close">✕</span>
    <img id="lightbox-img" src="" alt="Vorschau">
</div>
<script>
function openLightbox(src) {{
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('active');
}}
function closeLightbox() {{
    document.getElementById('lightbox').classList.remove('active');
    document.getElementById('lightbox-img').src = '';
}}
document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closeLightbox();
}});
document.querySelectorAll('.img-box img, .scene-card img').forEach(function(img) {{
    img.addEventListener('click', function(e) {{
        e.stopPropagation();
        openLightbox(this.src);
    }});
}});
function switchTab(name) {{
    document.querySelectorAll('.tab-content').forEach(t => {{
        t.style.display = 'none';
        t.classList.remove('active');
    }});
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    var el = document.getElementById('tab-' + name);
    if (el) {{ el.style.display = 'block'; el.classList.add('active'); }}
    event.target.classList.add('active');
}}
// Laien-Tab standardmäßig aktiv
document.addEventListener('DOMContentLoaded', function() {{
    document.getElementById('tab-laien').style.display = 'block';
}});
</script>
</body>
</html>"""

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return report_path
    except Exception as e:
        print(f"Fehler beim Speichern des Reports: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SOLO-SCAN REPORT – eigenständiger Report ohne Referenz
# ─────────────────────────────────────────────────────────────────────────────

def generate_solo_report(br_res, art_res, enco_path, hdr_info,
                         frame_drop_res=None, audio_res=None,
                         dark_mode=False, active_metrics=None):
    """
    Eigenständiger HTML-Report für den referenzlosen Solo-Scan.
    Zeigt nur die 4 referenzfreien Metriken: Bitrate, Artefakte, Frame-Drops, Audio.
    """
    if active_metrics is None:
        active_metrics = {"BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"}

    base_dir    = APP_PATH
    report_dir  = os.path.join(base_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)

    timestamp   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name   = os.path.basename(enco_path) if enco_path else "unbekannt"
    report_path = os.path.join(report_dir, f"SoloReport_{timestamp}.html")

    # --- Theme ---
    if dark_mode:
        bg_color       = "#120a1e"
        container_bg   = "#1a0f2e"
        card_bg        = "#251840"
        box_bg         = "#1e1430"
        text_primary   = "#e8d5ff"
        text_secondary = "#9b80cc"
        border_color   = "#3d2a6e"
        table_header   = "#2a1a50"
        accent         = "#a855f7"
        accent_dark    = "#7c3aed"
    else:
        bg_color       = "#f5f0ff"
        container_bg   = "#ffffff"
        card_bg        = "#faf5ff"
        box_bg         = "#ffffff"
        text_primary   = "#2d1b5e"
        text_secondary = "#7c6b9e"
        border_color   = "#ddd0f5"
        table_header   = "#ede8fb"
        accent         = "#8e44ad"
        accent_dark    = "#6c3483"

    GREEN  = "#2ecc71"
    YELLOW = "#f39c12"
    RED    = "#e74c3c"
    GRAY   = "#95a5a6"

    def _drop_color(n):
        return GREEN if n == 0 else (YELLOW if n <= 5 else RED)

    # ── Hilfsfunktionen ──────────────────────────────────────────────────────

    def _ampel(icon, title, color, text, recommendation=""):
        rec = (f'<div style="margin-top:10px;background:{color}18;border-left:3px solid {color};'
               f'border-radius:0 6px 6px 0;padding:10px 14px;font-size:0.87em;'
               f'color:{text_secondary};">💡 {recommendation}</div>') if recommendation else ""
        return f"""
        <div style="background:{container_bg};border:1px solid {border_color};
                    border-radius:12px;overflow:hidden;margin-bottom:16px;
                    box-shadow:0 2px 8px rgba(100,0,200,0.08);">
            <div style="background:{color};padding:14px 20px;
                        display:flex;align-items:center;gap:14px;">
                <span style="font-size:2em;line-height:1;">{icon}</span>
                <div style="font-weight:bold;color:#fff;font-size:1.05em;">{title}</div>
            </div>
            <div style="padding:16px 20px;">
                <p style="margin:0;color:{text_primary};line-height:1.6;font-size:0.95em;">{text}</p>
                {rec}
            </div>
        </div>"""

    def _info_row(label, value, highlight=False):
        style = f"color:{RED};font-weight:bold;" if highlight else f"color:{text_primary};"
        return (f'<tr><td style="padding:7px 12px;color:{text_secondary};">{label}</td>'
                f'<td style="padding:7px 12px;{style}">{value}</td></tr>')

    # ── Bewertungskarten ─────────────────────────────────────────────────────
    score_p = 0
    score_t = 0
    cards   = ""

    # BITRATE
    if "BITRATE" in active_metrics and br_res:
        avg_br  = br_res.get("avg_bitrate", 0)
        peak_br = br_res.get("peak_bitrate", 0)
        profile = br_res.get("profile", "N/A")
        if avg_br > 0:
            score_t += 1
            if avg_br >= 6000:
                score_p += 1
                cards += _ampel("📊", f"Bitrate – Hoch ({avg_br:.0f} kbps Ø)", GREEN,
                    f"Mit {avg_br:.0f} kbps Durchschnittsbitrate ist das Video sehr gut versorgt. "
                    f"Peak: {peak_br:.0f} kbps. Auch komplexe, schnelle Szenen werden sauber kodiert.",
                    "Optimal für hochauflösende Inhalte.")
            elif avg_br >= 3000:
                score_p += 1
                cards += _ampel("📊", f"Bitrate – Ausreichend ({avg_br:.0f} kbps Ø)", GREEN,
                    f"Die Bitrate von {avg_br:.0f} kbps ist für die meisten Inhalte gut genug. "
                    f"Peak: {peak_br:.0f} kbps.",
                    "Für normalen Gebrauch in Ordnung.")
            elif avg_br >= 1500:
                cards += _ampel("📊", f"Bitrate – Niedrig ({avg_br:.0f} kbps Ø)", YELLOW,
                    f"Die Datenmenge von {avg_br:.0f} kbps ist eher gering. Bei schnellen Szenen "
                    f"oder Details kann die Qualität leiden. Peak: {peak_br:.0f} kbps.",
                    "Neu encodieren mit höherer Bitrate wenn Qualität wichtig ist.")
            else:
                cards += _ampel("📊", f"Bitrate – Sehr niedrig ({avg_br:.0f} kbps Ø)", RED,
                    f"Nur {avg_br:.0f} kbps – das Video ist stark komprimiert. "
                    f"Sichtbare Artefakte sind zu erwarten.",
                    "Neu-Encodierung mit deutlich höherer Bitrate empfohlen.")

    # ARTEFAKTE
    if "ARTIFACTS" in active_metrics and art_res:
        art_result = art_res.get("result", "")
        art_count  = art_res.get("total_count", 0)
        if art_result.startswith("✅"):
            score_t += 1
            score_p += 1
            cards += _ampel("🔍", "Artefakte – Keine erkannt", GREEN,
                "Das Video ist frei von Blocking-Artefakten und Unschärfen durch Kompression. "
                "Es wurden keine sichtbaren Encoding-Fehler gefunden.",
                "Sehr gut – das Video sieht sauber aus.")
        elif art_result.startswith("⚠"):
            score_t += 1
            cards += _ampel("🔍", f"Artefakte – {art_count} Frames betroffen", YELLOW,
                f"In {art_count} Frames wurden Blocking-Artefakte oder Unschärfen erkannt. "
                f"Das sind sichtbare Klötzchen, meist in dunklen oder schnellen Szenen.",
                "Bei hohen Qualitätsansprüchen neu encodieren mit besserem Preset.")
        else:
            cards += _ampel("🔍", "Artefakte – Nicht auswertbar", GRAY,
                (art_result if art_result else "Artefakt-Scan konnte nicht abgeschlossen werden."),
                "Kein Handlungsbedarf – andere Metriken zeigen trotzdem die Qualität.")

    # FRAME DROPS
    if "FRAME DROPS" in active_metrics and frame_drop_res:
        enco_r  = frame_drop_res.get("encoded", {})
        e_drops = enco_r.get("drops", 0)
        e_total = enco_r.get("total_frames", 0)
        e_stat  = enco_r.get("status", "")
        if "Timeout" in e_stat:
            cards += _ampel("🎞️", "Ruckler – Zeitüberschreitung", GRAY,
                "Das Video ist zu lang für einen vollständigen Frame-Scan.",
                "Kein Handlungsbedarf – tritt bei sehr langen Videos auf.")
        elif e_drops == 0:
            score_t += 1
            score_p += 1
            cards += _ampel("🎞️", "Ruckler – Keine Frame-Drops", GREEN,
                f"Alle {e_total} Frames sind vollständig vorhanden. "
                f"Die Wiedergabe sollte absolut flüssig sein – kein einziger Ruckler.",
                "Perfekt – das Video läuft ohne Unterbrechungen.")
        elif e_drops <= 5:
            score_t += 1
            cards += _ampel("🎞️", f"Ruckler – {e_drops} Frames fehlen", YELLOW,
                f"Es fehlen {e_drops} von {e_total} Frames. Das ist sehr wenig und "
                f"in der Praxis kaum wahrnehmbar.",
                "Für normale Wiedergabe kein Problem.")
        else:
            score_t += 1
            pct = (e_drops / e_total * 100) if e_total > 0 else 0
            cards += _ampel("🎞️", f"Ruckler – {e_drops} Frames fehlen ({pct:.1f}%)", RED,
                f"Es fehlen {e_drops} von {e_total} Frames. Bei der Wiedergabe können "
                f"sichtbare Ruckler oder kurze Sprünge auftreten.",
                "Neu-Encodierung empfohlen.")

    # AUDIO
    if "AUDIO" in active_metrics and audio_res:
        enco_a = audio_res.get("encoded", {})
        has_audio = enco_a.get("has_audio", False)
        if not has_audio:
            cards += _ampel("🔇", "Audio – Kein Stream gefunden", GRAY,
                "Das Video enthält keinen Audio-Track.",
                "Falls Audio erwartet wird: Encodierung prüfen.")
        else:
            codec  = enco_a.get("codec", "N/A")
            layout = enco_a.get("channel_layout", "N/A")
            sr     = enco_a.get("sample_rate", "N/A")
            br_a   = enco_a.get("bitrate_kbps", 0)
            br_str = f"{br_a:.0f} kbps" if br_a > 0 else "N/A"
            score_t += 1
            score_p += 1
            cards += _ampel("🔊", f"Audio – {codec} | {layout} | {sr} Hz", GREEN,
                f"Audio-Stream vollständig vorhanden. "
                f"Codec: {codec} · Kanäle: {layout} · Sample-Rate: {sr} Hz · Bitrate: {br_str}.",
                "Audio-Track ist korrekt und vollständig.")

    # ── Gesamtbewertung ──────────────────────────────────────────────────────
    if score_t >= 2:
        pct    = int(score_p / score_t * 100)
        ratio  = score_p / score_t
        if ratio >= 0.85:
            grade, g_color = "Sehr gut",          GREEN
            g_detail = "Das Video hat eine hervorragende Qualität – gut für Streaming, Archivierung oder Weitergabe."
        elif ratio >= 0.65:
            grade, g_color = "Gut",               GREEN
            g_detail = "Die Qualität ist insgesamt gut. Kleinere Schwächen beeinträchtigen das Seherlebnis kaum."
        elif ratio >= 0.45:
            grade, g_color = "Akzeptabel",        YELLOW
            g_detail = "Die Qualität ist noch brauchbar, aber in einigen Bereichen gibt es Einschränkungen."
        else:
            grade, g_color = "Verbesserungsbedarf", RED
            g_detail = "Mehrere Qualitätsmerkmale sind beeinträchtigt. Eine Neu-Encodierung wird empfohlen."

        overall_html = f"""
        <div style="background:{g_color}18;border:2px solid {g_color};border-radius:14px;
                    padding:24px;margin-bottom:24px;text-align:center;">
            <div style="font-size:0.85em;color:{text_secondary};text-transform:uppercase;
                        letter-spacing:1.5px;margin-bottom:8px;">Gesamtbewertung</div>
            <div style="font-size:3.2em;font-weight:900;color:{g_color};line-height:1;">{pct}%</div>
            <div style="font-size:1.1em;font-weight:bold;color:{text_primary};margin:8px 0 4px;">{grade}</div>
            <div style="color:{text_secondary};font-size:0.9em;max-width:580px;margin:0 auto 16px;">{g_detail}</div>
            <div style="background:{border_color};border-radius:99px;height:12px;overflow:hidden;
                        max-width:400px;margin:0 auto;">
                <div style="background:{g_color};width:{pct}%;height:100%;border-radius:99px;"></div>
            </div>
            <div style="font-size:0.8em;color:{text_secondary};margin-top:6px;">
                {score_p} von {score_t} Kriterien erfüllt
            </div>
        </div>"""
    else:
        overall_html = ""

    # ── Technischer Tab ──────────────────────────────────────────────────────
    tech_rows = ""

    # Bitrate-Details
    if "BITRATE" in active_metrics and br_res:
        avg_br  = br_res.get("avg_bitrate", 0)
        peak_br = br_res.get("peak_bitrate", 0)
        profile = br_res.get("profile", "N/A")
        tech_rows += f"""
        <tr style="background:{card_bg};"><td colspan="2" style="padding:10px 12px;font-weight:bold;
            color:{accent};border-top:2px solid {border_color};">📊 Bitrate</td></tr>
        {_info_row("Durchschnittliche Bitrate", f"{avg_br:.2f} kbps" if avg_br > 0 else "N/A")}
        {_info_row("Peak Bitrate",              f"{peak_br:.2f} kbps" if peak_br > 0 else "N/A")}
        {_info_row("Codec Profil",              profile)}"""

    # Artefakte-Details
    if "ARTIFACTS" in active_metrics and art_res:
        art_result = art_res.get("result",      "N/A")
        art_count  = art_res.get("total_count", 0)
        art_frames = art_res.get("frames_scanned", "N/A")
        tech_rows += f"""
        <tr style="background:{card_bg};"><td colspan="2" style="padding:10px 12px;font-weight:bold;
            color:{accent};border-top:2px solid {border_color};">🔍 Artefakte</td></tr>
        {_info_row("Ergebnis",          art_result)}
        {_info_row("Betroffene Frames", str(art_count))}
        {_info_row("Frames gescannt",   str(art_frames))}"""

    # Frame-Drop-Details
    if "FRAME DROPS" in active_metrics and frame_drop_res:
        enco_r  = frame_drop_res.get("encoded", {})
        tech_rows += f"""
        <tr style="background:{card_bg};"><td colspan="2" style="padding:10px 12px;font-weight:bold;
            color:{accent};border-top:2px solid {border_color};">🎞️ Frame-Integrität</td></tr>
        {_info_row("Frame Drops",    str(enco_r.get("drops",        0)))}
        {_info_row("Duplikate",      str(enco_r.get("duplicates",   0)))}
        {_info_row("Frames gesamt",  str(enco_r.get("total_frames", 0)))}
        {_info_row("Status",         enco_r.get("status", "N/A"))}"""

    # Audio-Details
    if "AUDIO" in active_metrics and audio_res:
        enco_a = audio_res.get("encoded", {})
        br_a   = enco_a.get("bitrate_kbps", 0)
        tech_rows += f"""
        <tr style="background:{card_bg};"><td colspan="2" style="padding:10px 12px;font-weight:bold;
            color:{accent};border-top:2px solid {border_color};">🔊 Audio</td></tr>
        {_info_row("Stream vorhanden", "✅ Ja" if enco_a.get("has_audio") else "❌ Nein")}
        {_info_row("Codec",            enco_a.get("codec", "N/A"))}
        {_info_row("Sample-Rate",      str(enco_a.get("sample_rate", "N/A")) + " Hz")}
        {_info_row("Kanäle",           enco_a.get("channel_layout", "N/A"))}
        {_info_row("Bitrate",          f"{br_a:.0f} kbps" if br_a > 0 else "N/A")}
        {_info_row("Bit-Tiefe",        enco_a.get("bit_depth", "N/A"))}
        {_info_row("Streams gesamt",   str(enco_a.get("stream_count", 0)))}"""

    # Video-Info (HDR etc.)
    pix_fmt  = hdr_info.get("pix_fmt",    "N/A")
    hdr_fmt  = hdr_info.get("hdr_format", "SDR")
    bit_dep  = hdr_info.get("bit_depth",  8)
    is_hdr   = hdr_info.get("is_hdr") == "Ja"
    hdr_badge = (f"<span style='background:#f1c40f;color:#000;padding:2px 10px;"
                 f"border-radius:6px;font-size:0.85em;font-weight:bold;'>{hdr_fmt}</span>"
                 if is_hdr else
                 f"<span style='background:{GRAY};color:#fff;padding:2px 10px;"
                 f"border-radius:6px;font-size:0.85em;'>SDR</span>")

    tech_rows += f"""
        <tr style="background:{card_bg};"><td colspan="2" style="padding:10px 12px;font-weight:bold;
            color:{accent};border-top:2px solid {border_color};">🎨 Video-Info</td></tr>
        {_info_row("HDR / Farbraum", hdr_badge)}
        {_info_row("Pixel Format",  pix_fmt)}
        {_info_row("Farbtiefe",     f"{bit_dep} Bit")}"""

    # ── HTML zusammenbauen ───────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Solo-Scan Report – {file_name}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: {bg_color};
            color: {text_primary};
            margin: 0; padding: 20px;
        }}
        .container {{
            max-width: 900px; margin: auto;
            background: {container_bg};
            padding: 30px; border-radius: 14px;
            box-shadow: 0 10px 40px rgba(100,0,200,0.15);
        }}
        h2.section-title {{
            background: {table_header}; color: {accent};
            padding: 10px 15px; border-radius: 4px;
            margin-top: 30px; font-size: 1.15em;
            border-left: 5px solid {accent};
        }}
        .tab-nav {{
            display: flex; gap: 0;
            border-bottom: 2px solid {border_color};
            margin-bottom: 28px; margin-top: 16px;
        }}
        .tab-btn {{
            padding: 11px 26px; cursor: pointer;
            background: none; border: none;
            font-size: 0.95em; font-weight: 600;
            color: {text_secondary};
            border-bottom: 3px solid transparent;
            margin-bottom: -2px; transition: all 0.2s;
            font-family: inherit;
        }}
        .tab-btn:hover {{ color: {accent}; }}
        .tab-btn.active {{
            color: {accent};
            border-bottom: 3px solid {accent};
        }}
        .tab-content {{ display: none; }}
        table {{ width: 100%; border-collapse: collapse; border-radius: 8px; overflow: hidden; }}
        td {{ border-bottom: 1px solid {border_color}; }}
    </style>
</head>
<body>
<div class="container">

    <!-- HEADER -->
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:4px;">
        <span style="font-size:2.2em;">🔍</span>
        <div>
            <div style="font-size:1.7em;font-weight:900;color:{accent};line-height:1.1;">
                Solo-Scan Report
            </div>
            <div style="font-size:0.85em;color:{text_secondary};margin-top:3px;">
                Referenzloser Qualitäts-Check &nbsp;·&nbsp;
                <span style="color:{text_primary};font-weight:600;">{file_name}</span>
            </div>
        </div>
    </div>

    <div style="background:{card_bg};border:1px solid {border_color};border-left:4px solid {accent};
                border-radius:8px;padding:12px 18px;margin:16px 0;font-size:0.87em;color:{text_secondary};">
        <strong style="color:{accent};">ℹ️ Kein Original erforderlich</strong> &nbsp;–&nbsp;
        Dieser Report misst ausschließlich absolute Qualitätsmerkmale des Videos (Bitrate,
        Artefakte, Frame-Drops, Audio). Vergleichsmetriken wie VMAF, SSIM und PSNR
        sind ohne Referenzvideo nicht verfügbar.
    </div>

    <!-- TAB NAVIGATION -->
    <div class="tab-nav">
        <button class="tab-btn active" onclick="switchTab('bewertung')">🎯 Bewertung</button>
        <button class="tab-btn"        onclick="switchTab('technik')">🛠 Technische Daten</button>
    </div>

    <!-- TAB: BEWERTUNG -->
    <div id="tab-bewertung" class="tab-content">
        {overall_html}
        {cards if cards else f"<p style='color:{text_secondary};'>Keine Metriken aktiv.</p>"}
    </div>

    <!-- TAB: TECHNIK -->
    <div id="tab-technik" class="tab-content">
        <table>
            <tbody>
                {tech_rows if tech_rows else
                 f'<tr><td style="padding:15px;color:{text_secondary};">Keine technischen Daten verfügbar.</td></tr>'}
            </tbody>
        </table>
    </div>

    <div style="margin-top:40px;text-align:center;color:{text_secondary};
                font-size:11px;border-top:1px solid {border_color};padding-top:20px;">
        Solo-Scan erstellt am {datetime.datetime.now().strftime("%d.%m.%Y um %H:%M:%S")}
        &nbsp;|&nbsp; Video Quality Analyzer PRO
    </div>

</div>
<script>
function switchTab(name) {{
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    var el = document.getElementById('tab-' + name);
    if (el) el.style.display = 'block';
    event.target.classList.add('active');
}}
document.addEventListener('DOMContentLoaded', function() {{
    document.getElementById('tab-bewertung').style.display = 'block';
}});
</script>
</body>
</html>"""

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        return report_path
    except Exception as e:
        print(f"Fehler beim Speichern des Solo-Reports: {e}")
        return None