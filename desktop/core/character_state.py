from PySide6.QtCore import QObject, QTimer, Signal


class CharacterStateController(QObject):
    state_changed = Signal(str)

    def __init__(self, done_to_idle_ms: int = 3000) -> None:
        super().__init__()

        self.current_state = "idle"
        self.done_to_idle_ms = done_to_idle_ms

        self.done_to_idle_timer = QTimer(self)
        self.done_to_idle_timer.setSingleShot(True)
        self.done_to_idle_timer.timeout.connect(self.to_idle)

    def set_state(self, state: str) -> None:
        if self.current_state == state:
            return

        self.done_to_idle_timer.stop()

        self.current_state = state
        self.state_changed.emit(state)

        if state in {"assistant_done", "panic"}:
            self.done_to_idle_timer.start(self.done_to_idle_ms)

    def to_idle(self) -> None:
        self.set_state("idle")

    def on_user_text_changed(self, text: str) -> None:
        if self.current_state in {
            "thinking",
            "searching",
            "assistant_typing",
            "panic",
        }:
            return

        if text.strip():
            self.set_state("user_typing")
        else:
            self.set_state("idle")

    def on_message_sent(self) -> None:
        self.set_state("thinking")

    def on_assistant_typing(self) -> None:
        self.set_state("assistant_typing")

    def on_assistant_done(self) -> None:
        self.set_state("assistant_done")

    def on_error(self) -> None:
        self.set_state("error")

    def on_panic(self) -> None:
        self.set_state("panic")
