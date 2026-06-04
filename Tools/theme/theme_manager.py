from __future__ import annotations

import json
from pathlib import Path

from theme.theme_model import ThemeDefinition, ThemePalette


class ThemeManager:
    def __init__(self, themes_dir: str | Path) -> None:
        self.themes_dir = Path(themes_dir)
        self._themes: dict[str, ThemeDefinition] = {}
        self.load()

    @property
    def themes(self) -> list[ThemeDefinition]:
        return list(self._themes.values())

    def load(self) -> None:
        themes: dict[str, ThemeDefinition] = {}
        for path in sorted(self.themes_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            palette = ThemePalette(**data["palette"])
            themes[data["id"]] = ThemeDefinition(
                id=data["id"],
                name=data["name"],
                palette=palette,
            )
        self._themes = themes

    def get_theme(self, theme_id: str) -> ThemeDefinition:
        return self._themes.get(theme_id) or self._themes["light"]
