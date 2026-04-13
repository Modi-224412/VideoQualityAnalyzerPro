import static_ffmpeg, subprocess, shutil
static_ffmpeg.add_paths()
ff = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True).stdout.strip()
fp = subprocess.run(['which', 'ffprobe'], capture_output=True, text=True).stdout.strip()
shutil.copy(ff, 'ffmpeg')
shutil.copy(fp, 'ffprobe')
print('Fertig:', ff)
