from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


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
        label = QLabel()
        label.setWordWrap(True)
        label.setText(f"<b>{role}</b><br>{text}")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if role.lower() == "user":
            label.setObjectName("UserMessageBubble")
        else:
            label.setObjectName("AssistantMessageBubble")

        self.layout.addWidget(label)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())