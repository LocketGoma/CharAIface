from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from shared.schema.chat import ChatMessage


class ChatView(QScrollArea):
    def __init__(self) -> None:
        super().__init__()

        self.setWidgetResizable(True)

        self.container = QWidget()
        self.container.setObjectName("ChatContainer")

        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)

        self.setWidget(self.container)

    def add_message(self, role: str, text: str) -> None:
        message = ChatMessage(role=self._normalize_role(role), content=text)
        self.add_chat_message(message)

    def add_chat_message(self, message: ChatMessage) -> None:
        label = QLabel()
        label.setWordWrap(True)
        label.setText(f"<b>{self._display_role(message.role)}</b><br>{message.content}")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if message.role == "user":
            label.setObjectName("UserMessageBubble")
        else:
            label.setObjectName("AssistantMessageBubble")

        self.layout.addWidget(label)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def clear_messages(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _normalize_role(self, role: str):
        lowered = role.lower()

        if lowered in {"system", "user", "assistant", "tool"}:
            return lowered

        return "assistant"

    def _display_role(self, role: str) -> str:
        if role == "user":
            return "User"

        if role == "assistant":
            return "Assistant"

        if role == "system":
            return "System"

        if role == "tool":
            return "Tool"

        return role