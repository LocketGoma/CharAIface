import json
from pathlib import Path

from desktop.theme.theme_model import ThemeDefinition


class ThemeManager:
    def __init__(self, themes_dir: str | Path) -> None:
        self.themes_dir = Path(themes_dir)
        self._themes: dict[str, ThemeDefinition] = {}

        self.load_builtin_themes()

    def load_builtin_themes(self) -> None:
        self._themes.clear()

        for theme_id in ("light", "dark"):
            path = self.themes_dir / f"{theme_id}.json"

            if not path.exists():
                raise FileNotFoundError(f"Theme file not found: {path}")

            data = json.loads(path.read_text(encoding="utf-8"))
            theme = ThemeDefinition(**data)

            self._themes[theme.id] = theme

    def get_theme(self, theme_id: str) -> ThemeDefinition:
        theme = self._themes.get(theme_id)

        if theme is None:
            raise ValueError(f"Unknown theme: {theme_id}")

        return theme

    def available_theme_ids(self) -> list[str]:
        return list(self._themes.keys())