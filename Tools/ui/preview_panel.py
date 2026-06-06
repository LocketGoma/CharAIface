from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localization.localization_manager import LocalizationManager
from ui.animated_image_label import AnimatedImageLabel


class MainChatStage(QWidget):
    def __init__(
        self,
        localization: LocalizationManager,
        fullscreen: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.localization = localization
        self.fullscreen = fullscreen
        self.setObjectName("ChatStage")

        self.avatar = AnimatedImageLabel(self)
        self.avatar.setText(localization.t("preview.empty"))
        self.avatar.setObjectName("AvatarPlaceholder")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.avatar_width = 360 if fullscreen else 238
        self.avatar_height = 420 if fullscreen else 320
        self.avatar.setFixedSize(self.avatar_width, self.avatar_height)

        self.user_message = QLabel(localization.t("preview.message.user"), self)
        self.user_message.setObjectName("UserMessageBubble")
        self.assistant_message = QLabel(localization.t("preview.message.assistant"), self)
        self.assistant_message.setObjectName("AssistantMessageBubble")
        for label in (self.user_message, self.assistant_message):
            label.setWordWrap(True)
            label.setFixedWidth(560 if fullscreen else 390)

        self.composer_stack = QWidget(self)
        self.composer_stack.setObjectName("ComposerStack")
        composer_stack_layout = QVBoxLayout(self.composer_stack)
        composer_stack_layout.setContentsMargins(0, 0, 0, 0)
        composer_stack_layout.setSpacing(6)

        attachment_row = QWidget()
        attachment_layout = QHBoxLayout(attachment_row)
        attachment_layout.setContentsMargins(0, 0, 0, 0)
        attachment_layout.setSpacing(6)

        attach_button = QPushButton("+")
        attach_button.setObjectName("AttachFileButton")
        attach_button.setFixedSize(34, 30)
        attachment_label = QLabel(localization.t("chat.attachment"))
        attachment_label.setObjectName("AttachmentLabel")
        attachment_layout.addWidget(attach_button)
        attachment_layout.addWidget(attachment_label, 1)
        composer_stack_layout.addWidget(attachment_row)

        composer = QFrame()
        composer.setObjectName("ComposerFrame")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(0, 0, 0, 0)
        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText(localization.t("chat.input.placeholder"))
        self.input_box.setFixedHeight(96 if fullscreen else 68)
        composer_layout.addWidget(self.input_box)
        composer_stack_layout.addWidget(composer)

        self.send_button = QPushButton(localization.t("chat.send"), self)
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedSize(124 if fullscreen else 104, 52 if fullscreen else 44)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = self.width()
        height = self.height()

        if self.fullscreen:
            avatar_x = max(12, int(width * 0.05))
            avatar_y = max(80, height - self.avatar.height() - 36)
            message_x = max(avatar_x + self.avatar.width() + 80, int(width * 0.58))
            composer_x = avatar_x + self.avatar.width() + 20
            composer_y = height - 168
            composer_height = 146
            send_bottom_margin = 46
        else:
            avatar_x = 0
            avatar_y = max(22, height - self.avatar.height() - 12)
            message_x = max(avatar_x + 430, width - 430)
            composer_x = 238
            composer_y = height - 116
            composer_height = 104
            send_bottom_margin = 60

        self.avatar.move(avatar_x, avatar_y)

        self.user_message.move(message_x, 32)
        self.assistant_message.move(message_x, 110 if self.fullscreen else 92)

        send_width = self.send_button.width()
        composer_width = max(260, width - composer_x - send_width - 38)
        self.composer_stack.setGeometry(composer_x, composer_y, composer_width, composer_height)
        self.send_button.move(width - send_width - 18, height - send_bottom_margin)


class PreviewPanel(QFrame):
    def __init__(
        self,
        localization: LocalizationManager,
        fullscreen: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.localization = localization
        self.fullscreen = fullscreen
        self.image_path: Path | None = None

        self.setObjectName("PreviewPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(localization.t("preview.title"))
        title.setObjectName("PreviewTitle")
        header.addWidget(title)
        header.addStretch(1)

        self.fullscreen_button = QPushButton(localization.t("preview.fullscreen"))
        header.addWidget(self.fullscreen_button)
        if fullscreen:
            self.fullscreen_button.hide()
            root.setContentsMargins(0, 0, 0, 0)
        else:
            root.addLayout(header)

        self.main_preview = QWidget()
        self.main_preview.setObjectName("MainChatPreview")
        preview_layout = QVBoxLayout(self.main_preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        preview_layout.addWidget(self._create_content_area(), 1)
        root.addWidget(self.main_preview, 1)

    def _create_content_area(self) -> QWidget:
        content = QWidget()
        content.setObjectName("ContentArea")
        root_layout = QHBoxLayout(content)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._create_sidebar(), 0)

        main_stack = QWidget()
        main_stack.setObjectName("BodyArea")
        main_layout = QVBoxLayout(main_stack)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._create_header(), 0)
        self.stage = MainChatStage(self.localization, fullscreen=self.fullscreen)
        self.avatar = self.stage.avatar
        main_layout.addWidget(self.stage, 1)
        root_layout.addWidget(main_stack, 1)
        return content

    def _create_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("SessionSidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 14, 10, 14)
        layout.setSpacing(10)

        title = QLabel(self.localization.t("chat.sidebar.title"))
        title.setObjectName("SessionSidebarTitle")
        layout.addWidget(title)

        new_button = QPushButton(self.localization.t("chat.sidebar.new"))
        new_button.setObjectName("SessionSidebarPrimaryButton")
        layout.addWidget(new_button)

        item = QFrame()
        item.setObjectName("SessionListItemWidget")
        item_layout = QVBoxLayout(item)
        item_layout.setContentsMargins(10, 8, 10, 8)
        item_label = QLabel(self.localization.t("chat.sidebar.item"))
        item_label.setObjectName("SessionListItemLabel")
        item_label.setWordWrap(True)
        item_layout.addWidget(item_label)
        layout.addWidget(item)
        layout.addStretch(1)
        return sidebar

    def _create_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        title_group = QVBoxLayout()
        title_group.setSpacing(2)
        title = QLabel(self.localization.t("chat.header.title"))
        title.setObjectName("HeaderTitle")
        status = QLabel(self.localization.t("chat.header.status"))
        status.setObjectName("StateLabel")
        title_group.addWidget(title)
        title_group.addWidget(status)
        header_layout.addLayout(title_group)
        header_layout.addStretch(1)
        return header

    def set_image(self, path: Path | None) -> None:
        self.image_path = path

        if path is None:
            self.avatar.stop_animation()
            self.avatar.clear()
            self.avatar.setText(self.localization.t("preview.empty"))
            return

        if not self.avatar.set_image_path(path, animate=True):
            self.avatar.setText(self.localization.t("preview.empty"))
            return

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)


class FullscreenPreview(QDialog):
    def __init__(
        self,
        image_path: Path | None,
        localization: LocalizationManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(localization.t("preview.title"))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1280, 820)
        self.preview = PreviewPanel(localization, fullscreen=True)
        self.preview.fullscreen_button.setText("Esc")
        self.preview.fullscreen_button.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.preview)
        self.preview.set_image(image_path)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
