import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from desktop.localization.localization_manager import LocalizationManager
from desktop.theme.theme_manager import ThemeManager
from desktop.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    project_root = Path(__file__).resolve().parents[1]
    locale_path = project_root / "resources" / "locales" / "ui.csv"
    themes_dir = project_root / "resources" / "themes"

    localization = LocalizationManager(
        csv_path=locale_path,
        default_language="ko",
        fallback_language="en",
    )

    theme_manager = ThemeManager(themes_dir=themes_dir)
    theme = theme_manager.get_theme("light")

    window = MainWindow(
        localization=localization,
        theme=theme,
    )
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())