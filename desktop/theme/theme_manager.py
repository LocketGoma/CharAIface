import json
from pathlib import Path

from desktop.theme.theme_model import ThemeDefinition, ThemePalette


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

    def create_character_theme(
        self,
        base_theme_id: str,
        palette_override: dict[str, str] | None,
        character_name: str = "Character",
    ) -> ThemeDefinition:
        base_theme = self.get_theme(base_theme_id)
        palette_data = base_theme.palette.model_dump()

        if palette_override:
            valid_keys = set(ThemePalette.model_fields.keys())

            for key, value in palette_override.items():
                if key in valid_keys:
                    palette_data[key] = value
                else:
                    print(
                        "[Theme] Unknown palette key ignored: "
                        f"{key} for character theme"
                    )

        return ThemeDefinition(
            id="character",
            name=f"{character_name} Theme",
            palette=ThemePalette(**palette_data),
        )

    def available_theme_ids(self) -> list[str]:
        return list(self._themes.keys())