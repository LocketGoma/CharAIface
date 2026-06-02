from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QTextEdit


class ComposerTextEdit(QTextEdit):
    send_requested = Signal()
    MIN_HEIGHT = 110
    MAX_HEIGHT = 220

    def __init__(self) -> None:
        super().__init__()

        self.setAcceptRichText(False)

        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setMaximumHeight(self.MAX_HEIGHT)
        self.setFixedHeight(self.MIN_HEIGHT)

        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def set_fixed_height(self, height: int) -> None:
        height = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, int(height)))
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setFixedHeight(height)

    def set_placeholder_text(self, text: str) -> None:
        self.setPlaceholderText(text)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return

            self.send_requested.emit()
            return

        super().keyPressEvent(event)
