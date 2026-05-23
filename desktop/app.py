import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.settings_repository import SettingsRepository
from desktop.theme.theme_manager import ThemeManager
from desktop.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    project_root = Path(__file__).resolve().parents[1]

    settings_path = project_root / "resources" / "data" / "settings.json"
    locale_path = project_root / "resources" / "locales" / "ui.csv"
    themes_dir = project_root / "resources" / "themes"

    settings_repository = SettingsRepository(settings_path=settings_path)
    settings = settings_repository.load()

    localization = LocalizationManager(
        csv_path=locale_path,
        default_language=settings.language,
        fallback_language=settings.fallback_language,
    )

    theme_manager = ThemeManager(themes_dir=themes_dir)

    try:
        initial_theme = theme_manager.get_theme(settings.theme_id)
    except ValueError:
        initial_theme = theme_manager.get_theme("light")

    window = MainWindow(
        localization=localization,
        theme=initial_theme,
        theme_manager=theme_manager,
        settings=settings,
        settings_repository=settings_repository,
    )
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())