@echo off
setlocal
set "ZIP_NAME=VideoAnalyzerPro Alpha v0.17 stable.zip"

echo [1/4] Bereinige Projekt von privaten Daten...
:: Löscht alle Python-Cache Ordner (__pycache__)
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

:: Löscht temporäre Arbeitsordner, Config und Build-Reste
if exist "temp" rd /s /q "temp"
if exist "reports" rd /s /q "reports"
if exist "dist" rd /s /q "dist"
if exist "build" rd /s /q "build"
if exist "config.json" del /f /q "config.json"
if exist "*.spec" del /f /q "*.spec"

echo [2/4] Erstelle sauberes ZIP-Archiv (inkl. ffprobe)...
:: Nutzt tar, um die Dateien zu bündeln
:: WICHTIG: ffprobe.exe wurde hier zur Liste hinzugefügt
tar -a -c -f "%ZIP_NAME%" main_gui.py modules ffmpeg.exe ffplay.exe ffprobe.exe icon.ico

echo [3/4] Verifiziere Archiv...
if exist "%ZIP_NAME%" (
    echo.
    echo ERFOLG: %ZIP_NAME% wurde inklusive aller FFmpeg-Tools erstellt.
) else (
    echo.
    echo FEHLER: ZIP konnte nicht erstellt werden.
)

echo [4/4] Abschluss...
pause