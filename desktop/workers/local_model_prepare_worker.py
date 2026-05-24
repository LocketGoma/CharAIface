from PySide6.QtCore import QObject, Signal, Slot

from desktop.client.backend_http_client import BackendHttpClient


class LocalModelPrepareWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        backend_client: BackendHttpClient,
        model: str,
        auto_pull: bool,
        auto_install_runtime: bool,
        auto_start_server: bool,
        timeout_seconds: float,
    ) -> None:
        super().__init__()

        self.backend_client = backend_client
        self.model = model
        self.auto_pull = auto_pull
        self.auto_install_runtime = auto_install_runtime
        self.auto_start_server = auto_start_server
        self.timeout_seconds = timeout_seconds

    @Slot()
    def run(self) -> None:
        result = self.backend_client.prepare_ollama_model(
            model=self.model,
            auto_pull=self.auto_pull,
            auto_install_runtime=self.auto_install_runtime,
            auto_start_server=self.auto_start_server,
            timeout_seconds=self.timeout_seconds,
        )

        if result is None:
            self.failed.emit("request_failed")
            return

        self.finished.emit(result)