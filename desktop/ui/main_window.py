from pathlib import Path
from desktop.chat.chat_session import ChatSession
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from desktop.characters.character_pack import CharacterPack
from desktop.characters.character_registry import CharacterRegistry
from desktop.core.character_state import CharacterStateController
from desktop.localization.localization_manager import LocalizationManager
from desktop.settings.app_settings import AppSettings
from desktop.settings.settings_repository import SettingsRepository
from desktop.theme.qss_builder import build_qss
from desktop.theme.theme_manager import ThemeManager
from desktop.theme.theme_model import ThemeDefinition
from desktop.ui.bottom_user_area import BottomUserArea
from desktop.ui.chat_view import ChatView
from desktop.ui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    MIN_WINDOW_WIDTH = 600
    MIN_WINDOW_HEIGHT = 450

    def __init__(
        self,
        localization: LocalizationManager,
        theme: ThemeDefinition,
        theme_manager: ThemeManager,
        settings: AppSettings,
        settings_repository: SettingsRepository,
    ) -> None:
        super().__init__()

        self.localization = localization
        self.theme = theme
        self.theme_manager = theme_manager
        self.settings = settings
        self.settings_repository = settings_repository

        self.character_state = CharacterStateController(done_to_idle_ms=3000)
        self.character_registry: CharacterRegistry | None = None
        self.current_character_pack: CharacterPack | None = None
        self.chat_session = ChatSession()

        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(self.settings.window_width, self.settings.window_height)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = self._create_header()
        content_area = self._create_content_area()

        root_layout.addWidget(header)
        root_layout.addWidget(content_area, stretch=1)

        self.setCentralWidget(root)

        self.apply_theme_from_settings()
        self.retranslate_ui()
        QTimer.singleShot(0, self._restore_window_geometry)

        self._add_assistant_message(
            "CharAIface 기본 화면 출력 테스트입니다. 아직 AI 연결 전입니다."
        )

    def _create_content_area(self) -> QWidget:
        content_area = QWidget()
        content_area.setObjectName("ContentArea")

        self.content_stack = QStackedLayout(content_area)
        self.content_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.content_stack.setContentsMargins(0, 0, 0, 0)
        self.content_stack.setSpacing(0)

        self.chat_view = ChatView()
        self.bottom_area = BottomUserArea(localization=self.localization)

        self.bottom_area.set_user_name(self.settings.user_name)

        self._load_character_registry()
        self._apply_selected_or_default_character_pack()

        self.bottom_area.send_requested.connect(self.on_send_requested)
        self.bottom_area.text_changed.connect(
            self.character_state.on_user_text_changed
        )
        self.character_state.state_changed.connect(self.bottom_area.set_state)

        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.bottom_area)

        self.content_stack.setCurrentWidget(self.bottom_area)
        self.bottom_area.raise_()

        return content_area

    def _create_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(56)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)

        self.title_label = QLabel()
        self.title_label.setObjectName("HeaderTitle")

        self.settings_button = QPushButton()
        self.settings_button.setObjectName("HeaderButton")
        self.settings_button.clicked.connect(self.open_settings_dialog)

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.settings_button)

        return header

    def _load_character_registry(self) -> None:
        project_root = Path(__file__).resolve().parents[2]

        builtin_characters_dir = (
            project_root
            / "resources"
            / "builtin"
            / "characters"
        )

        user_characters_dir = (
            project_root
            / "resources"
            / "characters"
        )

        self.character_registry = CharacterRegistry(
            builtin_characters_dir=builtin_characters_dir,
            user_characters_dir=user_characters_dir,
        )
        self.character_registry.load()

        print(
            "[CharacterRegistry] Loaded "
            f"{len(self.character_registry.packs)} character pack(s)."
        )

        for warning in self.character_registry.warnings:
            print(f"[CharacterRegistry] Warning: {warning}")

        for invalid in self.character_registry.invalid_packs:
            source = invalid.get("source", "unknown")
            path = invalid.get("path", "")

            print(f"[CharacterRegistry] Invalid [{source}]: {path}")

            for message in invalid.get("messages", []):
                print(f"  - {message}")

    def _apply_selected_or_default_character_pack(self) -> None:
        if self.character_registry is None:
            print("[CharacterRegistry] Registry is not initialized.")
            self._show_missing_default_character_warning()
            return

        character_pack = self.character_registry.get_pack(
            self.settings.selected_character_id
        )

        if character_pack is None:
            character_pack = self.character_registry.get_default_pack()

        if character_pack is None:
            print("[CharacterRegistry] No valid character pack found.")
            self._show_missing_default_character_warning()
            return

        self._apply_character_pack(character_pack)

    def _apply_character_pack(self, character_pack: CharacterPack) -> None:
        self.current_character_pack = character_pack
        self.settings.selected_character_id = character_pack.id

        self.bottom_area.set_character_name(character_pack.name)
        self.bottom_area.set_avatar_images(character_pack.avatar_images_as_str())

        if self.character_registry is not None:
            source = (
                "builtin"
                if self.character_registry.is_builtin(character_pack.id)
                else "user"
            )
        else:
            source = "unknown"

        print(
            "[CharacterRegistry] Applied character: "
            f"{character_pack.name} ({character_pack.id}) [{source}]"
        )
        
    def _show_missing_default_character_warning(self) -> None:
        QMessageBox.critical(
            self,
            "CharAIface",
            "기본 캐릭터가 없습니다!",
        )

        app = QApplication.instance()

        if app is not None:
            QTimer.singleShot(0, app.quit)
        else:
            QTimer.singleShot(0, self.close)

    def open_settings_dialog(self) -> None:
        if self.character_registry is None:
            print("[Settings] CharacterRegistry is not initialized.")
            return

        dialog = SettingsDialog(
            settings=self.settings.model_copy(deep=True),
            localization=self.localization,
            theme_manager=self.theme_manager,
            character_registry=self.character_registry,
            parent=self,
        )

        if not dialog.exec():
            return

        dialog.apply_to_settings()
        new_settings = dialog.settings

        self._apply_settings(new_settings)

    def _apply_settings(self, new_settings: AppSettings) -> None:
        old_language = self.settings.language
        old_theme_id = self.settings.theme_id
        old_character_id = self.settings.selected_character_id

        self.settings = new_settings

        if self.settings.language != old_language:
            try:
                self.localization.set_language(self.settings.language)
            except ValueError:
                print(
                    f'[Settings] Unsupported language "{self.settings.language}". '
                    f'Keeping "{old_language}".'
                )
                self.settings.language = old_language

        if (
            self.settings.theme_id != old_theme_id
            or self.settings.selected_character_id != old_character_id
        ):
            self.apply_theme_from_settings()

        if (
            self.character_registry is not None
            and self.settings.selected_character_id != old_character_id
        ):
            character_pack = self.character_registry.get_pack(
                self.settings.selected_character_id
            )

            if character_pack is not None:
                self._apply_character_pack(character_pack)
            else:
                print(
                    "[Settings] Unknown character id: "
                    f"{self.settings.selected_character_id}"
                )
                self.settings.selected_character_id = old_character_id

        self.bottom_area.set_user_name(self.settings.user_name)
        self.retranslate_ui()

        self.settings_repository.save(self.settings)

    def apply_theme(self, theme: ThemeDefinition) -> None:
        self.theme = theme
        self.setStyleSheet(build_qss(theme))

    def apply_theme_from_settings(self) -> None:
        if self.settings.theme_id == "character":
            character_pack = self.current_character_pack

            if character_pack is not None and character_pack.theme is not None:
                try:
                    character_theme = self.theme_manager.create_character_theme(
                        base_theme_id=character_pack.theme.base_theme,
                        palette_override=character_pack.theme.palette_override,
                        character_name=character_pack.name,
                    )
                    self.apply_theme(character_theme)
                    return

                except ValueError as error:
                    print(f"[Theme] Failed to apply character theme: {error}")

            try:
                self.apply_theme(self.theme_manager.get_theme("light"))
            except ValueError:
                self.apply_theme(self.theme)

            return

        try:
            theme = self.theme_manager.get_theme(self.settings.theme_id)
            self.apply_theme(theme)

        except ValueError:
            print(
                f'[Theme] Unknown theme "{self.settings.theme_id}". '
                "Falling back to light."
            )
            self.settings.theme_id = "light"
            self.apply_theme(self.theme_manager.get_theme("light"))

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.localization.t("app.title"))
        self.title_label.setText(self.localization.t("app.title"))
        self.settings_button.setText(self.localization.t("settings.title"))
        self.bottom_area.retranslate_ui()
        self.bottom_area.set_user_name(self.settings.user_name)

    def _add_user_message(self, content: str) -> None:
        message = self.chat_session.add_user_message(content)
        self.chat_view.add_chat_message(message)

    def _add_assistant_message(self, content: str) -> None:
        message = self.chat_session.add_assistant_message(content)
        self.chat_view.add_chat_message(message)

    def on_send_requested(self, text: str) -> None:
        self.content_stack.setCurrentWidget(self.bottom_area)
        self.bottom_area.raise_()
        self.character_state.on_message_sent()
        self._add_user_message(text)

        QTimer.singleShot(300, self._show_fake_assistant_typing)
        QTimer.singleShot(700, lambda: self._add_fake_assistant_response(text))

    def _show_fake_assistant_typing(self) -> None:
        self.character_state.on_assistant_typing()

    def _add_fake_assistant_response(self, text: str) -> None:
        self._add_assistant_message(f"임시 응답입니다. 입력한 내용: {text}")

        self.character_state.on_assistant_done()

    def _restore_window_geometry(self) -> None:
        width = max(self.MIN_WINDOW_WIDTH, self.settings.window_width)
        height = max(self.MIN_WINDOW_HEIGHT, self.settings.window_height)

        self.resize(width, height)

    def closeEvent(self, event) -> None:
        self.settings.window_width = self.width()
        self.settings.window_height = self.height()
        self.settings_repository.save(self.settings)

        super().closeEvent(event)