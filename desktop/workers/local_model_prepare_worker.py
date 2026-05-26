from PySide6.QtCore import QObject, Signal, Slot

from desktop.client.backend_http_client import BackendHttpClient


class LocalModelPrepareWorker(QObject):
    progress = Signal(dict)
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
        force_pull: bool = False,
    ) -> None:
        super().__init__()

        self.backend_client = backend_client
        self.model = model
        self.auto_pull = auto_pull
        self.auto_install_runtime = auto_install_runtime
        self.auto_start_server = auto_start_server
        self.timeout_seconds = timeout_seconds
        self.force_pull = force_pull

    @Slot()
    def run(self) -> None:
        final_result: dict | None = None

        try:
            stream = self.backend_client.stream_prepare_ollama_model(
                model=self.model,
                auto_pull=self.auto_pull,
                auto_install_runtime=self.auto_install_runtime,
                auto_start_server=self.auto_start_server,
                timeout_seconds=self.timeout_seconds,
                force_pull=self.force_pull,
            )

            for payload in stream:
                if payload.get("event") == "finished":
                    final_result = payload
                    break

                self.progress.emit(payload)

        except Exception as error:
            print(f"[LocalAI] Local model prepare worker failed: {error}")
            self.failed.emit("request_failed")
            return

        if final_result is None:
            self.failed.emit("request_failed")
            return

        self.finished.emit(final_result)
