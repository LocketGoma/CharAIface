from PySide6.QtCore import QPoint, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from desktop.localization.localization_manager import LocalizationManager
from desktop.ui.avatar_widget import AvatarWidget
from desktop.ui.composer import ComposerTextEdit


class BottomUserArea(QWidget):
    send_requested = Signal(str)
    cancel_requested = Signal()
    file_attach_requested = Signal()
    file_attachment_cancel_requested = Signal()
    text_changed = Signal(str)

    def __init__(self, localization: LocalizationManager) -> None:
        super().__init__()

        self.localization = localization
        self._composer_preferred_height: int | None = None
        self._response_pending = False

        self.setObjectName("BottomOverlayArea")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setMinimumSize(0, 0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(16, 8, 16, 16)
        root_layout.setSpacing(12)

        self.character_area = self._create_character_area()

        # Only the avatar image fades when it visually overlaps chat/session UI.
        # Name/state/user labels stay fully opaque so they remain readable.
        self.character_opacity_effect = QGraphicsOpacityEffect(self.avatar_widget)
        self.character_opacity_effect.setOpacity(1.0)
        self.avatar_widget.setGraphicsEffect(self.character_opacity_effect)

        self.composer = ComposerTextEdit()

        self.composer.send_requested.connect(self._emit_send)
        self.composer.textChanged.connect(self._emit_text_changed)

        composer_stack = QWidget()
        composer_stack.setObjectName("ComposerStack")
        composer_layout = QVBoxLayout(composer_stack)
        composer_layout.setContentsMargins(0, 0, 0, 0)
        composer_layout.setSpacing(6)

        attachment_row = QWidget()
        attachment_row.setObjectName("AttachmentRow")
        attachment_layout = QHBoxLayout(attachment_row)
        attachment_layout.setContentsMargins(0, 0, 0, 0)
        attachment_layout.setSpacing(6)

        self.attach_button = QPushButton("+")
        self.attach_button.setObjectName("AttachFileButton")
        self.attach_button.setFixedSize(34, 30)
        self.attach_button.clicked.connect(self.file_attach_requested.emit)

        self.attachment_pill = QFrame()
        self.attachment_pill.setObjectName("AttachmentPill")
        self.attachment_pill.setFixedHeight(30)
        self.attachment_pill.setVisible(False)
        attachment_pill_layout = QHBoxLayout(self.attachment_pill)
        attachment_pill_layout.setContentsMargins(10, 0, 6, 0)
        attachment_pill_layout.setSpacing(6)

        self.attachment_label = QLabel()
        self.attachment_label.setObjectName("AttachmentLabel")

        self.attachment_cancel_button = QPushButton("×")
        self.attachment_cancel_button.setObjectName("AttachmentCancelButton")
        self.attachment_cancel_button.setFixedSize(24, 24)
        self.attachment_cancel_button.clicked.connect(
            self.file_attachment_cancel_requested.emit
        )

        attachment_pill_layout.addWidget(self.attachment_label, stretch=1)
        attachment_pill_layout.addWidget(self.attachment_cancel_button)

        attachment_layout.addWidget(self.attach_button)
        attachment_layout.addWidget(self.attachment_pill, stretch=1)
        composer_layout.addWidget(attachment_row)
        composer_layout.addWidget(self.composer)

        self.send_button = QPushButton()
        self.send_button.setObjectName("SendButton")
        self.send_button.setFixedHeight(44)
        self.send_button.setMinimumWidth(104)
        self.send_button.clicked.connect(self._emit_send)

        root_layout.addWidget(
            self.character_area,
            alignment=Qt.AlignmentFlag.AlignBottom,
        )
        root_layout.addWidget(
            composer_stack,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignBottom,
        )
        root_layout.addWidget(
            self.send_button,
            alignment=Qt.AlignmentFlag.AlignBottom,
        )

        self.retranslate_ui()
        self.set_state("idle")
        QTimer.singleShot(0, self.sync_composer_height_to_left_name_area)

    def _create_character_area(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("CharacterArea")
        wrapper.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        wrapper.setFixedWidth(220)

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        character_box = QFrame()
        character_box.setObjectName("CharacterDisplayBox")
        character_box.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        character_layout = QVBoxLayout(character_box)
        character_layout.setContentsMargins(10, 10, 10, 10)
        character_layout.setSpacing(0)

        self.avatar_widget = AvatarWidget(size=160)

        self.character_info_box = QFrame()
        self.character_info_box.setObjectName("CharacterInfoBox")

        character_info_layout = QVBoxLayout(self.character_info_box)
        character_info_layout.setContentsMargins(10, 8, 10, 8)
        character_info_layout.setSpacing(4)

        self.character_name_label = QLabel("Default")
        self.character_name_label.setObjectName("CharacterNameLabel")
        self.character_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.state_label = QLabel()
        self.state_label.setObjectName("StateLabel")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        character_info_layout.addWidget(self.character_name_label)
        character_info_layout.addWidget(self.state_label)

        character_layout.addStretch()
        character_layout.addWidget(self.avatar_widget)
        character_layout.addWidget(self.character_info_box)
        character_layout.addStretch()

        self.user_name_box = QFrame()
        self.user_name_box.setObjectName("UserNameBox")
        self.user_name_box.setFixedHeight(44)

        user_name_layout = QHBoxLayout(self.user_name_box)
        user_name_layout.setContentsMargins(12, 4, 12, 4)
        user_name_layout.setSpacing(8)

        self.user_label = QLabel("유저 :")
        self.user_label.setObjectName("UserLabel")
        self.user_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.user_name_label = QLabel("곰")
        self.user_name_label.setObjectName("UserNameLabel")
        self.user_name_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        user_name_layout.addWidget(self.user_label)
        user_name_layout.addStretch()
        user_name_layout.addWidget(self.user_name_label)

        layout.addWidget(character_box, stretch=1)
        layout.addWidget(self.user_name_box)

        return wrapper

    def sync_composer_height_to_left_name_area(
        self,
        preferred_height: int | None = None,
    ) -> None:
        if preferred_height is not None:
            self._composer_preferred_height = int(preferred_height)

        target_height = self._left_name_stack_height()
        if self._composer_preferred_height is not None:
            target_height = max(target_height, self._composer_preferred_height)
        self.composer.set_fixed_height(target_height)

    def _left_name_stack_height(self) -> int:
        # The composer is bottom-aligned next to the left character/user block.
        # Match its top edge to CharacterInfoBox top by using the actual runtime
        # geometry instead of only size hints. This keeps the input field aligned
        # even when fonts, localization, or theme spacing change.
        info_top = self.character_info_box.mapTo(self.character_area, QPoint(0, 0)).y()
        user_bottom = self.user_name_box.mapTo(
            self.character_area,
            QPoint(0, self.user_name_box.height()),
        ).y()

        if user_bottom > info_top:
            return max(44, user_bottom - info_top)

        spacing = 8
        if self.character_area.layout() is not None:
            spacing = max(spacing, self.character_area.layout().spacing())

        character_info_height = max(
            self.character_info_box.sizeHint().height(),
            self.character_info_box.minimumSizeHint().height(),
        )
        user_name_height = max(
            self.user_name_box.height(),
            self.user_name_box.sizeHint().height(),
            44,
        )

        return character_info_height + spacing + user_name_height

    def recommended_input_area_height(self) -> int:
        attachment_height = 36 if self._has_visible_attachment() else 0
        return self.composer.height() + attachment_height + 46

    def retranslate_ui(self) -> None:
        self._update_send_button_text()
        self.attach_button.setToolTip(self.localization.t("chat.file.attach.button"))
        self.attachment_cancel_button.setToolTip(
            self.localization.t("chat.file.attach.cancel")
        )
        self.composer.set_placeholder_text(self.localization.t("chat.placeholder"))
        self.set_state("idle")

    def set_avatar_images(self, state_images: dict[str, str]) -> None:
        self.avatar_widget.set_state_images(state_images)

    def set_user_name(self, name: str) -> None:
        self.user_name_label.setText(name)
        QTimer.singleShot(0, self.sync_composer_height_to_left_name_area)

    def set_character_name(self, name: str) -> None:
        self.character_name_label.setText(name)
        QTimer.singleShot(0, self.sync_composer_height_to_left_name_area)

    def character_global_rect(self):
        top_left = self.character_area.mapToGlobal(self.character_area.rect().topLeft())
        return self.character_area.rect().translated(top_left)

    def set_character_occluded(
        self,
        is_occluded: bool,
        occluded_opacity: float,
    ) -> None:
        opacity = occluded_opacity if is_occluded else 1.0
        opacity = min(1.0, max(0.1, opacity))
        self.character_opacity_effect.setOpacity(opacity)

    def _emit_text_changed(self) -> None:
        self.text_changed.emit(self.composer.toPlainText())

    def _emit_send(self) -> None:
        if self._response_pending:
            self.cancel_requested.emit()
            return

        text = self.composer.toPlainText().strip()

        if not text and not self._has_visible_attachment():
            return

        self.composer.blockSignals(True)
        self.composer.clear()
        self.composer.blockSignals(False)

        self.send_requested.emit(text)

    def set_response_pending(self, is_pending: bool) -> None:
        self._response_pending = is_pending
        self._update_send_button_text()

    def set_attached_file_name(self, file_name: str | None) -> None:
        label = str(file_name or "").strip()
        self.attachment_label.setText(label)
        has_attachment = bool(label)
        self.attachment_pill.setVisible(has_attachment)

    def _has_visible_attachment(self) -> bool:
        return self.attachment_pill.isVisible()

    def _update_send_button_text(self) -> None:
        key = "chat.stop_generating" if self._response_pending else "chat.send"
        self.send_button.setText(self.localization.t(key))
        self.send_button.setProperty("responsePending", self._response_pending)
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

    def set_state(self, state: str) -> None:
        self.state_label.setText(self.localization.t(f"state.{state}"))
        self.avatar_widget.set_state(state)

    def set_state_text(self, text: str) -> None:
        self.state_label.setText(text)
