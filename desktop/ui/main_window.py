from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from desktop.characters.character_scanner import CharacterPackScanner
from desktop.core.character_state import CharacterStateController
from desktop.localization.localization_manager import LocalizationManager
from desktop.theme.qss_builder import build_qss
from desktop.theme.theme_model import ThemeDefinition
from desktop.ui.bottom_user_area import BottomUserArea
from desktop.ui.chat_view import ChatView


class MainWindow(QMainWindow):
    def __init__(
        self,
        localization: LocalizationManager,
        theme: ThemeDefinition,
    ) -> None:
        super().__init__()

        self.localization = localization
        self.theme = theme
        self.character_state = CharacterStateController(done_to_idle_ms=3000)

        self.resize(980, 720)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = self._create_header()
        content_area = self._create_content_area()

        root_layout.addWidget(header)
        root_layout.addWidget(content_area, stretch=1)

        self.setCentralWidget(root)

        self.apply_theme(self.theme)
        self.retranslate_ui()

        self.chat_view.add_message(
            "Assistant",
            "CharAIface 기본 화면 출력 테스트입니다. 아직 AI 연결 전입니다.",
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

        self._load_first_character_pack()

        self.bottom_area.send_requested.connect(self.on_send_requested)
        self.bottom_area.text_changed.connect(
            self.character_state.on_user_text_changed
        )
        self.character_state.state_changed.connect(self.bottom_area.set_state)

        self.content_stack.addWidget(self.chat_view)
        self.content_stack.addWidget(self.bottom_area)

        # Important:
        # StackAll still raises the current widget.
        # Keep bottom_area above chat_view so the character/input overlay is visible.
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

        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.settings_button)

        return header

    def _load_first_character_pack(self) -> None:
        project_root = Path(__file__).resolve().parents[2]

        builtin_characters_dir = (
            project_root
            / "resources"
            / "builtin"
            / "characters"
        )

        scanner = CharacterPackScanner(characters_dir=builtin_characters_dir)
        result = scanner.scan()

        if not result.valid_packs:
            print("[CharacterPack] No valid built-in character packs found.")

            for invalid in result.invalid_packs:
                print(f"[CharacterPack] Invalid: {invalid['path']}")

                for message in invalid["messages"]:
                    print(f"  - {message}")

            return

        character_pack = result.valid_packs[0]

        self.bottom_area.set_character_name(character_pack.name)
        self.bottom_area.set_avatar_images(character_pack.avatar_images_as_str())

        print(
            "[CharacterPack] Loaded built-in: "
            f"{character_pack.name} ({character_pack.id})"
        )

        for warning in character_pack.warnings:
            print(f"[CharacterPack] Warning: {warning}")

    def apply_theme(self, theme: ThemeDefinition) -> None:
        self.theme = theme
        self.setStyleSheet(build_qss(theme))

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.localization.t("app.title"))
        self.title_label.setText(self.localization.t("app.title"))
        self.settings_button.setText(self.localization.t("settings.title"))
        self.bottom_area.retranslate_ui()

    def on_send_requested(self, text: str) -> None:
        # Defensive: keep overlay on top after user interaction.
        self.content_stack.setCurrentWidget(self.bottom_area)
        self.bottom_area.raise_()

        self.character_state.on_message_sent()
        self.chat_view.add_message("User", text)

        QTimer.singleShot(300, self._show_fake_assistant_typing)
        QTimer.singleShot(700, lambda: self._add_fake_assistant_response(text))

    def _show_fake_assistant_typing(self) -> None:
        self.character_state.on_assistant_typing()

    def _add_fake_assistant_response(self, text: str) -> None:
        self.chat_view.add_message(
            "Assistant",
            f"임시 응답입니다. 입력한 내용: {text}",
        )

        self.character_state.on_assistant_done()