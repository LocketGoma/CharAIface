from html import escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from shared.schema.chat import ChatMessage, ChatRole


PAID_MODEL_LABEL = " (유료 모델 사용) "


class ChatView(QScrollArea):
    def __init__(self) -> None:
        super().__init__()

        self.user_display_name = "User"
        self.assistant_display_name = "Assistant"
        self._message_widgets: list[QWidget] = []
        self._bottom_reserved_height = 0
        self._left_reserved_width = 0
        self._right_reserved_width = 0

        self.setWidgetResizable(True)

        self.container = QWidget()
        self.container.setObjectName("ChatContainer")

        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)

        self.top_spacer = QSpacerItem(
            0,
            0,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Expanding,
        )
        self.layout.addItem(self.top_spacer)

        self.setWidget(self.container)
        self.verticalScrollBar().setSingleStep(36)
        self.verticalScrollBar().setPageStep(180)

    def set_user_display_name(self, name: str) -> None:
        stripped_name = name.strip()
        self.user_display_name = stripped_name or "User"

    def set_assistant_display_name(self, name: str) -> None:
        stripped_name = name.strip()
        self.assistant_display_name = stripped_name or "Assistant"

    def set_display_names(
        self,
        user_name: str,
        assistant_name: str,
    ) -> None:
        self.set_user_display_name(user_name)
        self.set_assistant_display_name(assistant_name)

    def set_bottom_reserved_height(self, height: int) -> None:
        self._bottom_reserved_height = max(0, height)
        self.setViewportMargins(0, 0, 0, self._bottom_reserved_height)

    def set_side_reserved_widths(
        self,
        left_width: int,
        right_width: int,
    ) -> None:
        self._left_reserved_width = max(0, left_width)
        self._right_reserved_width = max(0, right_width)

        self.layout.setContentsMargins(
            24 + self._left_reserved_width,
            24,
            24 + self._right_reserved_width,
            24,
        )

        self._update_message_max_widths()

    def message_widgets(self) -> list[QWidget]:
        return self._message_widgets.copy()

    def add_message(self, role: str, text: str) -> None:
        message = ChatMessage(
            role=self._normalize_role(role),
            content=text,
        )
        self.add_chat_message(message)

    def _message_max_width(self) -> int:
        available_width = (
            self.viewport().width()
            - self._left_reserved_width
            - self._right_reserved_width
            - 72
        )

        return max(260, int(available_width * 0.72))

    def _update_message_max_widths(self) -> None:
        max_width = self._message_max_width()

        for row in self._message_widgets:
            labels = row.findChildren(QLabel)
            for label in labels:
                label.setMaximumWidth(max_width)

    def add_chat_message(self, message: ChatMessage) -> None:
        row = QWidget()
        row.setObjectName("ChatMessageRow")

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        label = QLabel()
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(self._build_message_html(message))
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        label.setMaximumWidth(self._message_max_width())

        if message.role == "user":
            label.setObjectName("UserMessageBubble")
            row_layout.addStretch()
            row_layout.addWidget(label)
        else:
            label.setObjectName("AssistantMessageBubble")
            row_layout.addWidget(label)
            row_layout.addStretch()

        self.layout.addWidget(row)
        self._message_widgets.append(row)
        self._scroll_to_bottom_later()

    def clear_messages(self) -> None:
        for widget in self._message_widgets:
            self.layout.removeWidget(widget)
            widget.deleteLater()

        self._message_widgets.clear()
        self._scroll_to_bottom_later()

    def _scroll_to_bottom_later(self) -> None:
        QTimer.singleShot(0, self._scroll_to_bottom)
        QTimer.singleShot(30, self._scroll_to_bottom)
        QTimer.singleShot(80, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        self.container.adjustSize()
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _build_message_html(self, message: ChatMessage) -> str:
        display_role = escape(self._display_role(message))
        content = self._content_to_html(message.content)

        return f"<b>{display_role}</b><br>{content}"

    def _content_to_html(self, content: str) -> str:
        escaped_content = escape(content)
        return escaped_content.replace("\n", "<br>")

    def _normalize_role(self, role: str) -> ChatRole:
        lowered = role.lower()

        if lowered in {"system", "user", "assistant", "tool"}:
            return lowered  # type: ignore[return-value]

        return "assistant"

    def _display_role(self, message: ChatMessage) -> str:
        role = message.role

        if role == "user":
            return self.user_display_name

        if role == "assistant":
            display_name = self.assistant_display_name

            if self._is_paid_model_message(message):
                display_name += PAID_MODEL_LABEL

            return display_name

        if role == "system":
            return "System"

        if role == "tool":
            return "Tool"

        return role

    def _is_paid_model_message(self, message: ChatMessage) -> bool:
        value = message.metadata.get("paid_model_used", False)
        return bool(value)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_message_max_widths()