from PySide6.QtCore import QObject, Signal

from desktop.client.backend_http_client import BackendHttpClient, ChatRequestError
from shared.schema.chat import ChatRequest, ChatResponse


class ChatResponseWorker(QObject):
    finished = Signal(str, str, object)
    failed = Signal(str, str, object)

    def __init__(
        self,
        backend_client: BackendHttpClient,
        request: ChatRequest,
        session_id: str,
        request_id: str,
    ) -> None:
        super().__init__()
        self.backend_client = backend_client
        self.request = request
        self.session_id = session_id
        self.request_id = request_id

    def run(self) -> None:
        try:
            response: ChatResponse | None = self.backend_client.chat(self.request)
        except ChatRequestError as error:
            self.failed.emit(self.session_id, self.request_id, error.failure.to_dict())
            return
        except Exception as error:
            self.failed.emit(
                self.session_id,
                self.request_id,
                {
                    "error_code": "unknown_error",
                    "error_detail": str(error),
                    "exception_type": type(error).__name__,
                },
            )
            return

        if response is None:
            self.failed.emit(
                self.session_id,
                self.request_id,
                {
                    "error_code": "backend_chat_request_failed",
                    "error_detail": "Backend chat request returned no response.",
                },
            )
            return

        self.finished.emit(self.session_id, self.request_id, response)
