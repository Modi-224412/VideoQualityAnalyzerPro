import subprocess
import logging
import platform

# Cache für die Filter-Prüfung, damit wir nicht bei jedem Frame fragen
_ZSCALE_AVAILABLE = None

def check_zscale_support(ffmpeg_path):
    """Prüft, ob FFmpeg mit zscale Support kompiliert wurde."""
    global _ZSCALE_AVAILABLE
    if _ZSCALE_AVAILABLE is not None:
        return _ZSCALE_AVAILABLE
    
    try:
        CREATE_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0
        res = subprocess.run([ffmpeg_path, "-filters"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        _ZSCALE_AVAILABLE = "zscale" in res.stdout
        return _ZSCALE_AVAILABLE
    except (OSError, subprocess.SubprocessError):
        _ZSCALE_AVAILABLE = False
        return False

def get_analysis_filters(hdr_info, ffmpeg_path="ffmpeg", target_width=1920, target_height=None):
    """
    Generiert Filter für HDR/DV zu SDR Normalisierung.
    Reihenfolge: zscale (Farbraum) → tonemap (Helligkeit) → scale → format
    target_height: wenn gesetzt, wird auf exakt W×H skaliert (für libvmaf Height-Match).
                   Sonst: Höhe proportional berechnet (-2 = gerades Pixel).
    """
    filters = []
    is_hdr = hdr_info.get('is_hdr') == "Ja"
    is_dv = "Dolby Vision" in hdr_info.get('hdr_format', '')

    if is_dv or is_hdr:
        if check_zscale_support(ffmpeg_path):
            # High-End Normalisierung zu BT.709
            # Reihenfolge: erst Farbraum konvertieren, dann tonemappen
            filters.append("zscale=t=709:m=709:r=tv:p=709")
            filters.append("tonemap=hable")
        else:
            # Fallback KORRIGIERT: zscale ZUERST, dann tonemap
            logging.warning("zscale nicht gefunden, nutze Standard-Tonemapping.")
            filters.append("zscale=t=709:m=709")
            filters.append("tonemap=hable:desat=2")

    # Skalierung und Format-Fix (Immer nötig für VMAF)
    # Mit target_height: exakte Dimensionen → libvmaf "input height must match" vermieden.
    # Ohne target_height: Höhe proportional (-2 garantiert gerades Pixel für yuv420p).
    if target_height:
        filters.append(f"scale={target_width}:{target_height}:flags=bicubic")
    else:
        filters.append(f"scale={target_width}:-2:flags=bicubic")
    filters.append("format=yuv420p")
    
    return ",".join(filters)