import subprocess
import platform
import tkinter as tk
from modules.ui.console_manager import console

CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0

# Anzeige-Label für CPU-Option (kein GPU)
CPU_LABEL = "🖥️  Kein GPU  (CPU)"


class GpuManager:
    """
    Erkennt alle verfügbaren GPUs (NVIDIA / AMD / Intel, dediziert + iGPU)
    und stellt sie als auswählbare Liste bereit.

    Beschleuniger-Mapping:
        NVIDIA  →  cuda
        AMD     →  d3d11va  (Direct3D 11 Video Acceleration)
        Intel   →  qsv      (Quick Sync Video)
    """

    def __init__(self, ffmpeg_path):
        self.ffmpeg_path   = ffmpeg_path
        self._hwaccels     = set()
        # Liste aller erkannten GPU-Optionen: {"label": str, "accel": str|None}
        self.all_gpus      = []
        # Mapping Anzeige-Label → hwaccel-Wert (None = CPU / kein GPU)
        self.gpu_options   = {CPU_LABEL: None}
        # Vorausgewähltes Label (beste GPU oder CPU)
        self.best_label    = CPU_LABEL

    # ─────────────────────────────────────────
    # INTERNE HELFER
    # ─────────────────────────────────────────

    def _load_hwaccels(self):
        try:
            out = subprocess.run(
                [self.ffmpeg_path, "-hwaccels"],
                capture_output=True, text=True,
                errors="replace", encoding="utf-8",
                creationflags=CREATE_NO_WINDOW
            ).stdout.lower()
            self._hwaccels = set(out.split())
        except Exception:
            self._hwaccels = set()

    def _wmic_names(self):
        """Gibt alle GPU-Namen als (name, adapter_index) zurück.
        Der adapter_index entspricht dem D3D-Adapter-Index für -hwaccel_device.
        """
        if platform.system() != "Windows":
            return []

        # Methode 1: PowerShell Get-CimInstance (Windows 10/11, wmic-Ersatz)
        try:
            res = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
                ],
                capture_output=True, text=True,
                errors="replace", encoding="utf-8",
                creationflags=CREATE_NO_WINDOW,
                timeout=10
            )
            names = [l.strip() for l in res.stdout.splitlines() if l.strip()]
            if names:
                return [(name, idx) for idx, name in enumerate(names)]
        except Exception:
            pass

        # Methode 2: wmic (ältere Windows-Versionen)
        try:
            res = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True,
                errors="replace", encoding="utf-8",
                creationflags=CREATE_NO_WINDOW,
                timeout=10
            )
            names = [
                l.strip() for l in res.stdout.splitlines()
                if l.strip() and l.strip().lower() != "name"
            ]
            return [(name, idx) for idx, name in enumerate(names)]
        except Exception:
            return []

    def _best_accel(self, vendor):
        """Gibt den besten verfügbaren hwaccel für einen Hersteller zurück."""
        mapping = {
            "nvidia": ["cuda"],
            "amd":    ["d3d11va", "dxva2", "opencl"],
            "intel":  ["qsv", "d3d11va", "dxva2", "opencl"],
        }
        for accel in mapping.get(vendor, []):
            if accel in self._hwaccels:
                return accel
        # Windows-Fallback: d3d11va ist systemseitig immer verfügbar,
        # auch wenn FFmpeg es nicht explizit in -hwaccels listet
        if platform.system() == "Windows" and vendor in ("amd", "intel"):
            return "d3d11va"
        return None

    def _accel_label(self, accel):
        return {"cuda": "CUDA", "d3d11va": "D3D11", "dxva2": "DXVA2", "qsv": "QSV"}.get(accel, accel.upper())

    # ─────────────────────────────────────────
    # HAUPT-ERKENNUNG
    # ─────────────────────────────────────────

    def detect_all(self):
        """
        Erkennt alle GPUs und gibt eine priorisierte Liste zurück.
        Reihenfolge: NVIDIA → AMD dediziert → Intel dediziert → AMD iGPU → Intel iGPU
        """
        self._load_hwaccels()
        found = []
        nvidia_names = set()

        # ── NVIDIA via nvidia-smi ──────────────────────────────────────────
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, check=True,
                creationflags=CREATE_NO_WINDOW
            )
            for raw in res.stdout.strip().splitlines():
                name = raw.strip()
                if not name:
                    continue
                nvidia_names.add(name.lower())
                accel = self._best_accel("nvidia")
                if accel:
                    found.append({
                        "name":       name,
                        "vendor":     "nvidia",
                        "accel":      accel,
                        "label":      f"⚡  NVIDIA {name}  ({self._accel_label(accel)})",
                        "igpu":       False,
                        "device_idx": None,  # CUDA braucht keinen D3D-Adapter-Index
                    })
        except Exception:
            pass

        # ── AMD + Intel via wmic ───────────────────────────────────────────
        wmic_entries = self._wmic_names()  # [(name, adapter_idx), ...]

        for name, adapter_idx in wmic_entries:
            nl = name.lower()

            # NVIDIA-Duplikate überspringen
            if any(n in nl for n in nvidia_names):
                continue
            if "nvidia" in nl or "geforce" in nl or "quadro" in nl:
                continue

            if "amd" in nl or "radeon" in nl or "ati" in nl:
                accel = self._best_accel("amd")
                if accel:
                    # iGPU: Vega/Graphics/Integrated = klassisch, keine "RX ... XT/XT/Pro"-Angabe = modern (780M etc.)
                    is_dedicated = any(k in nl for k in (" rx ", "xt", " pro ", " w6", " w7"))
                    is_igpu = not is_dedicated
                    igpu_tag = "  [iGPU]" if is_igpu else ""
                    found.append({
                        "name":       name,
                        "vendor":     "amd",
                        "accel":      accel,
                        "label":      f"⚡  AMD {name}  ({self._accel_label(accel)}){igpu_tag}",
                        "igpu":       is_igpu,
                        "device_idx": adapter_idx,
                    })

            elif "intel" in nl:
                # Nur GPU-relevante Intel-Einträge – keine Netzwerkkarten etc.
                if not any(k in nl for k in ("graphics", "iris", "arc", "uhd", "hd", "xe")):
                    continue
                accel = self._best_accel("intel")
                if accel:
                    is_igpu = "arc" not in nl
                    igpu_tag = "  [iGPU]" if is_igpu else ""
                    found.append({
                        "name":       name,
                        "vendor":     "intel",
                        "accel":      accel,
                        "label":      f"⚡  Intel {name}  ({self._accel_label(accel)}){igpu_tag}",
                        "igpu":       is_igpu,
                        "device_idx": adapter_idx,
                    })
                else:
                    console.print_warning(f"Intel GPU '{name}' erkannt, aber kein kompatibler hwaccel gefunden.")

        # ── Sortierung: NVIDIA → AMD dGPU → Intel dGPU → AMD iGPU → Intel iGPU ──
        # Dedizierte GPUs zuerst, dann iGPUs; innerhalb: NVIDIA → AMD → Intel
        vendor_prio = {"nvidia": 0, "amd": 1, "intel": 2}
        found.sort(key=lambda g: (int(g["igpu"]), vendor_prio.get(g["vendor"], 9)))

        self.all_gpus = found
        return found

    # ─────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────

    def initialize(self):
        """
        Erkennt alle GPUs, füllt gpu_options und setzt best_label.
        Gibt True zurück wenn mindestens eine GPU nutzbar ist.
        """
        gpus = self.detect_all()

        # Options-Dict aufbauen (CPU immer als erste Option)
        # Wert: (accel, device_idx) – device_idx ist None für NVIDIA/CUDA
        self.gpu_options = {CPU_LABEL: (None, None)}
        for g in gpus:
            self.gpu_options[g["label"]] = (g["accel"], g.get("device_idx"))

        if gpus:
            self.best_label = gpus[0]["label"]   # Beste GPU vorauswählen
            console.print_success(f"GPU(s) gefunden: {', '.join(g['name'] for g in gpus)}")
            console.print_info(
                f"Vorausgewählt: {gpus[0]['name']} "
                f"({self._accel_label(gpus[0]['accel'])})"
            )
        else:
            self.best_label = CPU_LABEL
            console.print_warning("Keine kompatible GPU erkannt – Hardware-Beschleunigung nicht verfügbar.")

        return bool(gpus)

    def apply_to_ui(self, gpu_var, gpu_menu):
        """
        Befüllt das GPU-OptionMenu mit allen erkannten Optionen
        und wählt die beste GPU vor.
        """
        menu = gpu_menu["menu"]
        menu.delete(0, "end")

        for label in self.gpu_options:
            menu.add_command(
                label=label,
                command=lambda v=label: gpu_var.set(v)
            )

        gpu_var.set(self.best_label)

        # Deaktivieren wenn keine GPU verfügbar
        if not self.all_gpus:
            gpu_menu.config(state=tk.DISABLED)
        else:
            gpu_menu.config(state=tk.NORMAL)
