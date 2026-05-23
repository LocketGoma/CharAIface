import httpx

from shared.schema.chat import ChatRequest, ChatResponse


class BackendHttpClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:10420",
        timeout_seconds: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict | None:
        url = f"{self.base_url}/health"

        try:
            response = httpx.get(
                url,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] Health check failed: {error}")
            return None

    def chat(self, request: ChatRequest) -> ChatResponse | None:
        url = f"{self.base_url}/chat"

        try:
            response = httpx.post(
                url,
                json=request.model_dump(mode="json"),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return ChatResponse.model_validate(response.json())

        except httpx.HTTPError as error:
            print(f"[Backend] Chat request failed: {error}")
            return None
    def ollama_status(self) -> dict | None:
        url = f"{self.base_url}/local-ai/ollama/status"

        try:
            response = httpx.get(
                url,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] Ollama status request failed: {error}")
            return None

    def ensure_ollama_model(
        self,
        model: str,
        auto_pull: bool = True,
        auto_install_ollama: bool = False,
    ) -> dict | None:
        url = f"{self.base_url}/local-ai/ollama/ensure-model"

        try:
            response = httpx.post(
                url,
                json={
                    "model": model,
                    "auto_pull": auto_pull,
                    "auto_install_ollama": auto_install_ollama,
                },
                timeout=600.0,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] Ensure Ollama model failed: {error}")
            return None