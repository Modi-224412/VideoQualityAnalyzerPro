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


class PlayerWindow:
    """
    Eingebetteter Video-Player als Tkinter Popup-Fenster.
    - Seek-Audio-Fix: Debounce + einmaliger sauberer Neustart nach Drag-Ende
    - Frame-by-Frame Navigation (◀ ▶)
    - Fullscreen (F / Doppelklick)
    - Keyboard Shortcuts (Space, Links, Rechts, F, Esc)
    - Zentriertes Canvas-Rendering
    - Kein Zoom (entfernt)
    """

    def __init__(self, parent, video_path, ffmpeg_path,
                 title="Player", screenshot_dir=None):
        self.parent         = parent
        self.video_path     = video_path
        self.ffmpeg_path    = ffmpeg_path
        self.screenshot_dir = screenshot_dir or os.path.dirname(video_path)

        self.playing       = False
        self.loop          = False
        self.volume        = 0.8
        self.current_frame = 0
        self.total_frames  = 0
        self.fps           = 25.0
        self.cap           = None
        self._fullscreen   = False

        self._stop_video   = threading.Event()
        self._stop_audio   = threading.Event()
        self._seek_pending = None
        self._seek_lock    = threading.Lock()

        self._frame_queue  = []
        self._queue_lock   = threading.Lock()
        self._photo        = None

        self._playback_start_time  = 0.0
        self._playback_start_frame = 0

        # Debounce: Audio erst nach Ende des Timeline-Drags neu starten
        self._seek_debounce_id  = None
        self._user_is_dragging  = False

        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.configure(bg="#1e1e1e")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.resizable(True, True)

        self._build_ui()
        self._bind_keys()
        self._open_video()
        self._render_loop()

    # ─────────────────────────────────────────
    # UI AUFBAU
    # ─────────────────────────────────────────

    def _build_ui(self):
        self.canvas = tk.Canvas(
            self.win, bg="#000000",
            width=960, height=540,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.canvas.bind("<Double-Button-1>", lambda e: self._toggle_fullscreen())

        self.timeline_var = tk.DoubleVar(value=0)
        self.timeline = ttk.Scale(
            self.win, from_=0, to=100,
            orient=tk.HORIZONTAL,
            variable=self.timeline_var,
            command=self._on_seek_drag
        )
        self.timeline.pack(fill=tk.X, padx=10, pady=(0, 2))

        # Maus-Release auf der Timeline = Drag beendet → Audio neu starten
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

        tk.Label(slider_row, text="  ⏱ A/V Delay (ms):", **lbl_style).pack(side=tk.LEFT, padx=(15, 3))
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

        # Keyboard-Hint
        tk.Label(
            slider_row,
            text="  [ Space=Play/Pause  ←/→=Skip  F=Fullscreen  Esc=Exit ]",
            **{**lbl_style, "fg": "#555555"}
        ).pack(side=tk.LEFT, padx=(20, 0))

    # ─────────────────────────────────────────
    # KEYBOARD SHORTCUTS
    # ─────────────────────────────────────────

    def _bind_keys(self):
        self.win.bind("<space>",     lambda e: self.toggle_play())
        self.win.bind("<Left>",      lambda e: self._skip(-5))
        self.win.bind("<Right>",     lambda e: self._skip(5))
        self.win.bind("<comma>",     lambda e: self._step_frame(-1))
        self.win.bind("<period>",    lambda e: self._step_frame(1))
        self.win.bind("f",           lambda e: self._toggle_fullscreen())
        self.win.bind("<F11>",       lambda e: self._toggle_fullscreen())
        self.win.bind("<Escape>",    lambda e: self._exit_fullscreen())
        self.win.bind("<Up>",        lambda e: self._adjust_volume(0.1))
        self.win.bind("<Down>",      lambda e: self._adjust_volume(-0.1))

    # ─────────────────────────────────────────
    # VIDEO ÖFFNEN
    # ─────────────────────────────────────────

    def _open_video(self):
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            messagebox.showerror(
                "Player Fehler",
                f"Video konnte nicht geöffnet werden:\n{self.video_path}"
            )
            self.close()
            return

        self.fps          = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # cv2.CAP_PROP_FRAME_COUNT ist auf Linux bei MKV/HEVC oft 0 → ffprobe-Fallback
        if self.total_frames <= 0:
            self.fps, self.total_frames = self._get_video_info_ffprobe(self.video_path)

        self.timeline.config(to=max(1, self.total_frames))
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
        if self.cap is None:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self.cap.read()
        if ret:
            with self._queue_lock:
                self._frame_queue = [frame]

    def _prepare_photo(self, frame):
        """Skaliert Frame auf Canvas-Größe, zentriert."""
        cw = max(self.canvas.winfo_width(),  960)
        ch = max(self.canvas.winfo_height(), 540)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img       = Image.fromarray(frame_rgb)

        # Fit into canvas maintaining aspect ratio
        img.thumbnail((cw, ch), Image.LANCZOS)
        return ImageTk.PhotoImage(image=img)

    # ─────────────────────────────────────────
    # RENDER LOOP (Main Thread)
    # ─────────────────────────────────────────

    def _render_loop(self):
        try:
            with self._queue_lock:
                if self._frame_queue:
                    frame = self._frame_queue.pop(0)
                    self._photo = self._prepare_photo(frame)

                    # Zentriert rendern
                    cw = self.canvas.winfo_width()
                    ch = self.canvas.winfo_height()
                    self.canvas.delete("all")
                    self.canvas.create_image(
                        cw // 2, ch // 2,
                        anchor=tk.CENTER,
                        image=self._photo
                    )

                    self.timeline_var.set(self.current_frame)
                    cur = self.current_frame / self.fps
                    tot = self.total_frames  / self.fps
                    self.time_label.config(
                        text=f"{self._fmt(cur)} / {self._fmt(tot)}"
                    )
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
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, self._seek_pending)
                    self.current_frame             = self._seek_pending
                    self._playback_start_frame     = self._seek_pending
                    self._playback_start_time      = time.monotonic()
                    self._seek_pending             = None
                    frame_idx                      = 0

            target_time = self._playback_start_time + frame_idx * frame_duration
            now         = time.monotonic()

            if now > target_time + frame_duration:
                frames_behind = int((now - target_time) / frame_duration)
                skip          = min(frames_behind, 3)
                for _ in range(skip):
                    self.cap.read()
                frame_idx          += skip
                self.current_frame += skip

            ret, frame = self.cap.read()

            if not ret:
                if self.loop:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.current_frame         = 0
                    self._playback_start_time  = time.monotonic()
                    self._playback_start_frame = 0
                    frame_idx                  = 0
                    continue
                else:
                    self.win.after(0, self._pause)
                    break

            self.current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            frame_idx += 1

            with self._queue_lock:
                self._frame_queue = [frame.copy()]

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
                "-i", self.video_path,
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
            print(f"Audio Error: {e}")
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
        # Kurz warten bis der laufende Audio-Thread beendet ist
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
        """Wird während des Ziehens aufgerufen – nur Video-Position setzen, kein Audio."""
        self._user_is_dragging = True
        frame = int(float(val))
        with self._seek_lock:
            self._seek_pending = frame
            if not self.playing:
                self.current_frame = frame
        if not self.playing:
            self._decode_and_queue(frame)

    def _on_seek_release(self, event):
        """Wird beim Loslassen der Maus aufgerufen – jetzt erst Audio neu starten."""
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
        """Einzelner Frame-Schritt vor oder zurück (nur im Pause-Modus sinnvoll)."""
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
        if self.cap is None:
            return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ret, frame = self.cap.read()
        if not ret:
            return
        ts       = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(self.screenshot_dir, f"screenshot_{ts}.jpg")
        os.makedirs(self.screenshot_dir, exist_ok=True)
        cv2.imwrite(out_path, frame)
        # Kein störendes MessageBox – stattdessen kurze Titelbar-Benachrichtigung
        original_title = self.win.title()
        self.win.title(f"✅ Gespeichert: {os.path.basename(out_path)}")
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

        if self.cap:
            self.cap.release()
            self.cap = None

        try:
            self.win.destroy()
        except tk.TclError:
            pass