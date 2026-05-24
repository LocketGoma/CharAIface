from PySide6.QtCore import QObject, Signal

from desktop.client.backend_http_client import BackendHttpClient
from shared.schema.chat import ChatRequest, ChatResponse


class ChatResponseWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        backend_client: BackendHttpClient,
        request: ChatRequest,
    ) -> None:
        super().__init__()
        self.backend_client = backend_client
        self.request = request

    def run(self) -> None:
        try:
            response: ChatResponse | None = self.backend_client.chat(self.request)
        except Exception as error:
            self.failed.emit(str(error))
            return

        if response is None:
            self.failed.emit("backend_chat_request_failed")
            return

        self.finished.emit(response)
