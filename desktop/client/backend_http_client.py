import json

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

            data = response.json()

            if response.status_code >= 400:
                print(
                    "[Backend] Health check returned non-ok status "
                    f"{response.status_code}: {data}"
                )

            return data

        except httpx.HTTPError as error:
            print(f"[Backend] Health check failed: {error}")
            return None
        except ValueError as error:
            print(f"[Backend] Health response was not JSON: {error}")
            return None


    def system_status(self) -> dict | None:
        url = f"{self.base_url}/system/status"

        try:
            response = httpx.get(
                url,
                timeout=max(5.0, self.timeout_seconds),
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] System status request failed: {error}")
            return None
        except ValueError as error:
            print(f"[Backend] System status response was not JSON: {error}")
            return None

    def chat(
        self,
        request: ChatRequest,
        timeout_seconds: float | None = None,
    ) -> ChatResponse | None:
        url = f"{self.base_url}/chat"
        request_timeout = timeout_seconds if timeout_seconds is not None else max(120.0, self.timeout_seconds)

        try:
            response = httpx.post(
                url,
                json=request.model_dump(mode="json"),
                timeout=request_timeout,
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

    def prepare_ollama_model(
        self,
        model: str,
        auto_pull: bool,
        auto_install_runtime: bool,
        auto_start_server: bool,
        timeout_seconds: float,
    ) -> dict | None:
        url = f"{self.base_url}/local-ai/ollama/prepare-model"

        try:
            response = httpx.post(
                url,
                json={
                    "model": model,
                    "auto_pull": auto_pull,
                    "auto_install_runtime": auto_install_runtime,
                    "auto_start_server": auto_start_server,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] Prepare Ollama model failed: {error}")
            return None

    def stream_prepare_ollama_model(
        self,
        model: str,
        auto_pull: bool,
        auto_install_runtime: bool,
        auto_start_server: bool,
        timeout_seconds: float,
    ):
        url = f"{self.base_url}/local-ai/ollama/prepare-model-stream"

        try:
            with httpx.stream(
                "POST",
                url,
                json={
                    "model": model,
                    "auto_pull": auto_pull,
                    "auto_install_runtime": auto_install_runtime,
                    "auto_start_server": auto_start_server,
                },
                timeout=timeout_seconds,
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue

                    try:
                        yield json.loads(line)
                    except ValueError as error:
                        print(f"[Backend] Invalid Ollama prepare stream payload: {error}")

        except httpx.HTTPError as error:
            print(f"[Backend] Stream prepare Ollama model failed: {error}")
            yield {
                "event": "finished",
                "success": False,
                "error_code": "request_failed",
                "model": {
                    "model": model,
                    "installed": False,
                    "pulled": False,
                    "state": "unknown",
                    "error_code": "request_failed",
                },
            }


    def list_ollama_models(
        self,
        auto_start_server: bool,
        timeout_seconds: float = 10.0,
    ) -> dict | None:
        url = f"{self.base_url}/local-ai/ollama/list-models"

        try:
            response = httpx.post(
                url,
                json={
                    "auto_start_server": auto_start_server,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] List Ollama models failed: {error}")
            return None
        except ValueError as error:
            print(f"[Backend] List Ollama models response was not JSON: {error}")
            return None


    def delete_ollama_model(
        self,
        model: str,
        auto_start_server: bool,
        timeout_seconds: float = 30.0,
    ) -> dict | None:
        url = f"{self.base_url}/local-ai/ollama/delete-model"

        try:
            response = httpx.post(
                url,
                json={
                    "model": model,
                    "auto_start_server": auto_start_server,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] Delete Ollama model failed: {error}")
            return None
        except ValueError as error:
            print(f"[Backend] Delete Ollama model response was not JSON: {error}")
            return None

    def fetch_cloud_ai_models(
        self,
        provider: str,
        auth_mode: str,
        credential_id: str,
        api_key_env: str | None,
        base_url: str = "",
        timeout_seconds: float = 30.0,
    ) -> dict | None:
        url = f"{self.base_url}/cloud-ai/models"

        try:
            response = httpx.post(
                url,
                json={
                    "provider": provider,
                    "auth_mode": auth_mode,
                    "credential_id": credential_id,
                    "api_key_env": api_key_env,
                    "base_url": base_url,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as error:
            print(f"[Backend] Cloud AI model list request failed: {error}")
            return None
        except ValueError as error:
            print(f"[Backend] Cloud AI model list response was not JSON: {error}")
            return None

