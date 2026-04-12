import json
import os

class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path

    def load(self):
        """Lädt die Konfiguration aus der JSON-Datei."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self, data):
        """Speichert die Konfiguration atomar via Temp-Datei + Rename.
        Verhindert korrupte/leere Config bei Absturz während des Schreibens."""
        tmp_path = self.config_path + ".tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.config_path)  # Atomar auf allen Plattformen
        except Exception as e:
            print(f"Config speichern fehlgeschlagen: {e}")
            try:
                os.remove(tmp_path)
            except Exception:
                pass