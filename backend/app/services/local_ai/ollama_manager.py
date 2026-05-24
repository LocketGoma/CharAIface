import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal

import httpx


OllamaRuntimeState = Literal[
    "ready",
    "not_installed",
    "server_unavailable",
]

OllamaModelState = Literal[
    "ready",
    "not_installed",
    "pull_failed",
    "unknown",
]


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass
class OllamaRuntimeStatus:
    provider: str
    installed: bool
    cli_path: str | None
    server_available: bool
    version: str | None
    can_install_with_winget: bool
    base_url: str
    state: OllamaRuntimeState
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OllamaModelStatus:
    model: str
    installed: bool
    pulled: bool
    state: OllamaModelState
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OllamaManager:
    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def runtime_status(self) -> OllamaRuntimeStatus:
        cli_path = shutil.which("ollama")
        installed = cli_path is not None
        server_available = self.is_server_available()
        version = self._get_cli_version() if installed else None
        can_install_with_winget = self.can_install_with_winget()

        if not installed:
            state: OllamaRuntimeState = "not_installed"
            error_code = "ollama_not_installed"
        elif not server_available:
            state = "server_unavailable"
            error_code = "ollama_server_unavailable"
        else:
            state = "ready"
            error_code = None

        return OllamaRuntimeStatus(
            provider="ollama",
            installed=installed,
            cli_path=cli_path,
            server_available=server_available,
            version=version,
            can_install_with_winget=can_install_with_winget,
            base_url=self.base_url,
            state=state,
            error_code=error_code,
        )

    def is_server_available(self) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/api/tags",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def list_models(self) -> list[str]:
        response = httpx.get(
            f"{self.base_url}/api/tags",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        result: list[str] = []

        for model in models:
            name = model.get("name")
            if isinstance(name, str):
                result.append(name)

        return result

    def has_model(self, model_name: str) -> bool:
        normalized_target = self._normalize_model_name(model_name)

        for installed_model in self.list_models():
            if self._normalize_model_name(installed_model) == normalized_target:
                return True

        return False

    def model_status(self, model_name: str) -> OllamaModelStatus:
        runtime = self.runtime_status()

        if runtime.state != "ready":
            return OllamaModelStatus(
                model=model_name,
                installed=False,
                pulled=False,
                state="unknown",
                error_code=runtime.error_code,
            )

        try:
            installed = self.has_model(model_name)
        except httpx.HTTPError as error:
            return OllamaModelStatus(
                model=model_name,
                installed=False,
                pulled=False,
                state="unknown",
                error_code="ollama_model_list_failed",
                error_detail=str(error),
            )

        if installed:
            return OllamaModelStatus(
                model=model_name,
                installed=True,
                pulled=False,
                state="ready",
            )

        return OllamaModelStatus(
            model=model_name,
            installed=False,
            pulled=False,
            state="not_installed",
            error_code="model_not_installed",
        )

    def prepare_model(
        self,
        model_name: str,
        auto_pull: bool,
        auto_start_server: bool,
    ) -> OllamaModelStatus:
        runtime = self.runtime_status()

        if not runtime.installed:
            return OllamaModelStatus(
                model=model_name,
                installed=False,
                pulled=False,
                state="unknown",
                error_code="ollama_not_installed",
            )

        if not runtime.server_available and auto_start_server:
            self.start_server()
            self._wait_for_server(timeout_seconds=10.0)
            runtime = self.runtime_status()

        if runtime.state != "ready":
            return OllamaModelStatus(
                model=model_name,
                installed=False,
                pulled=False,
                state="unknown",
                error_code=runtime.error_code,
            )

        current_model_status = self.model_status(model_name)

        if current_model_status.installed:
            return current_model_status

        if not auto_pull:
            return current_model_status

        pull_result = self.pull_model(model_name)

        if pull_result.returncode != 0:
            error_detail = pull_result.stderr.strip() or pull_result.stdout.strip()

            return OllamaModelStatus(
                model=model_name,
                installed=False,
                pulled=False,
                state="pull_failed",
                error_code="model_pull_failed",
                error_detail=error_detail,
            )

        return OllamaModelStatus(
            model=model_name,
            installed=True,
            pulled=True,
            state="ready",
        )

    def pull_model(self, model_name: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["ollama", "pull", model_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def can_install_with_winget(self) -> bool:
        return shutil.which("winget") is not None

    def install_runtime_with_winget(self) -> dict[str, Any]:
        if not self.can_install_with_winget():
            return {
                "success": False,
                "install_method": "winget",
                "returncode": 1,
                "error_code": "winget_not_available",
                "stdout": "",
                "stderr": "",
            }

        result = subprocess.run(
            [
                "winget",
                "install",
                "--id",
                "Ollama.Ollama",
                "--exact",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        return {
            "success": result.returncode == 0,
            "install_method": "winget",
            "returncode": result.returncode,
            "error_code": None if result.returncode == 0 else "ollama_install_failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def start_server(self) -> None:
        if shutil.which("ollama") is None:
            return

        creationflags = 0

        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    def status_payload(self) -> dict[str, Any]:
        runtime = self.runtime_status()

        payload: dict[str, Any] = {
            "runtime": runtime.to_dict(),
            "models": [],
        }

        if runtime.state == "ready":
            try:
                payload["models"] = self.list_models()
            except httpx.HTTPError as error:
                payload["models_error"] = str(error)
                payload["models_error_code"] = "ollama_model_list_failed"

        return payload

    def _wait_for_server(self, timeout_seconds: float) -> bool:
        started_at = time.monotonic()

        while time.monotonic() - started_at < timeout_seconds:
            if self.is_server_available():
                return True

            time.sleep(0.5)

        return False

    def _get_cli_version(self) -> str | None:
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )

            if result.returncode != 0:
                return None

            return result.stdout.strip() or None

        except (OSError, subprocess.SubprocessError):
            return None

    def _normalize_model_name(self, model_name: str) -> str:
        stripped = model_name.strip().lower()

        if ":" not in stripped:
            return f"{stripped}:latest"

        return stripped