import json
from pathlib import Path

from pydantic import ValidationError

from desktop.settings.app_settings import AppSettings


class SettingsRepository:
    def __init__(self, settings_path: str | Path) -> None:
        self.settings_path = Path(settings_path)

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return AppSettings(**data)

        except (json.JSONDecodeError, ValidationError) as error:
            print(f"[Settings] Failed to load settings: {error}")
            print("[Settings] Falling back to default settings.")

            settings = AppSettings()
            self.save(settings)
            return settings

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

        text = settings.model_dump_json(indent=2)
        self.settings_path.write_text(text, encoding="utf-8")