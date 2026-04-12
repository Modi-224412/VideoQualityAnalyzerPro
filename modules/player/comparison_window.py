import tkinter as tk
from tkinter import ttk, messagebox
import cv2
import numpy as np
import threading
import time
import subprocess
import sounddevice as sd
import platform
import os
from PIL import Image, ImageTk

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


class ComparisonWindow:
    """
    Einzel-Fenster Comparison Player – Original (links) vs. Encoded (rechts).
    - Seek-Audio-Fix: Debounce + sauberer Neustart nur beim MouseRelease
    - Frame-by-Frame Navigation
    - Fullscreen (F / Doppelklick)
    - Keyboard Shortcuts
    - Zentriertes Canvas-Rendering
    - Kein Zoom (entfernt)
    """

    def __init__(self, parent, original_path, encoded_path,
                 ffmpeg_path, screenshot_dir=None,
                 offset_sec=0.0, offset_callback=None):
        self.parent           = parent
        self.original_path    = original_path
        self.encoded_path     = encoded_path
        self.ffmpeg_path      = ffmpeg_path
        self.screenshot_dir   = screenshot_dir or os.path.dirname(encoded_path)
        self.offset_callback  = offset_callback  # Wird aufgerufen wenn Versatz sich ändert

        self.playing       = False
        self.loop          = False
        self.volume        = 0.8
        self.current_frame = 0
        self.total_frames  = 0
        self.fps           = 25.0
        self._fullscreen   = False
        self._init_offset_sec = offset_sec               # Startwert für _build_ui
        self._offset_frames   = int(offset_sec * 25.0)  # Wird nach fps-Erkennung neu gesetzt

        self.cap_orig      = None
        self.cap_enco      = None

        # Crop-Koordinaten (y1, y2, x1, x2) wenn Videos unterschiedliche Dimensionen haben
        self._orig_crop    = None
        self._enco_crop    = None

        self._stop_video   = threading.Event()
        self._stop_audio   = threading.Event()
        self._seek_pending = None
        self._seek_lock    = threading.Lock()

        self._frame_queue  = []
        self._queue_lock   = threading.Lock()
        self._photo_orig   = None
        self._photo_enco   = None

        self._playback_start_time  = 0.0
        self._playback_start_frame = 0

        # Debounce: Audio erst nach Ende des Timeline-Drags neu starten
        self._user_is_dragging = False

        self.win = tk.Toplevel(parent)
        self.win.title("📺 Comparison Player – Original vs. Encoded")
        self.win.configure(bg="#1e1e1e")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.resizable(True, True)

        self._build_ui()
        self._bind_keys()
        self._open_videos()
        self._render_loop()

    # ─────────────────────────────────────────
    # UI AUFBAU
    # ─────────────────────────────────────────

    def _build_ui(self):
        label_row = tk.Frame(self.win, bg="#1e1e1e")
        label_row.pack(fill=tk.X, padx=5, pady=(5, 0))

        tk.Label(
            label_row, text="📁  ORIGINAL",
            bg="#1e1e1e", fg="#f1c40f",
            font=('Arial', 10, 'bold')
        ).pack(side=tk.LEFT, expand=True)

        tk.Label(
            label_row, text="🎬  ENCODED",
            bg="#1e1e1e", fg="#3498db",
            font=('Arial', 10, 'bold')
        ).pack(side=tk.RIGHT, expand=True)

        canvas_row = tk.Frame(self.win, bg="#000000")
        canvas_row.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas_orig = tk.Canvas(
            canvas_row, bg="#000000",
            width=640, height=360,
            highlightthickness=0
        )
        self.canvas_orig.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas_orig.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())

        # Trennlinie in Akzentfarbe
        tk.Frame(canvas_row, bg="#2ecc71", width=2).pack(side=tk.LEFT, fill=tk.Y)

        self.canvas_enco = tk.Canvas(
            canvas_row, bg="#000000",
            width=640, height=360,
            highlightthickness=0
        )
        self.canvas_enco.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.canvas_enco.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())

        self.timeline_var = tk.DoubleVar(value=0)
        self.timeline = ttk.Scale(
            self.win, from_=0, to=100,
            orient=tk.HORIZONTAL,
            variable=self.timeline_var,
            command=self._on_seek_drag
        )
        self.timeline.pack(fill=tk.X, padx=10, pady=(0, 2))
        self.timeline.bind("<ButtonRelease-1>", self._on_seek_release)

        self.time_label = tk.Label(
            self.win, text="00:00 / 00:00",
            bg="#1e1e1e", fg="#aaaaaa",
            font=('Consolas', 9)
        )
        self.time_label.pack()

        ctrl = tk.Frame(self.win, bg="#2d2d2d", pady=8)
        ctrl.pack(fill=tk.X, padx=5, pady=5)

        btn_style = {
            "relief": "flat", "bd": 0, "highlightthickness": 0,
            "bg": "#3d3d3d", "fg": "white",
            "activebackground": "#555",
            "font": ('Arial', 10), "padx": 8, "pady": 4,
            "cursor": "hand2"
        }

        btn_row = tk.Frame(ctrl, bg="#2d2d2d")
        btn_row.pack()

        tk.Button(
            btn_row, text="⏮ -5s",
            command=lambda: self._skip(-5), **btn_style
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            btn_row, text="◀",
            command=lambda: self._step_frame(-1),
            **{**btn_style, "font": ('Arial', 9)}
        ).pack(side=tk.LEFT, padx=2)

        self.play_btn = tk.Button(
            btn_row, text="▶  Play",
            command=self.toggle_play,
            **{**btn_style, "bg": "#2ecc71", "fg": "white",
               "activebackground": "#27ae60", "width": 8}
        )
        self.play_btn.pack(side=tk.LEFT, padx=3)

        tk.Button(
            btn_row, text="▶",
            command=lambda: self._step_frame(1),
            **{**btn_style, "font": ('Arial', 9)}
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            btn_row, text="⏭ +5s",
            command=lambda: self._skip(5), **btn_style
        ).pack(side=tk.LEFT, padx=3)

        self.loop_btn = tk.Button(
            btn_row, text="🔁 Loop: OFF",
            command=self._toggle_loop,
            **{**btn_style, "bg": "#444"}
        )
        self.loop_btn.pack(side=tk.LEFT, padx=10)

        tk.Button(
            btn_row, text="⛶ Fullscreen",
            command=self._toggle_fullscreen,
            **{**btn_style, "bg": "#555"}
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            btn_row, text="📸 Screenshot",
            command=self._take_screenshot,
            **{**btn_style, "bg": "#2980b9"}
        ).pack(side=tk.LEFT, padx=3)

        slider_row = tk.Frame(ctrl, bg="#2d2d2d")
        slider_row.pack(pady=(8, 0))

        lbl_style = {"bg": "#2d2d2d", "fg": "#aaaaaa", "font": ('Arial', 8)}

        tk.Label(slider_row, text="🔊 Volume:", **lbl_style).pack(side=tk.LEFT, padx=(10, 3))
        self.vol_var = tk.DoubleVar(value=self.volume)
        tk.Scale(
            slider_row, from_=0.0, to=1.0, resolution=0.05,
            orient=tk.HORIZONTAL, variable=self.vol_var,
            command=self._on_volume_change,
            bg="#2d2d2d", fg="white", troughcolor="#555",
            highlightthickness=0, length=120, showvalue=False
        ).pack(side=tk.LEFT)

        tk.Label(slider_row, text="  🎞 Video-Versatz (s):", **lbl_style).pack(side=tk.LEFT, padx=(15, 3))
        self.offset_var = tk.DoubleVar(value=self._init_offset_sec)
        tk.Spinbox(
            slider_row, from_=-300, to=300,
            increment=0.5, textvariable=self.offset_var,
            width=7, format="%.1f",
            command=self._on_offset_change,
            bg="#3d3d3d", fg="white",
            insertbackground="white",
            buttonbackground="#555", relief="flat",
            highlightthickness=0,
        ).pack(side=tk.LEFT)
        self.sync_btn = tk.Button(
            slider_row, text="🔍 Auto-Sync",
            command=self._auto_sync,
            relief="flat", bd=0, highlightthickness=0,
            bg="#8e44ad", fg="white",
            activebackground="#7d3c98",
            font=('Arial', 8), padx=6, pady=4, cursor="hand2"
        )
        self.sync_btn.pack(side=tk.LEFT, padx=(5, 15))

        tk.Label(slider_row, text="  ⏱ A/V Delay (ms):", **lbl_style).pack(side=tk.LEFT, padx=(0, 3))
        self.delay_var = tk.IntVar(value=0)
        tk.Spinbox(
            slider_row, from_=-2000, to=2000,
            increment=50, textvariable=self.delay_var,
            width=6, command=self._on_delay_change,
            bg="#3d3d3d", fg="white",
            insertbackground="white",
            buttonbackground="#555", relief="flat",
            highlightthickness=0,
        ).pack(side=tk.LEFT)

        tk.Label(
            slider_row,
            text="  [ Space=Play/Pause  ←/→=Skip  F=Fullscreen  Esc=Exit ]",
            **{**lbl_style, "fg": "#555555"}
        ).pack(side=tk.LEFT, padx=(20, 0))

    # ─────────────────────────────────────────
    # KEYBOARD SHORTCUTS
    # ─────────────────────────────────────────

    def _bind_keys(self):
        self.win.bind("<space>",  lambda e: self.toggle_play())
        self.win.bind("<Left>",   lambda e: self._skip(-5))
        self.win.bind("<Right>",  lambda e: self._skip(5))
        self.win.bind("<comma>",  lambda e: self._step_frame(-1))
        self.win.bind("<period>", lambda e: self._step_frame(1))
        self.win.bind("f",        lambda e: self._toggle_fullscreen())
        self.win.bind("<F11>",    lambda e: self._toggle_fullscreen())
        self.win.bind("<Escape>", lambda e: self._exit_fullscreen())
        self.win.bind("<Up>",     lambda e: self._adjust_volume(0.1))
        self.win.bind("<Down>",   lambda e: self._adjust_volume(-0.1))

    # ─────────────────────────────────────────
    # VIDEO ÖFFNEN
    # ─────────────────────────────────────────

    def _open_videos(self):
        self.cap_orig = cv2.VideoCapture(self.original_path)
        self.cap_enco = cv2.VideoCapture(self.encoded_path)

        if not self.cap_orig.isOpened():
            self.cap_orig.release()
            self.cap_orig = None
            messagebox.showerror("Fehler", f"Original konnte nicht geöffnet werden:\n{self.original_path}")
            self.close()
            return

        if not self.cap_enco.isOpened():
            self.cap_enco.release()
            self.cap_enco = None
            messagebox.showerror("Fehler", f"Encoded konnte nicht geöffnet werden:\n{self.encoded_path}")
            self.close()
            return

        self.fps  = self.cap_orig.get(cv2.CAP_PROP_FPS) or 25.0
        orig_total = int(self.cap_orig.get(cv2.CAP_PROP_FRAME_COUNT))
        enco_total = int(self.cap_enco.get(cv2.CAP_PROP_FRAME_COUNT))

        # cv2.CAP_PROP_FRAME_COUNT ist auf Linux bei MKV/HEVC oft 0 → ffprobe-Fallback
        if orig_total <= 0:
            self.fps, orig_total = self._get_video_info_ffprobe(self.original_path)
        if enco_total <= 0:
            _, enco_total = self._get_video_info_ffprobe(self.encoded_path)

        # Speichern für _apply_offset (cv2.CAP_PROP_FRAME_COUNT auf Linux unzuverlässig)
        self._orig_total_frames = orig_total
        self._enco_total_frames = enco_total

        # Dimensionen beider Videos prüfen → Crop bei Mismatch
        orig_w = int(self.cap_orig.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(self.cap_orig.get(cv2.CAP_PROP_FRAME_HEIGHT))
        enco_w = int(self.cap_enco.get(cv2.CAP_PROP_FRAME_WIDTH))
        enco_h = int(self.cap_enco.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._orig_crop = None
        self._enco_crop = None

        if orig_w != enco_w or orig_h != enco_h:
            # Kleinere Abmessungen als Ziel
            dst_w = min(orig_w, enco_w)
            dst_h = min(orig_h, enco_h)
            if orig_w > dst_w or orig_h > dst_h:
                x1 = (orig_w - dst_w) // 2
                y1 = (orig_h - dst_h) // 2
                self._orig_crop = (y1, y1 + dst_h, x1, x1 + dst_w)
            if enco_w > dst_w or enco_h > dst_h:
                x1 = (enco_w - dst_w) // 2
                y1 = (enco_h - dst_h) // 2
                self._enco_crop = (y1, y1 + dst_h, x1, x1 + dst_w)
            from modules.ui.console_manager import console
            console.print_info(
                f"Comparison Player: Unterschiedliche Dimensionen erkannt "
                f"(Original {orig_w}×{orig_h}, Encoded {enco_w}×{enco_h}) – "
                f"zentrierter Crop auf {dst_w}×{dst_h} aktiv."
            )

        # Offset-Frames jetzt mit echter FPS berechnen
        self._offset_frames = int(self.offset_var.get() * self.fps)
        # Timeline = kürzeres Video minus Offset-Betrag
        self.total_frames  = max(1, min(orig_total, enco_total) - abs(self._offset_frames))
        self.timeline.config(to=self.total_frames)
        self._decode_and_queue(0)

    def _get_video_info_ffprobe(self, path):
        """Liest FPS und Frame-Anzahl via ffprobe (Fallback wenn cv2 sie nicht liefert)."""
        import subprocess, json
        ffprobe = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        fps = self.fps
        total = 0
        try:
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", path],
                capture_output=True, text=True, timeout=15
            )
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") != "video":
                    continue
                fps_raw = stream.get("r_frame_rate", "")
                if "/" in fps_raw:
                    num, den = fps_raw.split("/")
                    if float(den) > 0:
                        fps = float(num) / float(den)
                nb = stream.get("nb_frames", "")
                if nb and int(nb) > 0:
                    total = int(nb)
                    break
                dur = stream.get("duration") or data.get("format", {}).get("duration", "")
                if dur and fps > 0:
                    total = int(float(dur) * fps)
                break
        except Exception:
            pass
        return fps, total

    # ─────────────────────────────────────────
    # FRAME DECODE + QUEUE
    # ─────────────────────────────────────────

    def _decode_and_queue(self, frame_num):
        off = self._offset_frames
        # Positiv: Original hat Intro → Original fährt voraus
        # Negativ: Encoded hat Intro  → Encoded fährt voraus
        orig_pos = frame_num + max(0,  off)
        enco_pos = frame_num + max(0, -off)
        if self.cap_orig:
            self.cap_orig.set(cv2.CAP_PROP_POS_FRAMES, orig_pos)
        if self.cap_enco:
            self.cap_enco.set(cv2.CAP_PROP_POS_FRAMES, enco_pos)

        ret_o, frame_o = self.cap_orig.read()
        ret_e, frame_e = self.cap_enco.read()

        if ret_o and ret_e:
            if self._orig_crop:
                y1, y2, x1, x2 = self._orig_crop
                frame_o = frame_o[y1:y2, x1:x2]
            if self._enco_crop:
                y1, y2, x1, x2 = self._enco_crop
                frame_e = frame_e[y1:y2, x1:x2]
            with self._queue_lock:
                self._frame_queue = [(frame_o, frame_e)]

    def _prepare_photo(self, frame, canvas):
        """Skaliert Frame auf Canvas-Größe, zentriert."""
        cw = max(canvas.winfo_width(),  640)
        ch = max(canvas.winfo_height(), 360)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img       = Image.fromarray(frame_rgb)
        img.thumbnail((cw, ch), Image.LANCZOS)
        return ImageTk.PhotoImage(image=img)

    # ─────────────────────────────────────────
    # RENDER LOOP (Main Thread)
    # ─────────────────────────────────────────

    def _render_loop(self):
        try:
            with self._queue_lock:
                if self._frame_queue:
                    frame_o, frame_e = self._frame_queue.pop(0)

                    self._photo_orig = self._prepare_photo(frame_o, self.canvas_orig)
                    self._photo_enco = self._prepare_photo(frame_e, self.canvas_enco)

                    # Zentriert rendern
                    for canvas, photo in [
                        (self.canvas_orig, self._photo_orig),
                        (self.canvas_enco, self._photo_enco)
                    ]:
                        cw = canvas.winfo_width()
                        ch = canvas.winfo_height()
                        canvas.delete("all")
                        canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=photo)

                    self.timeline_var.set(self.current_frame)
                    cur = self.current_frame / self.fps
                    tot = self.total_frames  / self.fps
                    self.time_label.config(text=f"{self._fmt(cur)} / {self._fmt(tot)}")
        except Exception:
            pass

        if self.win.winfo_exists():
            self.win.after(8, self._render_loop)

    # ─────────────────────────────────────────
    # PLAYBACK
    # ─────────────────────────────────────────

    def toggle_play(self):
        if self.playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        self.playing = True
        self.play_btn.config(text="⏸  Pause", bg="#e74c3c", activebackground="#c0392b")
        self._stop_video.clear()
        self._stop_audio.clear()

        self._playback_start_time  = time.monotonic()
        self._playback_start_frame = self.current_frame

        threading.Thread(target=self._video_loop, daemon=True).start()
        threading.Thread(
            target=self._audio_loop,
            args=(self.current_frame,),
            daemon=True
        ).start()

    def _pause(self):
        self.playing = False
        self.play_btn.config(text="▶  Play", bg="#2ecc71", activebackground="#27ae60")
        self._stop_video.set()
        self._stop_audio.set()

    # ─────────────────────────────────────────
    # VIDEO LOOP
    # ─────────────────────────────────────────

    def _video_loop(self):
        frame_duration = 1.0 / self.fps
        frame_idx      = 0

        while not self._stop_video.is_set():

            with self._seek_lock:
                if self._seek_pending is not None:
                    off      = self._offset_frames
                    target   = self._seek_pending
                    self.cap_orig.set(cv2.CAP_PROP_POS_FRAMES, target + max(0,  off))
                    self.cap_enco.set(cv2.CAP_PROP_POS_FRAMES, target + max(0, -off))
                    self.current_frame             = target
                    self._playback_start_frame     = target
                    self._playback_start_time      = time.monotonic()
                    self._seek_pending             = None
                    frame_idx                      = 0

            target_time = self._playback_start_time + frame_idx * frame_duration
            now         = time.monotonic()

            if now > target_time + frame_duration:
                frames_behind = int((now - target_time) / frame_duration)
                skip          = min(frames_behind, 3)
                for _ in range(skip):
                    self.cap_orig.read()
                    self.cap_enco.read()
                frame_idx          += skip
                self.current_frame += skip

            ret_o, frame_o = self.cap_orig.read()
            ret_e, frame_e = self.cap_enco.read()

            if not ret_o or not ret_e:
                if self.loop:
                    self.cap_orig.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.cap_enco.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.current_frame             = 0
                    self._playback_start_time      = time.monotonic()
                    self._playback_start_frame     = 0
                    frame_idx                      = 0
                    continue
                else:
                    self.win.after(0, self._pause)
                    break

            self.current_frame = int(self.cap_orig.get(cv2.CAP_PROP_POS_FRAMES))
            frame_idx += 1

            if self._orig_crop:
                y1, y2, x1, x2 = self._orig_crop
                frame_o = frame_o[y1:y2, x1:x2]
            if self._enco_crop:
                y1, y2, x1, x2 = self._enco_crop
                frame_e = frame_e[y1:y2, x1:x2]

            with self._queue_lock:
                self._frame_queue = [(frame_o.copy(), frame_e.copy())]

            next_target = self._playback_start_time + frame_idx * frame_duration
            sleep_time  = next_target - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ─────────────────────────────────────────
    # AUDIO LOOP
    # ─────────────────────────────────────────

    def _audio_loop(self, start_frame=None):
        proc   = None
        stream = None
        try:
            sample_rate = 44100
            channels    = 2

            frame     = start_frame if start_frame is not None else self.current_frame
            start_sec = max(0.0, (frame / self.fps) + (self.delay_var.get() / 1000.0))

            cmd = [
                self.ffmpeg_path,
                "-hide_banner", "-loglevel", "error",
                "-ss", f"{start_sec:.4f}",
                "-i", self.original_path,
                "-vn",
                "-acodec", "pcm_f32le",
                "-ar",  str(sample_rate),
                "-ac",  str(channels),
                "-f",   "f32le",
                "pipe:1"
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW
            )

            chunk_frames    = sample_rate // 20
            bytes_per_chunk = chunk_frames * channels * 4

            stream = sd.OutputStream(
                samplerate = sample_rate,
                channels   = channels,
                dtype      = 'float32',
                latency    = 0.2,   # 'low' crasht auf Linux/PipeWire – fester Wert stabiler
            )
            stream.start()

            while not self._stop_audio.is_set():
                raw = proc.stdout.read(bytes_per_chunk)
                if not raw or self._stop_audio.is_set():
                    break
                audio = np.frombuffer(raw, dtype=np.float32)
                if len(audio) < chunk_frames * channels:
                    break
                audio = audio.reshape(-1, channels)
                audio = (audio * self.vol_var.get()).clip(-1.0, 1.0)
                stream.write(audio)

        except Exception as e:
            print(f"Comparison Audio Error: {e}")
        finally:
            # proc zuerst beenden → entsperrt blockierendes stdout.read()
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            # Stream danach sauber abbrechen
            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass

    def _restart_audio(self, frame):
        """Stoppt Audio sauber und startet neu ab gegebenem Frame."""
        self._stop_audio.set()
        threading.Thread(
            target=self._delayed_audio_restart,
            args=(frame,),
            daemon=True
        ).start()

    def _delayed_audio_restart(self, frame):
        """Wartet auf Audio-Stop, dann Neustart – läuft im Hintergrund."""
        time.sleep(0.08)
        if self.playing:
            self._stop_audio.clear()
            self._audio_loop(start_frame=frame)

    # ─────────────────────────────────────────
    # SEEK – TIMELINE DRAG (DEBOUNCED)
    # ─────────────────────────────────────────

    def _on_seek_drag(self, val):
        """Während des Ziehens: nur Video-Position, kein Audio-Neustart."""
        self._user_is_dragging = True
        frame = int(float(val))
        with self._seek_lock:
            self._seek_pending = frame
            if not self.playing:
                self.current_frame = frame
        if not self.playing:
            self._decode_and_queue(frame)

    def _on_seek_release(self, event):
        """Maus losgelassen: jetzt Audio sauber neu starten."""
        self._user_is_dragging = False
        frame = int(self.timeline_var.get())
        with self._seek_lock:
            self._seek_pending = frame
            self.current_frame = frame
        if self.playing:
            self._restart_audio(frame)

    # ─────────────────────────────────────────
    # SKIP + FRAME STEP
    # ─────────────────────────────────────────

    def _skip(self, seconds):
        target = self.current_frame + int(seconds * self.fps)
        target = max(0, min(target, self.total_frames - 1))
        with self._seek_lock:
            self._seek_pending = target
        if not self.playing:
            self._decode_and_queue(target)
            self.current_frame = target
            self.timeline_var.set(target)
        else:
            self._restart_audio(target)

    def _step_frame(self, direction):
        """Einzelner Frame-Schritt (pausiert automatisch)."""
        if self.playing:
            self._pause()
        target = max(0, min(self.current_frame + direction, self.total_frames - 1))
        self._decode_and_queue(target)
        self.current_frame = target
        self.timeline_var.set(target)

    # ─────────────────────────────────────────
    # FULLSCREEN
    # ─────────────────────────────────────────

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        self.win.attributes("-fullscreen", self._fullscreen)

    def _exit_fullscreen(self):
        if self._fullscreen:
            self._fullscreen = False
            self.win.attributes("-fullscreen", False)

    # ─────────────────────────────────────────
    # VOLUME
    # ─────────────────────────────────────────

    def _adjust_volume(self, delta):
        new_vol = max(0.0, min(1.0, self.vol_var.get() + delta))
        self.vol_var.set(new_vol)

    def _on_volume_change(self, val):
        self.volume = float(val)

    def _on_delay_change(self):
        if self.playing:
            self._restart_audio(self.current_frame)

    def _on_offset_change(self):
        """Spinbox-Callback: Offset übernehmen und Player re-synchronisieren."""
        self._apply_offset(self.offset_var.get())

    def _apply_offset(self, offset_sec):
        """Setzt neuen Video-Versatz, aktualisiert Timeline und seeked zur aktuellen Position."""
        self._offset_frames = int(offset_sec * self.fps)
        # Timeline-Max neu berechnen (kurze Datei minus Offset-Betrag)
        if self.cap_orig and self.cap_enco:
            orig_total = getattr(self, "_orig_total_frames", 0)
            enco_total = getattr(self, "_enco_total_frames", 0)
            self.total_frames = max(1, min(orig_total, enco_total) - abs(self._offset_frames))
            self.timeline.config(to=self.total_frames)
            # Aktuelle Position ins gültige Fenster clampen
            clamped = min(self.current_frame, self.total_frames - 1)
            with self._seek_lock:
                self._seek_pending = clamped
            if not self.playing:
                self._decode_and_queue(clamped)
                self.current_frame = clamped
                self.timeline_var.set(clamped)
        # Callback an Main-App → Offset für Analyse übernehmen
        if self.offset_callback:
            self.offset_callback(offset_sec)

    # ─────────────────────────────────────────
    # AUTO-SYNC via Audio-Kreuzkorrelation
    # ─────────────────────────────────────────

    def _auto_sync(self):
        """Startet Audio-Kreuzkorrelation im Hintergrund."""
        self.sync_btn.config(text="⏳ Analysiere...", state="disabled")
        threading.Thread(target=self._auto_sync_thread, daemon=True).start()

    def _auto_sync_thread(self):
        """FFT-basierte Kreuzkorrelation der Audio-Spuren beider Videos."""
        try:
            sample_rate = 8000   # Niedrige Rate reicht für Sync-Erkennung
            duration    = 120    # Erste 2 Minuten analysieren

            audio_orig = self._extract_audio_for_sync(self.original_path, duration, sample_rate)
            audio_enco = self._extract_audio_for_sync(self.encoded_path,  duration, sample_rate)

            if len(audio_orig) < 1000 or len(audio_enco) < 1000:
                try:
                    self.win.after(0, lambda: messagebox.showwarning(
                        "Auto-Sync", "Kein Audio gefunden oder zu kurz für Sync-Erkennung."
                    ))
                except tk.TclError:
                    pass
                return

            # FFT-basierte Kreuzkorrelation – O(n log n), schnell für große Arrays
            n     = len(audio_orig) + len(audio_enco) - 1
            n_fft = 1 << int(np.ceil(np.log2(n)))  # Nächste Zweierpotenz

            F_orig = np.fft.rfft(audio_orig, n=n_fft)
            F_enco = np.fft.rfft(audio_enco, n=n_fft)
            corr   = np.fft.irfft(F_orig * np.conj(F_enco), n=n_fft)

            # Lag bestimmen: positiver Lag → Original führt
            lag_samples = int(np.argmax(corr[:n]))
            if lag_samples > n // 2:
                lag_samples -= n_fft

            offset_sec     = lag_samples / sample_rate
            offset_rounded = round(offset_sec * 2) / 2  # Auf 0.5 s runden

            def _apply():
                self.offset_var.set(offset_rounded)
                self._apply_offset(offset_rounded)
                messagebox.showinfo(
                    "Auto-Sync erkannt",
                    f"Ermittelter Video-Versatz: {offset_rounded:+.1f} s\n\n"
                    f"(Positiv = Original hat {offset_rounded:.1f}s Extra-Inhalt am Anfang)\n"
                    f"Der Versatz wurde automatisch übernommen."
                )

            try:
                self.win.after(0, _apply)
            except tk.TclError:
                pass

        except Exception as e:
            try:
                self.win.after(0, lambda: messagebox.showerror("Auto-Sync Fehler", str(e)))
            except tk.TclError:
                pass
        finally:
            try:
                self.win.after(0, lambda: self.sync_btn.config(text="🔍 Auto-Sync", state="normal"))
            except tk.TclError:
                pass

    def _extract_audio_for_sync(self, video_path, duration, sample_rate):
        """Extrahiert Mono-Audio als float32-Array für Kreuzkorrelation."""
        cmd = [
            self.ffmpeg_path, "-hide_banner", "-loglevel", "error",
            "-i", video_path,
            "-t", str(duration),
            "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-acodec", "pcm_f32le", "-f", "f32le", "pipe:1"
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW
            )
            raw = proc.stdout.read()
            proc.wait()
            return np.frombuffer(raw, dtype=np.float32)
        except Exception:
            return np.array([], dtype=np.float32)

    # ─────────────────────────────────────────
    # LOOP / SCREENSHOT
    # ─────────────────────────────────────────

    def _toggle_loop(self):
        self.loop = not self.loop
        self.loop_btn.config(
            text=f"🔁 Loop: {'ON' if self.loop else 'OFF'}",
            bg="#27ae60" if self.loop else "#444"
        )

    def _take_screenshot(self):
        ts = time.strftime("%Y%m%d_%H%M%S")
        os.makedirs(self.screenshot_dir, exist_ok=True)
        saved = []

        for cap, label, crop in [
            (self.cap_orig, "original", self._orig_crop),
            (self.cap_enco, "encoded",  self._enco_crop),
        ]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            ret, frame = cap.read()
            if ret:
                if crop:
                    y1, y2, x1, x2 = crop
                    frame = frame[y1:y2, x1:x2]
                path = os.path.join(self.screenshot_dir, f"comparison_{label}_{ts}.jpg")
                cv2.imwrite(path, frame)
                saved.append(os.path.basename(path))

        if saved:
            original_title = self.win.title()
            self.win.title(f"✅ Gespeichert: {', '.join(saved)}")
            self.win.after(2500, lambda: self.win.title(original_title))

    # ─────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────

    def _fmt(self, seconds):
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    # ─────────────────────────────────────────
    # CLEANUP
    # ─────────────────────────────────────────

    def close(self):
        self._stop_video.set()
        self._stop_audio.set()
        self.playing = False

        if self.cap_orig:
            self.cap_orig.release()
            self.cap_orig = None
        if self.cap_enco:
            self.cap_enco.release()
            self.cap_enco = None

        try:
            self.win.destroy()
        except tk.TclError:
            pass