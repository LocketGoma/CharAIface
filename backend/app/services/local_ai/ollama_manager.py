import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterator, Literal

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

    def list_model_details(self) -> list[dict[str, Any]]:
        response = httpx.get(
            f"{self.base_url}/api/tags",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        result: list[dict[str, Any]] = []

        for model in models:
            if not isinstance(model, dict):
                continue

            name = model.get("name")
            if not isinstance(name, str) or not name.strip():
                continue

            result.append({
                "name": name,
                "model": model.get("model") or name,
                "size": model.get("size"),
                "digest": model.get("digest"),
                "modified_at": model.get("modified_at"),
                "details": model.get("details") if isinstance(model.get("details"), dict) else {},
            })

        result.sort(key=lambda item: str(item.get("name") or "").lower())
        return result

    def get_model_detail(self, model_name: str) -> dict[str, Any] | None:
        normalized_target = self._normalize_model_name(model_name)

        for model in self.list_model_details():
            name = str(model.get("name") or model.get("model") or "")
            if self._normalize_model_name(name) == normalized_target:
                return model

        return None

    def get_model_digest(self, model_name: str) -> str:
        try:
            detail = self.get_model_detail(model_name)
        except httpx.HTTPError:
            return ""

        if not detail:
            return ""

        return str(detail.get("digest") or "").strip()

    def list_models(self) -> list[str]:
        return [
            str(model["name"])
            for model in self.list_model_details()
            if isinstance(model.get("name"), str)
        ]

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


    def prepare_model_stream(
        self,
        model_name: str,
        auto_pull: bool,
        auto_start_server: bool,
        auto_install_runtime: bool = False,
        force_pull: bool = False,
    ) -> Iterator[dict[str, Any]]:
        runtime = self.runtime_status()

        yield {
            "event": "runtime_status",
            "runtime": runtime.to_dict(),
            "model": model_name,
            "progress": None,
        }

        if not runtime.installed:
            if auto_install_runtime:
                install_result = self.install_runtime_with_winget()
                yield {
                    "event": "runtime_install_finished",
                    "model": model_name,
                    "install_result": install_result,
                    "progress": None,
                }
                runtime = self.runtime_status()

                if not install_result.get("success"):
                    yield {
                        "event": "finished",
                        "provider": "ollama",
                        "success": False,
                        "runtime": runtime.to_dict(),
                        "model": {
                            "model": model_name,
                            "installed": False,
                            "pulled": False,
                            "state": "unknown",
                            "error_code": install_result.get("error_code")
                            or "ollama_install_failed",
                        },
                    }
                    return
            else:
                yield {
                    "event": "finished",
                    "provider": "ollama",
                    "success": False,
                    "runtime": runtime.to_dict(),
                    "model": OllamaModelStatus(
                        model=model_name,
                        installed=False,
                        pulled=False,
                        state="unknown",
                        error_code="ollama_not_installed",
                    ).to_dict(),
                }
                return

        if not runtime.server_available and auto_start_server:
            self.start_server()
            self._wait_for_server(timeout_seconds=10.0)
            runtime = self.runtime_status()
            yield {
                "event": "runtime_status",
                "runtime": runtime.to_dict(),
                "model": model_name,
                "progress": None,
            }

        if runtime.state != "ready":
            yield {
                "event": "finished",
                "provider": "ollama",
                "success": False,
                "runtime": runtime.to_dict(),
                "model": OllamaModelStatus(
                    model=model_name,
                    installed=False,
                    pulled=False,
                    state="unknown",
                    error_code=runtime.error_code,
                ).to_dict(),
            }
            return

        current_model_status = self.model_status(model_name)
        before_digest = self.get_model_digest(model_name) if current_model_status.installed else ""

        if current_model_status.installed and not force_pull:
            yield {
                "event": "finished",
                "provider": "ollama",
                "success": True,
                "runtime": runtime.to_dict(),
                "model": {
                    **current_model_status.to_dict(),
                    "digest": before_digest,
                    "updated": False,
                    "update_checked": False,
                },
            }
            return

        if not auto_pull:
            yield {
                "event": "finished",
                "provider": "ollama",
                "success": False,
                "runtime": runtime.to_dict(),
                "model": current_model_status.to_dict(),
            }
            return

        yield {
            "event": "download_started",
            "provider": "ollama",
            "model": model_name,
            "progress": 0,
            "status": "starting",
            "force_pull": force_pull,
            "previous_digest": before_digest,
        }

        last_progress = 0
        last_status = "starting"
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": True},
                timeout=httpx.Timeout(None),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue

                    try:
                        payload = json.loads(line)
                    except (TypeError, ValueError):
                        continue

                    if not isinstance(payload, dict):
                        continue

                    status = payload.get("status")
                    if isinstance(status, str) and status.strip():
                        last_status = status.strip()

                    total = payload.get("total")
                    completed = payload.get("completed")
                    progress = None

                    if isinstance(total, int) and total > 0 and isinstance(completed, int):
                        progress = int(max(0, min(100, round((completed / total) * 100))))
                        last_progress = progress
                    elif status == "success":
                        progress = 100
                        last_progress = 100

                    yield {
                        "event": "download_progress",
                        "provider": "ollama",
                        "model": model_name,
                        "status": last_status,
                        "digest": payload.get("digest"),
                        "total": total,
                        "completed": completed,
                        "progress": progress if progress is not None else last_progress,
                    }

        except httpx.HTTPError as error:
            yield {
                "event": "finished",
                "provider": "ollama",
                "success": False,
                "runtime": self.runtime_status().to_dict(),
                "model": OllamaModelStatus(
                    model=model_name,
                    installed=False,
                    pulled=False,
                    state="pull_failed",
                    error_code="model_pull_failed",
                    error_detail=str(error),
                ).to_dict(),
            }
            return

        installed = False
        after_digest = ""
        try:
            installed = self.has_model(model_name)
            after_digest = self.get_model_digest(model_name) if installed else ""
        except httpx.HTTPError:
            installed = False

        updated = bool(force_pull and before_digest and after_digest and before_digest != after_digest)

        yield {
            "event": "finished",
            "provider": "ollama",
            "success": installed,
            "runtime": self.runtime_status().to_dict(),
            "model": {
                **OllamaModelStatus(
                    model=model_name,
                    installed=installed,
                    pulled=installed,
                    state="ready" if installed else "pull_failed",
                    error_code=None if installed else "model_pull_failed",
                ).to_dict(),
                "digest": after_digest,
                "previous_digest": before_digest,
                "updated": updated,
                "update_checked": bool(force_pull),
            },
        }


    def delete_model(
        self,
        model_name: str,
        auto_start_server: bool,
    ) -> dict[str, Any]:
        model_name = model_name.strip()

        if not model_name:
            return {
                "success": False,
                "deleted": False,
                "model": "",
                "error_code": "model_name_empty",
            }

        runtime = self.runtime_status()

        if not runtime.installed:
            return {
                "success": False,
                "deleted": False,
                "runtime": runtime.to_dict(),
                "model": model_name,
                "error_code": "ollama_not_installed",
            }

        if not runtime.server_available and auto_start_server:
            self.start_server()
            self._wait_for_server(timeout_seconds=10.0)
            runtime = self.runtime_status()

        if runtime.state != "ready":
            return {
                "success": False,
                "deleted": False,
                "runtime": runtime.to_dict(),
                "model": model_name,
                "error_code": runtime.error_code or "ollama_server_unavailable",
            }

        try:
            if not self.has_model(model_name):
                return {
                    "success": True,
                    "deleted": False,
                    "runtime": runtime.to_dict(),
                    "model": model_name,
                    "state": "not_installed",
                }
        except httpx.HTTPError as error:
            return {
                "success": False,
                "deleted": False,
                "runtime": runtime.to_dict(),
                "model": model_name,
                "error_code": "ollama_model_list_failed",
                "error_detail": str(error),
            }

        try:
            response = httpx.request(
                "DELETE",
                f"{self.base_url}/api/delete",
                json={"name": model_name},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()

        except httpx.HTTPStatusError as error:
            return {
                "success": False,
                "deleted": False,
                "runtime": self.runtime_status().to_dict(),
                "model": model_name,
                "error_code": "model_delete_failed",
                "error_detail": error.response.text.strip(),
            }
        except httpx.HTTPError as error:
            return {
                "success": False,
                "deleted": False,
                "runtime": self.runtime_status().to_dict(),
                "model": model_name,
                "error_code": "model_delete_failed",
                "error_detail": str(error),
            }

        return {
            "success": True,
            "deleted": True,
            "runtime": self.runtime_status().to_dict(),
            "model": model_name,
            "state": "deleted",
        }

    def prepare_model(
        self,
        model_name: str,
        auto_pull: bool,
        auto_start_server: bool,
        force_pull: bool = False,
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

        if current_model_status.installed and not force_pull:
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

    def list_models_payload(self, auto_start_server: bool) -> dict[str, Any]:
        runtime = self.runtime_status()

        if runtime.installed and not runtime.server_available and auto_start_server:
            self.start_server()
            self._wait_for_server(timeout_seconds=10.0)
            runtime = self.runtime_status()

        if runtime.state != "ready":
            return {
                "success": False,
                "runtime": runtime.to_dict(),
                "models": [],
                "error_code": runtime.error_code or "ollama_server_unavailable",
            }

        try:
            models = self.list_model_details()
        except httpx.HTTPError as error:
            return {
                "success": False,
                "runtime": self.runtime_status().to_dict(),
                "models": [],
                "error_code": "ollama_model_list_failed",
                "error_detail": str(error),
            }

        return {
            "success": True,
            "runtime": self.runtime_status().to_dict(),
            "models": models,
            "count": len(models),
        }

    def _normalize_model_name(self, model_name: str) -> str:
        normalized = model_name.strip().lower()

        if not normalized:
            return normalized

        if ":" not in normalized:
            return f"{normalized}:latest"

        return normalized

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
