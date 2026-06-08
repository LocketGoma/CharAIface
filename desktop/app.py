import sys
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from shared.runtime_paths import resource_path, runtime_root
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.settings_repository import SettingsRepository
from desktop.theme.theme_manager import ThemeManager
from desktop.ui.main_window import MainWindow
from desktop.utils.app_icon import load_app_icon
from desktop.utils.single_instance import (
    FrontendSingleInstanceServer,
    request_existing_frontend_activation,
)


class CharAIfaceApplication(QApplication):
    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self._main_window: MainWindow | None = None

    def set_main_window(self, window: MainWindow) -> None:
        self._main_window = window

    def event(self, event) -> bool:
        if (
            sys.platform == "darwin"
            and event.type() == QEvent.Type.Quit
            and self._main_window is not None
        ):
            self._main_window.prepare_application_quit()
        return super().event(event)


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



def _restore_window_when_app_activated(window: MainWindow, state: Qt.ApplicationState) -> None:
    """Restore the session window when the user re-activates the app on macOS.

    macOS users expect Dock activation to bring back the app window.  Windows
    keeps the tray-hide behavior, so this hook is intentionally macOS-only.
    """
    if sys.platform != "darwin":
        return

    if state == Qt.ApplicationState.ApplicationActive and (
        not window.isVisible() or window.isMinimized()
    ):
        window.show_session_window()

def main() -> int:
    # If another frontend is already alive, ask it to open the session window
    # and exit before creating a second PySide frontend process.
    if request_existing_frontend_activation():
        return 0

    app = CharAIfaceApplication(sys.argv)
    app.setApplicationName("CharAIface")
    app.setApplicationDisplayName("CharAIface")
    app.setOrganizationName("LocketGoma")
    app.setQuitOnLastWindowClosed(False)
    _ensure_valid_application_font(app)

    project_root = runtime_root()
    app_icon = load_app_icon(project_root)
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    settings_path = resource_path("data", "settings.json")
    locale_path = resource_path("locales", "ui.csv")
    themes_dir = resource_path("themes")

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
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    app.set_main_window(window)

    app.applicationStateChanged.connect(
        lambda state: _restore_window_when_app_activated(window, state)
    )

    single_instance_server = FrontendSingleInstanceServer(window.show_session_window)
    single_instance_server.start()
    app.aboutToQuit.connect(single_instance_server.stop)

    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
