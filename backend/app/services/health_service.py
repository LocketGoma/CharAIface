import os
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.app.services.local_ai.ollama_manager import OllamaManager


APP_NAME = "CharAIface Backend"
APP_VERSION = "0.1.0"
CLOUD_AI_TIMEOUT_SECONDS = 5.0


class HealthService:
    def __init__(self, ollama_manager: OllamaManager | None = None) -> None:
        self.ollama_manager = ollama_manager or OllamaManager()

    def build_payload(self) -> dict[str, Any]:
        local_ai = self._local_ai_status()
        cloud_ai = self._cloud_ai_status()

        local_available = bool(local_ai.get("available"))
        cloud_available = bool(cloud_ai.get("available"))
        cloud_configured = bool(cloud_ai.get("configured"))
        cloud_error = cloud_configured and not cloud_available
        ai_available = local_available or cloud_available

        checks = {
            "backend_api": "available",
            "chat_api": "available",
            "chat_service": "available",
            "local_ai_available": local_available,
            "cloud_ai_available": cloud_available,
            "ai_available": ai_available,
        }

        errors: list[dict[str, str]] = []

        if not ai_available:
            errors.append(
                {
                    "code": "no_ai_available",
                    "message": "No usable local or cloud AI provider is available.",
                }
            )

        if cloud_error:
            errors.append(
                {
                    "code": "cloud_ai_unavailable",
                    "message": "Cloud AI is configured but is not reachable or did not pass validation.",
                }
            )

        status = "ok" if not errors else "error"

        return {
            "status": status,
            "app": APP_NAME,
            "version": APP_VERSION,
            "backend_api": "available",
            "chat_api": "available",
            "chat_service": "available",
            "checks": checks,
            "errors": errors,
            "local_ai": local_ai,
            "cloud_ai": cloud_ai,
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
        }

    def status_code_for_payload(self, payload: dict[str, Any]) -> int:
        if payload.get("status") == "ok":
            return 200

        return 503

    def _local_ai_status(self) -> dict[str, Any]:
        try:
            status_payload = self.ollama_manager.status_payload()
        except Exception as error:
            return {
                "provider": "ollama",
                "available": False,
                "state": "error",
                "error_code": "local_ai_status_failed",
                "error_detail": str(error),
                "status": {},
            }

        runtime = status_payload.get("runtime", {})
        models = status_payload.get("models", [])
        runtime_ready = runtime.get("state") == "ready"
        model_available = isinstance(models, list) and len(models) > 0
        available = bool(runtime_ready and model_available)

        if available:
            state = "ready"
            error_code = None
        elif not runtime_ready:
            state = runtime.get("state") or "runtime_unavailable"
            error_code = runtime.get("error_code") or "local_ai_runtime_unavailable"
        else:
            state = "no_model"
            error_code = "local_ai_model_not_available"

        return {
            "provider": "ollama",
            "available": available,
            "state": state,
            "error_code": error_code,
            "status": status_payload,
        }

    def _cloud_ai_status(self) -> dict[str, Any]:
        provider = self._detect_cloud_provider()

        if provider is None:
            return {
                "configured": False,
                "available": False,
                "provider": None,
                "state": "not_configured",
                "error_code": "cloud_ai_not_configured",
            }

        try:
            if provider == "openai":
                return self._check_openai()

            if provider == "openrouter":
                return self._check_openrouter()

            if provider == "anthropic":
                return self._check_anthropic()

            if provider == "gemini":
                return self._check_gemini()

            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "state": "unsupported_provider",
                "error_code": "cloud_ai_provider_unsupported",
            }

        except httpx.HTTPStatusError as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "state": "http_error",
                "error_code": "cloud_ai_http_error",
                "http_status": error.response.status_code,
                "error_detail": str(error),
            }
        except httpx.HTTPError as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "state": "request_failed",
                "error_code": "cloud_ai_request_failed",
                "error_detail": str(error),
            }
        except Exception as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "state": "error",
                "error_code": "cloud_ai_unknown_error",
                "error_detail": str(error),
            }

    def _detect_cloud_provider(self) -> str | None:
        if os.getenv("OPENAI_API_KEY"):
            return "openai"

        if os.getenv("OPENROUTER_API_KEY"):
            return "openrouter"

        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"

        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            return "gemini"

        provider = os.getenv("CHARAIFACE_CLOUD_AI_PROVIDER", "").strip().lower()

        if provider:
            return provider

        return None

    def _check_openai(self) -> dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY", "")
        response = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return {
            "configured": True,
            "available": True,
            "provider": "openai",
            "state": "ready",
            "error_code": None,
        }

    def _check_openrouter(self) -> dict[str, Any]:
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        response = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return {
            "configured": True,
            "available": True,
            "provider": "openrouter",
            "state": "ready",
            "error_code": None,
        }

    def _check_anthropic(self) -> dict[str, Any]:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        response = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return {
            "configured": True,
            "available": True,
            "provider": "anthropic",
            "state": "ready",
            "error_code": None,
        }

    def _check_gemini(self) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        response = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return {
            "configured": True,
            "available": True,
            "provider": "gemini",
            "state": "ready",
            "error_code": None,
        }
