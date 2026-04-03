import os
import re
import json
import time
import threading
import subprocess
import platform
import webbrowser
import numpy as np

from modules.ui.console_manager import console
from modules.analysis.hdr_checker import HDRChecker
from modules.analysis.bitrate_analysis import BitrateAnalyzer
from modules.analysis.scene_analysis import SceneAnalyzer
from modules.analysis.screenshot_tool import ScreenshotTool
from modules.analysis.frame_drop_detector import detect_frame_drops
from modules.analysis.audio_analyzer import AudioAnalyzer
from modules.artifact_detection.artifact_detector import ArtifactDetector
from modules.visualization.artifact_heatmap import ArtifactHeatmapGenerator
from modules.visualization.vmaf_graph import create_vmaf_graph
from modules.reporting.html_report import generate_full_report, generate_solo_report
from modules.processing.filter_factory import get_analysis_filters
from modules.path_utils import APP_PATH, get_tool

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


class AnalysisRunner:
    def __init__(self, ffmpeg_path, app_path, dirs, ui_callbacks):
        self.ffmpeg_path      = ffmpeg_path
        self.app_path         = APP_PATH   # Immer aus path_utils – ignoriert übergebenen app_path
        self.dirs             = dirs
        self.cb               = ui_callbacks
        self.proc             = None
        self._sync_proc       = None   # Auto-Sync Subprozess (für Stop während Auto-Sync)
        self.analysis_running = False
        self._lock            = threading.Lock()
        self._artifact_stop   = threading.Event()
        self.active_metrics   = set()

    # ─────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────

    def start(self, orig, enco, subsample, gpu_active, dark_mode, active_metrics=None, offset_sec=0.0, solo_mode=False, gpu_type="cuda", gpu_device=None):
        """Startet die Analyse in einem eigenen Thread."""
        with self._lock:
            if self.analysis_running:
                return
            self.analysis_running = True

        self._artifact_stop.clear()
        with self._lock:
            self._sync_proc = None
        self.offset_sec = offset_sec
        self.solo_mode  = solo_mode
        self.gpu_type   = gpu_type or "cuda"
        self.gpu_device = gpu_device  # D3D-Adapter-Index für d3d11va/qsv (None = nicht angegeben)

        # FIX: aktive Metriken übernehmen – Standard: alle
        self.active_metrics = active_metrics or {
            "VMAF", "SSIM", "PSNR", "BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"
        }

        target = self._run_solo if self.solo_mode else self._run
        threading.Thread(
            target=target,
            args=(orig, enco, subsample, gpu_active, dark_mode),
            daemon=True
        ).start()

    def stop(self):
        """Bricht die laufende Analyse ab."""
        self._artifact_stop.set()
        with self._lock:
            if self._sync_proc:
                self._sync_proc.terminate()
                try:
                    self._sync_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._sync_proc.kill()
                self._sync_proc = None
            if self.proc:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                self.proc = None
            self.analysis_running = False
        console.print_warning("Analyse durch Benutzer abgebrochen.")
        self.cb["handle_abort_ui"]()

    def is_running(self):
        with self._lock:
            return self.analysis_running

    # ─────────────────────────────────────────
    # INTERNAL PIPELINE
    # ─────────────────────────────────────────

    def _run(self, orig, enco, subsample, gpu_active, dark_mode):
        try:
            if not os.path.exists(orig) or not os.path.exists(enco):
                console.print_error("Analyse fehlgeschlagen: Ungültige Dateipfade.")
                with self._lock:
                    self.analysis_running = False
                return

            console.print_step("STARTING VIDEO ANALYSIS")
            console.print_info(
                f"Aktive Metriken: {', '.join(sorted(self.active_metrics))}"
            )

            # 1. HDR Check (immer – wird für Filter benötigt)
            hdr_info = HDRChecker().analyze(enco, self.ffmpeg_path)

            # 2. Dynamische Filter (immer)
            # Auflösungen beider Videos ermitteln.
            # Encoded ist oft gecroppt (Balken entfernt) → kleiner als Original.
            # → Original bekommt einen Crop-Filter, der die Balken entfernt,
            #   bevor beide auf exakt gleiche Größe skaliert werden.
            enc_w, enc_h = self._get_video_resolution(enco)
            orig_w, orig_h = self._get_video_resolution(orig)

            # Fallback: wenn JSON-Methode keine Dimensionen liefert (z.B. ffprobe-Fehler),
            # einfachere CSV-Abfrage versuchen – verhindert scale=-2 mit unterschiedlichen
            # Quellhöhen, das zu libvmaf "input height must match" führt.
            if enc_h is None:
                enc_w, enc_h = self._get_resolution_fallback(enco)
            if orig_h is None:
                orig_w, orig_h = self._get_resolution_fallback(orig)

            # th immer explizit setzen – scale=-2 bei unterschiedlichen Höhen ist der Bug.
            tw = enc_w or orig_w or 1920
            th = enc_h or orig_h or 1080

            enco_filter = get_analysis_filters(
                hdr_info, self.ffmpeg_path, target_width=tw, target_height=th
            )

            # Crop-Präfix für Original berechnen (symmetrisch, Balken oben/unten/seitlich)
            if enc_w and enc_h and orig_w and orig_h and (orig_w > enc_w or orig_h > enc_h):
                crop_x = max(0, (orig_w - enc_w) // 2)
                crop_y = max(0, (orig_h - enc_h) // 2)
                crop_prefix = f"crop={enc_w}:{enc_h}:{crop_x}:{crop_y},"
                console.print_info(
                    f"Balken-Crop erkannt: Original {orig_w}×{orig_h} → "
                    f"crop={enc_w}:{enc_h}:{crop_x}:{crop_y}"
                )
            else:
                crop_prefix = ""

            orig_filter = crop_prefix + get_analysis_filters(
                hdr_info, self.ffmpeg_path, target_width=tw, target_height=th
            )

            # 3. Auto-Sync (nur wenn AUDIO aktiv und kein manueller Versatz gesetzt)
            if "AUDIO" in self.active_metrics and self.offset_sec == 0.0:
                self.cb["set_progress_busy"]("Audio-Sync-Erkennung läuft...")
                detected = self._detect_audio_offset(orig, enco)
                if detected != 0.0:
                    self.offset_sec = detected
                    console.print_info(
                        f"Auto-Sync: Versatz erkannt → {detected:+.1f}s "
                        f"({'Original' if detected > 0 else 'Encoded'} wird übersprungen)"
                    )
                else:
                    console.print_info("Auto-Sync: Kein signifikanter Versatz erkannt (0.0s).")

            with self._lock:
                if not self.analysis_running:
                    return

            # 4. VMAF + SSIM + PSNR via FFmpeg
            # Nur starten wenn mindestens eine dieser Metriken aktiv ist
            ssim_f = 0.0
            psnr_f = 0.0
            abs_log_json = os.path.abspath(
                os.path.join(self.app_path, "temp", "vmaf.json")
            )

            run_vmaf = "VMAF"   in self.active_metrics
            run_ssim = "SSIM"   in self.active_metrics
            run_psnr = "PSNR"   in self.active_metrics

            if run_vmaf or run_ssim or run_psnr:
                if self.offset_sec != 0.0:
                    console.print_info(
                        f"Video-Versatz aktiv: {self.offset_sec:+.1f}s – "
                        f"{'Original' if self.offset_sec > 0 else 'Encoded'} wird um "
                        f"{abs(self.offset_sec):.1f}s übersprungen."
                    )
                ssim_f, psnr_f = self._run_ffmpeg_metrics(
                    orig, enco, abs_log_json,
                    subsample, gpu_active, enco_filter, orig_filter,
                    run_vmaf, run_ssim, run_psnr
                )
            else:
                console.print_info("VMAF / SSIM / PSNR übersprungen (nicht ausgewählt).")

            with self._lock:
                still_running = self.analysis_running
            if not still_running:
                return

            if run_vmaf or run_ssim or run_psnr:
                console.print_success("Primäre Metriken abgeschlossen.")
            self.cb["set_progress_busy"]("Heatmap wird erstellt...")

            # 4. Heatmap (nur wenn VMAF aktiv und Log vorhanden)
            if run_vmaf and os.path.exists(abs_log_json):
                ArtifactHeatmapGenerator(self.ffmpeg_path).generate(abs_log_json)

            with self._lock:
                if not self.analysis_running:
                    return

            # 5. Bitrate
            br_res = {}
            if "BITRATE" in self.active_metrics:
                self.cb["set_progress_busy"]("Bitrate-Analyse läuft...")
                br_res = BitrateAnalyzer().analyze(enco)
            else:
                console.print_info("Bitrate übersprungen.")

            with self._lock:
                if not self.analysis_running:
                    return

            # 6. Artefakte
            art_res = {}
            if "ARTIFACTS" in self.active_metrics:
                self.cb["set_progress_busy"]("Artefakt-Scan läuft...")
                art_frames = self.cb.get("get_artifact_frames", lambda: 1000)()
                console.print_info(f"Artefakt-Scan läuft ({art_frames} Frames)...")
                art_res = ArtifactDetector().detect(
                    enco, max_frames=art_frames,
                    stop_event=self._artifact_stop,
                )
            else:
                console.print_info("Artefakt-Scan übersprungen.")

            with self._lock:
                if not self.analysis_running:
                    return

            # 7. Frame Drops
            frame_drop_res = None
            if "FRAME DROPS" in self.active_metrics:
                self.cb["set_progress_busy"]("Frame-Drop Analyse läuft...")
                console.print_info("Frame-Drop Analyse läuft...")
                drop_orig = detect_frame_drops(self.ffmpeg_path, orig, label="Original")

                # Encoded überspringen wenn Original bereits fehlgeschlagen –
                # ohne Referenzwert ist der Vergleich sinnlos
                orig_failed = "Fehler" in drop_orig.get("status", "")
                if orig_failed:
                    console.print_warning(
                        "Frame-Drop Analyse: Original fehlgeschlagen – "
                        "Encoded wird übersprungen (kein Vergleich möglich)."
                    )
                    drop_enco = {
                        "drops": 0, "duplicates": 0, "total_frames": 0,
                        "status": "Übersprungen – Original fehlgeschlagen"
                    }
                else:
                    drop_enco = detect_frame_drops(self.ffmpeg_path, enco, label="Encoded")
                    console.print_info(
                        f"Frame-Drops → Original: {drop_orig['status']} | "
                        f"Encoded: {drop_enco['status']}"
                    )

                frame_drop_res = {
                    "original": drop_orig,
                    "encoded":  drop_enco
                }
            else:
                console.print_info("Frame-Drop Analyse übersprungen (nicht ausgewählt).")

            with self._lock:
                if not self.analysis_running:
                    return

            # 8. Audio-Analyse
            audio_res = None
            if "AUDIO" in self.active_metrics:
                self.cb["set_progress_busy"]("Audio-Analyse läuft...")
                audio_res = AudioAnalyzer().compare(orig, enco)
            else:
                console.print_info("Audio-Analyse übersprungen.")

            # 9. Worst Scenes (nur wenn VMAF aktiv)
            final_worst = []
            if run_vmaf and os.path.exists(abs_log_json):
                final_worst = self._extract_worst_scenes(abs_log_json, enco)

            # 9. VMAF Graph + Stats
            vmaf_avg, vmaf_min = 0.0, 0.0
            if run_vmaf and os.path.exists(abs_log_json):
                vmaf_avg, vmaf_min = self._get_vmaf_stats(abs_log_json)
                create_vmaf_graph(log_path=abs_log_json, dark_mode=dark_mode)

            # 10. HTML Report
            rep = generate_full_report(
                abs_log_json, br_res, art_res, enco,
                ssim_f, psnr_f, vmaf_avg, vmaf_min,
                final_worst, hdr_info,
                frame_drop_res = frame_drop_res,
                audio_res      = audio_res,
                dark_mode      = dark_mode,
                active_metrics = self.active_metrics
            )

            if rep:
                # Plattformübergreifend korrekter file:// Pfad via pathlib
                from pathlib import Path
                report_url = Path(os.path.abspath(rep)).as_uri()
                webbrowser.open(report_url)
                console.print_success("✅ Analyse abgeschlossen.")

            self.cb.get("on_results", lambda r: None)({
                "mode":     "comparison",
                "vmaf_avg": round(vmaf_avg, 3),
                "vmaf_min": round(vmaf_min, 3),
                "ssim":     round(ssim_f, 5),
                "psnr":     round(psnr_f, 3),
            })
            self.cb["on_done"]()

        except Exception as e:
            console.print_error(f"Kritischer Fehler: {e}")
            self.cb["handle_abort_ui"]()
        finally:
            with self._lock:
                self.analysis_running = False

    def _run_solo(self, _orig, enco, _subsample, gpu_active, dark_mode):
        """
        Referenzloser Scan – kein Original nötig.
        Misst: Bitrate, Artefakte, Frame-Drops, Audio direkt am Encode.
        VMAF / SSIM / PSNR werden übersprungen (brauchen Referenz).
        """
        SOLO_METRICS = {"BITRATE", "ARTIFACTS", "FRAME DROPS", "AUDIO"}

        try:
            if not os.path.exists(enco):
                console.print_error("Solo-Scan fehlgeschlagen: Encode-Datei nicht gefunden.")
                with self._lock:
                    self.analysis_running = False
                return

            console.print_step("STARTING SOLO SCAN (REFERENZLOS)")
            active = self.active_metrics & SOLO_METRICS
            console.print_info(f"Aktive Metriken: {', '.join(sorted(active))}")

            # HDR-Info (für Report-Badge)
            hdr_info = HDRChecker().analyze(enco, self.ffmpeg_path)
            console.print_info(f"HDR Format erkannt: {hdr_info.get('hdr_format', 'SDR')}")

            # Bitrate
            br_res = {}
            if "BITRATE" in active:
                self.cb["set_progress_busy"]("Bitrate-Analyse läuft...")
                br_res = BitrateAnalyzer().analyze(enco)
                console.print_info("Bitrate-Analyse abgeschlossen.")

            with self._lock:
                if not self.analysis_running:
                    return

            # Artefakte
            art_res = {}
            if "ARTIFACTS" in active:
                self.cb["set_progress_busy"]("Artefakt-Scan läuft...")
                art_frames = self.cb.get("get_artifact_frames", lambda: 1000)()
                console.print_info(f"Artefakt-Scan läuft ({art_frames} Frames)...")
                art_res = ArtifactDetector().detect(
                    enco, max_frames=art_frames,
                    stop_event=self._artifact_stop,
                )
                console.print_info("Artefakt-Erkennung abgeschlossen.")

            with self._lock:
                if not self.analysis_running:
                    return

            # Frame Drops
            frame_drop_res = None
            if "FRAME DROPS" in active:
                self.cb["set_progress_busy"]("Frame-Drop Analyse läuft...")
                console.print_info("Frame-Drop Analyse läuft...")
                drop_enco = detect_frame_drops(self.ffmpeg_path, enco, label="Encoded")
                console.print_info(f"Encoded → {drop_enco['status']} (Frames: {drop_enco['total_frames']})")
                frame_drop_res = {
                    "original": {
                        "drops": 0, "duplicates": 0, "total_frames": 0,
                        "status": "⏭ Solo-Scan – kein Original"
                    },
                    "encoded": drop_enco
                }

            with self._lock:
                if not self.analysis_running:
                    return

            # Audio
            audio_res = None
            if "AUDIO" in active:
                self.cb["set_progress_busy"]("Audio-Analyse läuft...")
                audio_data = AudioAnalyzer()._analyze_single(enco)
                audio_res = {
                    "original": {"has_audio": False},
                    "encoded":  audio_data,
                    "issues":   [],
                    "summary":  f"Solo-Scan: {audio_data.get('status', 'N/A')}"
                }
                console.print_info("Audio-Analyse abgeschlossen.")

            # Report generieren – eigener Solo-Report
            rep = generate_solo_report(
                br_res         = br_res,
                art_res        = art_res,
                enco_path      = enco,
                hdr_info       = hdr_info,
                frame_drop_res = frame_drop_res,
                audio_res      = audio_res,
                dark_mode      = dark_mode,
                active_metrics = active,
            )

            if rep:
                from pathlib import Path
                webbrowser.open(Path(os.path.abspath(rep)).as_uri())
                console.print_success("✅ Solo-Scan abgeschlossen.")

            self.cb.get("on_results", lambda r: None)({"mode": "solo"})
            self.cb["on_done"]()

        except Exception as e:
            console.print_error(f"Solo-Scan Fehler: {e}")
            self.cb["handle_abort_ui"]()
        finally:
            with self._lock:
                self.analysis_running = False

    def _run_ffmpeg_metrics(self, orig, enco, abs_log_json,
                             subsample, gpu_active, enco_filter, orig_filter,
                             run_vmaf, run_ssim, run_psnr):
        """
        Startet FFmpeg filter_complex für die gewählten Metriken.
        Gibt (ssim, psnr) als Float-Tuple zurück.
        FIX: Nur aktive Metriken werden in filter_complex eingebaut.
        """
        total_sec = self._get_video_duration(orig)
        start_t   = time.time()
        ssim_f    = 0.0
        psnr_f    = 0.0

        # Anzahl Splits berechnen (mind. 1 pro aktiver Metrik)
        n_splits = sum([run_vmaf, run_ssim, run_psnr])

        # Relativer Pfad vermeidet alle Windows-Escaping-Probleme mit Laufwerksbuchstaben
        # und Leerzeichen im Pfad. FFmpeg schreibt vmaf.json ins cwd (= vmaf_dir).
        vmaf_dir  = os.path.dirname(abs_log_json)
        clean_log = "vmaf.json"

        # Filter-Complex dynamisch aufbauen
        split_labels_e = [f"[e{i+1}]" for i in range(n_splits)]
        split_labels_o = [f"[o{i+1}]" for i in range(n_splits)]

        f_parts = [
            f"[0:v]{enco_filter},split={n_splits}{''.join(split_labels_e)}",
            f"[1:v]{orig_filter},split={n_splits}{''.join(split_labels_o)}"
        ]

        idx = 1
        if run_vmaf:
            f_parts.append(
                f"[e{idx}][o{idx}]libvmaf=log_path={clean_log}"
                f":log_fmt=json:n_subsample={subsample}:n_threads=4"
            )
            idx += 1
        if run_ssim:
            f_parts.append(f"[e{idx}][o{idx}]ssim")
            idx += 1
        if run_psnr:
            f_parts.append(f"[e{idx}][o{idx}]psnr")
            idx += 1

        f_complex = "; ".join(f_parts)

        # offset_sec > 0: Original hat Intro → Original um offset überspringen (Input 1)
        # offset_sec < 0: Encoded hat Intro  → Encoded  um |offset| überspringen (Input 0)
        offset = getattr(self, 'offset_sec', 0.0)

        # libvmaf / ssim / psnr sind CPU-Filter – nur CUDA ist kompatibel
        # (d3d11va liefert NV12-Frames die libvmaf nicht verarbeiten kann).
        # Für andere Analysen (z.B. Artefakt-Scan) kann gpu_device genutzt werden.
        hwaccel_args = ["-hwaccel", "cuda"] if (gpu_active and self.gpu_type == "cuda") else []

        cmd = [self.ffmpeg_path, "-hide_banner", "-y"]
        cmd += hwaccel_args
        if offset < 0:
            cmd += ["-ss", f"{abs(offset):.4f}"]   # Encoded überspringen
        cmd += ["-i", enco]
        cmd += hwaccel_args
        if offset > 0:
            cmd += ["-ss", f"{offset:.4f}"]         # Original überspringen
        cmd += ["-i", orig, "-filter_complex", f_complex, "-f", "null", "-"]

        metrics_str = " + ".join(
            m for m, active in [("VMAF", run_vmaf), ("SSIM", run_ssim), ("PSNR", run_psnr)]
            if active
        )
        console.print_info(f"Berechne {metrics_str}...")

        with self._lock:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=CREATE_NO_WINDOW,
                cwd=vmaf_dir,   # vmaf.json wird relativ ins temp-Verzeichnis geschrieben
            )
            _proc = self.proc  # lokale Referenz – stop() setzt self.proc=None, _proc bleibt gültig

        last_lines = []
        for line in _proc.stdout:
            with self._lock:
                running = self.analysis_running
            if not running:
                break

            stripped = line.rstrip()
            last_lines.append(stripped)
            if len(last_lines) > 40:
                last_lines.pop(0)

            if "time=" in line:
                tm = re.search(r'time=(\d+):(\d+):(\d+)', line)
                if tm and total_sec > 0:
                    h, m, s = map(int, tm.groups())
                    perc = min(100, ((h * 3600 + m * 60 + s) / total_sec) * 100)
                    self.cb["update_ui"](perc, start_t)

            if run_ssim and "All:" in line:
                match = re.search(r"All:(\d+\.\d+)", line)
                if match:
                    ssim_f = float(match.group(1))

            if run_psnr and "average:" in line:
                match = re.search(r"average:(\d+\.\d+)", line)
                if match:
                    psnr_f = float(match.group(1))

        _proc.wait()

        with self._lock:
            user_aborted = not self.analysis_running

        if _proc.returncode not in (0, None) and not user_aborted:
            console.print_error(
                f"FFmpeg Metriken fehlgeschlagen (Exit-Code {_proc.returncode}). "
                f"Letzte Ausgabe:"
            )
            error_keywords = ("error", "invalid", "failed", "cannot", "unable", "no such")
            for l in last_lines:
                ls = l.strip()
                if ls and any(kw in ls.lower() for kw in error_keywords):
                    console.print_error(f"  {ls}")

        return ssim_f, psnr_f

    def _extract_worst_scenes(self, abs_log_json, enco):
        """Ermittelt die schlechtesten Szenen und extrahiert Screenshots."""
        s_analyzer = SceneAnalyzer()
        worst = s_analyzer.get_worst_scenes(abs_log_json, enco)
        if not worst and os.path.exists(abs_log_json):
            worst = s_analyzer.get_absolute_worst_frames(abs_log_json, enco, limit=3)

        shot_tool   = ScreenshotTool(self.ffmpeg_path)
        final_worst = []

        for i, scene in enumerate(worst):
            img_name      = f"worst_scene_{i + 1}.jpg"
            full_img_path = os.path.join(self.dirs["screenshots"], img_name)
            if shot_tool.extract_frame(
                enco,
                scene.get('frame', 0),
                full_img_path,
                fallback_timestamp=scene.get('timestamp_raw')
            ):
                scene['screenshot'] = img_name
                final_worst.append(scene)

        return final_worst

    def _get_vmaf_stats(self, log_path):
        """Liest VMAF Durchschnitt und Minimum aus dem JSON-Log.
        Nutzt pooled_metrics.vmaf.min von libvmaf direkt – robuster als
        Frame-by-Frame-Minimum, da libvmaf Warmup-Artefakte intern filtert."""
        try:
            with open(log_path, encoding='utf-8', errors='replace') as f:
                data = json.load(f)
            pooled = data.get("pooled_metrics", {}).get("vmaf", {})
            avg_v  = pooled.get("mean", 0.0)
            min_v  = pooled.get("min")
            if min_v is None:
                # Fallback für ältere libvmaf-Versionen ohne pooled_metrics
                scores = [
                    fr["metrics"]["vmaf"]
                    for fr in data.get("frames", [])
                    if fr.get("metrics", {}).get("vmaf") is not None
                    and fr["metrics"]["vmaf"] > 2.0
                ]
                min_v = min(scores) if scores else 0.0
            return avg_v, min_v
        except (OSError, json.JSONDecodeError, KeyError, ValueError, TypeError):
            return 0.0, 0.0

    def _detect_audio_offset(self, orig_path, enco_path):
        """
        Erkennt den zeitlichen Versatz zwischen zwei Videos via FFT-Kreuzkorrelation
        der Audio-Spuren. Gibt den Versatz in Sekunden zurück (gerundet auf 0.5s).
        Positiv = Original führt (hat Intro), Negativ = Encoded führt.
        Gibt 0.0 zurück wenn kein Audio vorhanden oder Versatz < 0.5s.
        """
        SAMPLE_RATE = 8000   # Niedrige Rate reicht für Sync-Erkennung
        DURATION    = 120    # Erste 2 Minuten analysieren
        MIN_OFFSET  = 0.5    # Kleinere Versätze als Rauschen ignorieren
        MAX_OFFSET  = 300.0  # Versätze > 5 Minuten als unrealistisch ablehnen

        def _extract(path):
            cmd = [
                self.ffmpeg_path, "-hide_banner", "-loglevel", "error",
                "-i", path,
                "-t", str(DURATION),
                "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                "-acodec", "pcm_f32le", "-f", "f32le", "pipe:1"
            ]
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW
                )
                with self._lock:
                    self._sync_proc = proc
                raw = proc.stdout.read()
                proc.wait()
                with self._lock:
                    self._sync_proc = None
                return np.frombuffer(raw, dtype=np.float32)
            except Exception:
                return np.array([], dtype=np.float32)

        try:
            audio_orig = _extract(orig_path)
            audio_enco = _extract(enco_path)

            if len(audio_orig) < 1000 or len(audio_enco) < 1000:
                console.print_info("Auto-Sync: Kein Audio gefunden – Erkennung übersprungen.")
                return 0.0

            # FFT-Kreuzkorrelation – O(n log n)
            n     = len(audio_orig) + len(audio_enco) - 1
            n_fft = 1 << int(np.ceil(np.log2(n)))

            F_orig = np.fft.rfft(audio_orig, n=n_fft)
            F_enco = np.fft.rfft(audio_enco, n=n_fft)
            corr   = np.fft.irfft(F_orig * np.conj(F_enco), n=n_fft)

            lag = int(np.argmax(corr[:n]))
            if lag > n // 2:
                lag -= n_fft

            offset_sec = lag / SAMPLE_RATE

            # Unplausible Werte verwerfen
            if abs(offset_sec) < MIN_OFFSET or abs(offset_sec) > MAX_OFFSET:
                return 0.0

            return round(offset_sec * 2) / 2   # Auf 0.5s runden

        except Exception as e:
            console.print_warning(f"Auto-Sync Fehler: {e}")
            return 0.0

    def _ffprobe_json(self, path, show_streams=False, show_format=False):
        """Führt ffprobe aus und gibt das geparste JSON-Dict zurück."""
        ffprobe = get_tool("ffprobe")
        args = [ffprobe, "-v", "quiet", "-print_format", "json"]
        if show_streams:
            args.append("-show_streams")
        if show_format:
            args.append("-show_format")
        args.append(path)
        try:
            result = subprocess.run(
                args, capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=30, creationflags=CREATE_NO_WINDOW
            )
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            console.print_warning(f"ffprobe Timeout: {os.path.basename(path)}")
            return {}
        except (OSError, json.JSONDecodeError, ValueError) as e:
            console.print_error(f"ffprobe Fehler: {e}")
            return {}

    def _get_video_resolution(self, path):
        """Liest Breite und Höhe des ersten Video-Streams via ffprobe JSON."""
        data = self._ffprobe_json(path, show_streams=True)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                w = stream.get("width")
                h = stream.get("height")
                if w and h:
                    return int(w), int(h)
        return None, None

    def _get_resolution_fallback(self, path):
        """Einfache ffprobe-Abfrage als Fallback wenn JSON-Methode fehlschlägt."""
        try:
            ffprobe = get_tool("ffprobe")
            result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", path],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=15, creationflags=CREATE_NO_WINDOW
            )
            # Ausgabe: "1920,1080"
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return None, None

    def _get_video_duration(self, path):
        """Liest die Videodauer in Sekunden via ffprobe JSON."""
        data = self._ffprobe_json(path, show_format=True)
        dur = data.get("format", {}).get("duration")
        if dur:
            try:
                return float(dur)
            except ValueError:
                pass
        console.print_warning("Videodauer nicht ermittelbar.")
        return 0