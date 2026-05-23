import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import httpx


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass
class OllamaCheckResult:
    installed: bool
    cli_path: str | None
    server_available: bool
    version: str | None
    error: str | None = None


@dataclass
class OllamaModelResult:
    model: str
    installed: bool
    pulled: bool
    error: str | None = None


class OllamaManager:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def check(self) -> OllamaCheckResult:
        cli_path = shutil.which("ollama")
        installed = cli_path is not None

        version = self._get_cli_version() if installed else None
        server_available = self.is_server_available()

        return OllamaCheckResult(
            installed=installed,
            cli_path=cli_path,
            server_available=server_available,
            version=version,
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

    def ensure_model(
        self,
        model_name: str,
        auto_pull: bool = True,
    ) -> OllamaModelResult:
        check_result = self.check()

        if not check_result.installed:
            return OllamaModelResult(
                model=model_name,
                installed=False,
                pulled=False,
                error="Ollama CLI is not installed or not found in PATH.",
            )

        if not check_result.server_available:
            self.try_start_server()
            self._wait_for_server(timeout_seconds=10.0)

        if not self.is_server_available():
            return OllamaModelResult(
                model=model_name,
                installed=False,
                pulled=False,
                error="Ollama server is not available.",
            )

        if self.has_model(model_name):
            return OllamaModelResult(
                model=model_name,
                installed=True,
                pulled=False,
            )

        if not auto_pull:
            return OllamaModelResult(
                model=model_name,
                installed=False,
                pulled=False,
                error="Model is not installed.",
            )

        pull_result = self.pull_model(model_name)

        if pull_result.returncode != 0:
            error_text = pull_result.stderr.strip() or pull_result.stdout.strip()

            return OllamaModelResult(
                model=model_name,
                installed=False,
                pulled=False,
                error=error_text or "Failed to pull Ollama model.",
            )

        return OllamaModelResult(
            model=model_name,
            installed=True,
            pulled=True,
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

    def install_ollama_with_winget(self) -> subprocess.CompletedProcess[str]:
        if not self.can_install_with_winget():
            return subprocess.CompletedProcess(
                args=["winget"],
                returncode=1,
                stdout="",
                stderr="winget is not available.",
            )

        return subprocess.run(
            [
                "winget",
                "install",
                "--id",
                "Ollama.Ollama",
                "-e",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def try_start_server(self) -> None:
        if shutil.which("ollama") is None:
            return

        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

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

    def status_payload(self) -> dict[str, Any]:
        check_result = self.check()

        payload: dict[str, Any] = {
            "installed": check_result.installed,
            "cli_path": check_result.cli_path,
            "server_available": check_result.server_available,
            "version": check_result.version,
            "can_install_with_winget": self.can_install_with_winget(),
            "base_url": self.base_url,
        }

        if check_result.server_available:
            try:
                payload["models"] = self.list_models()
            except httpx.HTTPError as error:
                payload["models_error"] = str(error)

        return payload