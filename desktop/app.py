import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.settings_repository import SettingsRepository
from desktop.theme.theme_manager import ThemeManager
from desktop.ui.main_window import MainWindow


def _ensure_valid_application_font(app: QApplication) -> None:
    """Normalize the application font before Qt style polishing.

    Some Qt platform themes can expose a default font whose pointSize() is -1
    because it is defined by pixel size.  Later stylesheet polishing may pass
    that unresolved value back through QFont.setPointSize(), which prints:

        QFont::setPointSize: Point size <= 0 (-1), must be greater than 0

    Keep the visible font close to Qt's default, but make sure the application
    font always has a positive point size.
    """
    font = QFont(app.font())

    if font.pointSize() > 0:
        return

    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF())
    elif font.pixelSize() > 0:
        # 12 px is close to the usual 9 pt desktop UI default at 96 DPI.
        fallback_point_size = max(1, round(font.pixelSize() * 72 / 96))
        font.setPointSize(fallback_point_size)
    else:
        font.setPointSize(9)

    app.setFont(font)


def main() -> int:
    app = QApplication(sys.argv)
    _ensure_valid_application_font(app)

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