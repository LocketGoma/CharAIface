from PySide6.QtCore import QObject, Signal

from desktop.client.backend_http_client import BackendHttpClient
from shared.schema.chat import ChatRequest, ChatResponse


class ChatResponseWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)

    def __init__(
        self,
        backend_client: BackendHttpClient,
        request: ChatRequest,
        session_id: str,
    ) -> None:
        super().__init__()
        self.backend_client = backend_client
        self.request = request
        self.session_id = session_id

    def run(self) -> None:
        try:
            response: ChatResponse | None = self.backend_client.chat(self.request)
        except Exception as error:
            self.failed.emit(self.session_id, str(error))
            return

        if response is None:
            self.failed.emit(self.session_id, "backend_chat_request_failed")
            return

        self.finished.emit(self.session_id, response)
