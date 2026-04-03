import datetime

class ConsoleManager:
    def __init__(self):
        self.ui_callback          = None
        self.ui_progress_callback = None   # Ersetzt letzte Zeile statt neu anzuhängen

    def register_ui_callback(self, callback):
        """Verknüpft die Konsole mit dem ScrolledText-Widget der GUI."""
        self.ui_callback = callback

    def register_progress_callback(self, callback):
        """
        Registriert einen zweiten Callback für Fortschritts-Updates.
        Dieser ersetzt die letzte Progress-Zeile statt eine neue anzuhängen.
        """
        self.ui_progress_callback = callback

    def _log(self, level, message):
        timestamp     = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [{level:7}] {message}"
        print(formatted_msg)
        if self.ui_callback:
            self.ui_callback(formatted_msg)

    def print_info(self, message):
        self._log("INFO", message)

    def print_step(self, message):
        self._log("STEP", f"--- {message.upper()} ---")

    def print_success(self, message):
        self._log("SUCCESS", f"✅ {message}")

    def print_warning(self, message):
        self._log("WARN", f"⚠️ {message}")

    def print_error(self, message):
        self._log("ERROR", f"❌ {message}")

    def print_progress(self, message):
        """
        Fortschritts-Update: überschreibt in der GUI die letzte Progress-Zeile.
        Im Terminal wird die Zeile per \\r überschrieben.
        """
        timestamp     = datetime.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] [INFO   ] {message}"
        # Terminal: Zeile in-place überschreiben
        import sys
        sys.stdout.write(f"\r{formatted_msg}")
        sys.stdout.flush()
        # GUI: letzte Progress-Zeile ersetzen
        if self.ui_progress_callback:
            self.ui_progress_callback(formatted_msg)
        elif self.ui_callback:
            self.ui_callback(formatted_msg)

# Singleton-Instanz für das gesamte Projekt
console = ConsoleManager()