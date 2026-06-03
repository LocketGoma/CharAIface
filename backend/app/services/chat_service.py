from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal
from datetime import datetime

import httpx

from backend.app.services.cloud_auth_manager import (
    CloudAuthManager,
    CloudCredentialConfig,
)
from backend.app.services import file_export_response
from backend.app.services.file_analysis_service import FileAnalysisService
from backend.app.services.file_tool_loop import FileToolLoop
from backend.app.core.backend_helper import (
    ANTHROPIC_VERSION,
    cloud_provider_base_url,
    normalize_cloud_provider,
)
from backend.app.services.health_service import HealthService
from backend.app.services.system_status_service import SystemStatusService
from backend.app.services.web_search_service import (
    WebSearchError,
    WebSearchService,
)
from backend.app.services.web_search_context import WebSearchContextBuilder
from desktop.localization.localization_manager import LocalizationManager
from shared.schema.chat import ChatMessage, ChatRequest, ChatResponse


ChatRoute = Literal[
    "local_ollama",
    "local_error",
    "cloud_ai",
    "cloud_error",
    "command",
]

DEFAULT_LOCAL_MODEL = "qwen2.5:3b"
DEFAULT_LOCAL_AI_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_CHAT_TIMEOUT_SECONDS = 120.0
CLOUD_AI_CHAT_TIMEOUT_SECONDS = 120.0
MAX_CHAT_HISTORY_MESSAGES = 24

ROUTE_POLICY_HANDLERS = {
    "local_only": "_route_local_only",
    "cloud_only": "_route_cloud_when_available",
    "cloud_first": "_route_cloud_when_available",
    "local_first": "_route_local_only",
    "auto": "_route_auto",
}

CLOUD_CHAT_PROVIDER_HANDLERS = {
    "openai": "_call_openai_cloud_chat",
    "openrouter": "_call_openrouter_cloud_chat",
    "anthropic": "_call_anthropic_cloud_chat",
    "gemini": "_call_gemini_cloud_chat",
    "custom": "_call_custom_cloud_chat",
}

CLOUD_PROVIDER_PROBE_HANDLERS = {
    "openai": "_probe_openai_provider",
    "openrouter": "_probe_openrouter_provider",
    "anthropic": "_probe_anthropic_provider",
    "gemini": "_probe_gemini_provider",
}


class ChatService:
    def __init__(self) -> None:
        self.health_service = HealthService()
        self.system_status_service = SystemStatusService()
        self.web_search_service = WebSearchService()
        self.project_root = Path(__file__).resolve().parents[3]
        self.file_analysis_service = FileAnalysisService(self.project_root)
        self.file_tool_loop = FileToolLoop(self.file_analysis_service)
        self.settings_path = self.project_root / "resources" / "data" / "settings.json"
        self.localization = LocalizationManager(
            self.project_root / "resources" / "locales" / "ui.csv"
        )
        self.web_search_context = WebSearchContextBuilder(self.project_root)

    def create_response(self, request: ChatRequest) -> ChatResponse:
        latest_user_message = self._find_latest_user_message(request)

        if latest_user_message is None:
            return self._create_assistant_response(
                content=self._localized_backend_message(
                    request,
                    ko="사용자 메시지가 없습니다.",
                    en="There is no user message.",
                ),
                route="local_error",
                model="none",
                paid_model_used=False,
                metadata={
                    "source": "chat_service",
                    "reason": "no_user_message",
                    "error": True,
                },
            )

        command_response = self._try_handle_command(
            command_text=latest_user_message.content,
            request=request,
        )

        if command_response is not None:
            return command_response

        settings = self._effective_settings(request)
        web_search_context = self._prepare_web_search_context(
            latest_user_message=latest_user_message,
            request=request,
            settings=settings,
        )
        if web_search_context.get("fatal_response") is not None:
            return web_search_context["fatal_response"]

        route = self._select_route(request, settings)

        if route == "cloud_ai":
            cloud_response = self._create_cloud_ai_response(
                latest_user_message=latest_user_message,
                request=request,
                settings=settings,
                web_search_context=web_search_context,
            )
            if not self._response_has_error(cloud_response):
                return cloud_response

            # Paid/cloud model failures should not stop the conversation.
            # Fall back to the local model and let the local character briefly
            # acknowledge the fallback before answering the original request.
            return self._create_local_ollama_response(
                latest_user_message=latest_user_message,
                request=request,
                settings=settings,
                web_search_context=web_search_context,
                cloud_fallback_context=self._cloud_fallback_context_from_response(cloud_response),
            )

        local_response = self._create_local_ollama_response(
            latest_user_message=latest_user_message,
            request=request,
            settings=settings,
            web_search_context=web_search_context,
        )

        if not self._response_has_error(local_response):
            return local_response

        policy = self._route_policy(settings)
        if policy == "local_first" and self._cloud_ai_configured(settings):
            cloud_response = self._create_cloud_ai_response(
                latest_user_message=latest_user_message,
                request=request,
                settings=settings,
                web_search_context=web_search_context,
            )
            if not self._response_has_error(cloud_response):
                return cloud_response
            # Local already failed and cloud is unavailable too. Keep the local
            # failure as the primary response because it is the configured first route.
            return local_response

        return local_response

    def _find_latest_user_message(
        self,
        request: ChatRequest,
    ) -> ChatMessage | None:
        for message in reversed(request.messages):
            if message.role == "user":
                return message

        return None

    def _try_handle_command(
        self,
        command_text: str,
        request: ChatRequest,
    ) -> ChatResponse | None:
        normalized_command = command_text.strip().lower()

        if normalized_command == "/status":
            return self._create_status_response(request)

        if normalized_command == "/health":
            return self._create_health_response()

        if normalized_command == "/systemstatus":
            return self._create_system_status_response()

        if normalized_command == "/cloudaistatus":
            return self._create_cloud_ai_status_response(request)

        if normalized_command == "/help":
            return self._create_help_response()
        return None

    def _select_route(
        self,
        request: ChatRequest,
        settings: dict[str, Any] | None = None,
    ) -> ChatRoute:
        settings = settings or self._effective_settings(request)
        policy = self._route_policy(settings)
        cloud_available = self._cloud_ai_configured(settings) and self._cloud_ai_credentials_available(settings)
        handler_name = ROUTE_POLICY_HANDLERS.get(policy, ROUTE_POLICY_HANDLERS["auto"])
        handler = getattr(self, handler_name)
        return handler(request, settings, cloud_available)

    def _route_local_only(
        self,
        request: ChatRequest,
        settings: dict[str, Any],
        cloud_available: bool,
    ) -> ChatRoute:
        return "local_ollama"

    def _route_cloud_when_available(
        self,
        request: ChatRequest,
        settings: dict[str, Any],
        cloud_available: bool,
    ) -> ChatRoute:
        return "cloud_ai" if cloud_available else "local_ollama"

    def _route_auto(
        self,
        request: ChatRequest,
        settings: dict[str, Any],
        cloud_available: bool,
    ) -> ChatRoute:
        if not cloud_available:
            return "local_ollama"
        cloud_weight = self._cloud_ai_usage_weight(settings)
        if cloud_weight >= 75:
            return "cloud_ai"
        if cloud_weight <= 20:
            return "local_ollama"
        if self._should_auto_use_cloud(request):
            return "cloud_ai"
        return "local_ollama"

    def _route_policy(self, settings: dict[str, Any]) -> str:
        policy = str(settings.get("ai_route_policy") or "auto").strip().lower()
        allowed = {"local_only", "cloud_only", "local_first", "cloud_first", "auto"}
        if policy not in allowed:
            return "auto"
        return policy

    def _cloud_ai_usage_weight(self, settings: dict[str, Any]) -> int:
        try:
            weight = int(settings.get("cloud_ai_usage_weight_percent", 50))
        except (TypeError, ValueError):
            weight = 50

        weight = max(0, min(100, weight))
        return int(round(weight / 5) * 5)

    def _cloud_ai_configured(self, settings: dict[str, Any]) -> bool:
        cloud_enabled = bool(settings.get("cloud_ai_enabled"))
        cloud_provider = str(settings.get("cloud_ai_provider") or "none").strip().lower()
        cloud_model = str(settings.get("cloud_model") or "").strip()
        return cloud_enabled and cloud_provider != "none" and bool(cloud_model)

    def _cloud_ai_credentials_available(self, settings: dict[str, Any]) -> bool:
        """Return whether a configured cloud provider has usable credentials.

        Route selection must never raise because the chat endpoint is used for
        every turn.  The actual cloud API may still fail later, in which case
        the existing cloud->local fallback path handles the failure and
        /cloudaistatus reports details.  This method only answers whether it is
        reasonable to attempt the cloud route at all.
        """
        if not self._cloud_ai_configured(settings):
            return False

        provider = str(settings.get("cloud_ai_provider") or "none").strip().lower()
        auth_mode = str(settings.get("cloud_ai_auth_mode") or "secure_store").strip()
        credential_id = str(settings.get("cloud_ai_credential_id") or "").strip()
        api_key_env = str(settings.get("cloud_ai_api_key_env") or "").strip() or None

        credential_config = CloudCredentialConfig(
            provider=provider,
            auth_mode=auth_mode,
            credential_id=credential_id,
            api_key_env=api_key_env,
        )

        try:
            return bool(CloudAuthManager.get_api_key(credential_config))
        except Exception:
            return False

    def _should_auto_use_cloud(self, request: ChatRequest) -> bool:
        latest_user_message = self._find_latest_user_message(request)
        if latest_user_message is None:
            return False

        text = latest_user_message.content.strip()
        if not text:
            return False

        lowered = text.lower()

        explicit_cloud_keywords = (
            "클라우드", "유료모델", "유료 모델", "고성능", "정확하게", "자세히",
            "분석", "설계", "리팩토링", "최적화", "디버그", "에러", "로그",
            "구현", "코드", "프로그래밍", "언리얼", "unreal", "c++", "python",
            "traceback", "exception", "stack trace", "architecture", "refactor",
            "optimize", "debug", "analyze", "compare", "review",
        )
        if any(keyword in lowered for keyword in explicit_cloud_keywords):
            return True

        if "```" in text or len(text) >= 700:
            return True

        # Very short casual messages should stay local.
        if len(text) <= 120 and not any(char in text for char in "{}[]();=<>/"):
            return False

        return False

    def _response_has_error(self, response: ChatResponse) -> bool:
        metadata = getattr(response.message, "metadata", {}) or {}
        return bool(metadata.get("error"))

    def _create_local_ollama_response(
        self,
        latest_user_message: ChatMessage,
        request: ChatRequest,
        settings: dict[str, Any] | None = None,
        web_search_context: dict[str, Any] | None = None,
        cloud_fallback_context: dict[str, Any] | None = None,
    ) -> ChatResponse:
        settings = settings or self._effective_settings(request)
        model = str(settings.get("local_model") or DEFAULT_LOCAL_MODEL).strip()
        base_url = str(
            settings.get("local_ai_base_url") or DEFAULT_LOCAL_AI_BASE_URL
        ).strip()

        if not model:
            model = DEFAULT_LOCAL_MODEL
        if not base_url:
            base_url = DEFAULT_LOCAL_AI_BASE_URL

        app_language = self._request_language(request, settings)
        character_info = self._load_character_info(request.character_id, app_language, target_provider="local_ollama", settings=settings)
        model_messages = self._build_model_messages(
            request=request,
            character_info=character_info,
            target_provider="local_ollama",
            app_language=app_language,
            settings=settings,
            web_search_context=web_search_context,
            cloud_fallback_context=cloud_fallback_context,
        )
        tool_loop_messages = self._build_model_messages(
            request=request,
            character_info=character_info,
            target_provider="local_ollama",
            app_language=app_language,
            settings=settings,
            web_search_context=web_search_context,
            cloud_fallback_context=cloud_fallback_context,
            strip_latest_file_context=True,
        )

        tool_response_metadata: dict[str, Any] = {}
        try:
            tool_response = self.file_tool_loop.try_create_augmented_content(
                latest_user_message=latest_user_message,
                base_messages=tool_loop_messages,
                app_language=app_language,
                call_model=lambda messages: self._call_ollama_chat(
                    base_url=base_url,
                    model=model,
                    messages=messages,
                ),
            )
            if tool_response is not None:
                content = tool_response.content
                tool_response_metadata = tool_response.metadata
            else:
                content = self._call_ollama_chat(
                    base_url=base_url,
                    model=model,
                    messages=model_messages,
                )
        except httpx.TimeoutException as error:
            return self._create_local_error_response(
                request=request,
                model=model,
                error_code="model_timeout",
                error_detail=str(error) or "Local AI model generation timed out.",
            )
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            detail = self._safe_response_text(error.response)
            return self._create_local_error_response(
                request=request,
                model=model,
                error_code="ollama_http_error",
                error_detail=f"HTTP {status_code}: {detail}",
            )
        except httpx.HTTPError as error:
            return self._create_local_error_response(
                request=request,
                model=model,
                error_code="ollama_request_failed",
                error_detail=str(error),
            )
        except Exception as error:
            return self._create_local_error_response(
                request=request,
                model=model,
                error_code="ollama_unknown_error",
                error_detail=str(error),
            )

        if not content.strip():
            return self._create_local_error_response(
                request=request,
                model=model,
                error_code="ollama_empty_response",
                error_detail="Ollama returned an empty assistant message.",
            )

        if self.web_search_context.looks_like_refusal(content, web_search_context):
            content = self.web_search_context.fallback_answer(web_search_context, app_language, request.developer_mode)

        content = file_export_response.repair_refusal(
            content=content,
            request_content=latest_user_message.content,
        )

        return self._create_assistant_response(
            content=content,
            route="local_ollama",
            model=model,
            paid_model_used=False,
            metadata={
                "source": "ollama",
                "character_id": request.character_id,
                "character_name": character_info.get("name"),
                "base_url": base_url,
                "language": app_language,
                "render_markdown": self._render_markdown_requested(latest_user_message),
                **self.web_search_context.metadata(web_search_context),
                **self._cloud_fallback_metadata(cloud_fallback_context),
                **tool_response_metadata,
            },
        )

    def _create_cloud_ai_response(
        self,
        latest_user_message: ChatMessage,
        request: ChatRequest,
        settings: dict[str, Any],
        web_search_context: dict[str, Any] | None = None,
    ) -> ChatResponse:
        provider = str(settings.get("cloud_ai_provider") or "none").strip().lower()
        model = str(settings.get("cloud_model") or "").strip()
        base_url = str(settings.get("cloud_ai_base_url") or "").strip()
        auth_mode = str(settings.get("cloud_ai_auth_mode") or "secure_store").strip()
        credential_id = str(settings.get("cloud_ai_credential_id") or "").strip()
        api_key_env = str(settings.get("cloud_ai_api_key_env") or "").strip() or None

        if provider == "none" or not model:
            return self._create_cloud_error_response(
                request=request,
                model=model or "none",
                provider=provider,
                error_code="cloud_ai_not_configured",
                error_detail="Cloud AI provider or model is not configured.",
            )

        credential_config = CloudCredentialConfig(
            provider=provider,
            auth_mode=auth_mode,
            credential_id=credential_id,
            api_key_env=api_key_env,
        )

        try:
            api_key = CloudAuthManager.get_api_key(credential_config)
        except Exception as error:
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="cloud_ai_credential_error",
                error_detail=str(error),
            )

        if not api_key:
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="cloud_ai_api_key_missing",
                error_detail="Cloud AI API key was not found.",
            )

        app_language = self._request_language(request, settings)
        character_info = self._load_character_info(request.character_id, app_language, target_provider=provider, settings=settings)
        model_messages = self._build_model_messages(
            request=request,
            character_info=character_info,
            target_provider=provider,
            app_language=app_language,
            settings=settings,
            web_search_context=web_search_context,
        )
        tool_loop_messages = self._build_model_messages(
            request=request,
            character_info=character_info,
            target_provider=provider,
            app_language=app_language,
            settings=settings,
            web_search_context=web_search_context,
            strip_latest_file_context=True,
        )

        tool_response_metadata: dict[str, Any] = {}
        try:
            tool_response = self.file_tool_loop.try_create_augmented_content(
                latest_user_message=latest_user_message,
                base_messages=tool_loop_messages,
                app_language=app_language,
                call_model=lambda messages: self._call_cloud_ai_chat(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                ),
            )
            if tool_response is not None:
                content = tool_response.content
                tool_response_metadata = tool_response.metadata
            else:
                content = self._call_cloud_ai_chat(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=model_messages,
                )
        except httpx.TimeoutException as error:
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="model_timeout",
                error_detail=str(error) or "Cloud AI model generation timed out.",
            )
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            detail = self._safe_response_text(error.response)
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="cloud_ai_http_error",
                error_detail=f"HTTP {status_code}: {detail}",
            )
        except httpx.HTTPError as error:
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="cloud_ai_request_failed",
                error_detail=str(error),
            )
        except Exception as error:
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="cloud_ai_unknown_error",
                error_detail=str(error),
            )

        if not content.strip():
            return self._create_cloud_error_response(
                request=request,
                model=model,
                provider=provider,
                error_code="cloud_ai_empty_response",
                error_detail="Cloud AI returned an empty assistant message.",
            )

        if self.web_search_context.looks_like_refusal(content, web_search_context):
            content = self.web_search_context.fallback_answer(web_search_context, self._request_language(request, settings), request.developer_mode)

        content = file_export_response.repair_refusal(
            content=content,
            request_content=latest_user_message.content,
        )

        return self._create_assistant_response(
            content=content,
            route="cloud_ai",
            model=model,
            paid_model_used=True,
            metadata={
                "source": "cloud_ai",
                "provider": provider,
                "character_id": request.character_id,
                "character_name": character_info.get("name"),
                "language": app_language,
                "render_markdown": self._render_markdown_requested(latest_user_message),
                **self.web_search_context.metadata(web_search_context),
                **tool_response_metadata,
            },
        )

    def _call_ollama_chat(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.35,
                    "top_p": 0.82,
                    "repeat_penalty": 1.08,
                },
            },
            timeout=OLLAMA_CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        data = response.json()
        message = data.get("message", {})
        content = message.get("content", "")

        if not isinstance(content, str):
            return ""

        return content.strip()

    def _call_cloud_ai_chat(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        provider = normalize_cloud_provider(provider)
        handler_name = CLOUD_CHAT_PROVIDER_HANDLERS.get(provider)
        if handler_name is None:
            raise ValueError(f"Unsupported Cloud AI provider: {provider}")

        handler = getattr(self, handler_name)
        return handler(base_url=base_url, api_key=api_key, model=model, messages=messages)

    def _call_openai_cloud_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return self._call_openai_compatible_chat(
            base_url=cloud_provider_base_url("openai", base_url),
            api_key=api_key,
            model=model,
            messages=messages,
        )

    def _call_openrouter_cloud_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return self._call_openai_compatible_chat(
            base_url=cloud_provider_base_url("openrouter", base_url),
            api_key=api_key,
            model=model,
            messages=messages,
            extra_headers={
                "HTTP-Referer": "https://char-aiface.local",
                "X-Title": "CharAIface",
            },
        )

    def _call_anthropic_cloud_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return self._call_anthropic_chat(
            base_url=cloud_provider_base_url("anthropic", base_url),
            api_key=api_key,
            model=model,
            messages=messages,
        )

    def _call_gemini_cloud_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        return self._call_gemini_chat(
            base_url=cloud_provider_base_url("gemini", base_url),
            api_key=api_key,
            model=model,
            messages=messages,
        )

    def _call_custom_cloud_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        if not base_url.strip():
            raise ValueError("Custom Cloud AI provider requires a base_url.")
        return self._call_openai_compatible_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
        )

    def _call_openai_compatible_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.6,
            },
            timeout=CLOUD_AI_CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        content = message.get("content") or ""

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content") or ""
                    if text:
                        text_parts.append(str(text))
                elif part:
                    text_parts.append(str(part))
            return "\n".join(text_parts).strip()

        return str(content).strip()

    def _call_anthropic_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        system_prompt = ""
        anthropic_messages: list[dict[str, str]] = []

        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            if role == "system":
                system_prompt = content
                continue
            if role not in {"user", "assistant"}:
                continue
            anthropic_messages.append({"role": role, "content": content})

        response = httpx.post(
            f"{base_url.rstrip('/')}/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "system": system_prompt,
                "messages": anthropic_messages,
            },
            timeout=CLOUD_AI_CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        data = response.json()
        content_blocks = data.get("content") or []
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text") or ""
                if text:
                    text_parts.append(str(text))

        return "\n".join(text_parts).strip()

    def _call_gemini_chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        gemini_model = model.strip()
        if gemini_model.startswith("models/"):
            gemini_model = gemini_model[len("models/"):]

        system_prompt = ""
        contents: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role", "")
            content = message.get("content", "")
            if role == "system":
                system_prompt = content
                continue
            if role == "assistant":
                gemini_role = "model"
            else:
                gemini_role = "user"

            contents.append(
                {
                    "role": gemini_role,
                    "parts": [{"text": content}],
                }
            )

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.6,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
            }

        response = httpx.post(
            f"{base_url.rstrip('/')}/models/{gemini_model}:generateContent",
            params={"key": api_key},
            json=body,
            timeout=CLOUD_AI_CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return ""

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        text_parts: list[str] = []
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text") or ""
                if text:
                    text_parts.append(str(text))

        return "\n".join(text_parts).strip()

    def _build_model_messages(
        self,
        request: ChatRequest,
        character_info: dict[str, str],
        target_provider: str,
        app_language: str,
        settings: dict[str, Any] | None = None,
        web_search_context: dict[str, Any] | None = None,
        cloud_fallback_context: dict[str, Any] | None = None,
        strip_latest_file_context: bool = False,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": self._build_system_prompt(
                    request=request,
                    character_info=character_info,
                    target_provider=target_provider,
                    app_language=app_language,
                    settings=settings or {},
                    web_search_context=web_search_context,
                    cloud_fallback_context=cloud_fallback_context,
                ),
            }
        ]

        latest_user_message = self._find_latest_user_message(request)
        latest_user_message_id = id(latest_user_message) if latest_user_message is not None else None
        has_web_search_results = bool(web_search_context and web_search_context.get("used"))

        filtered_history = []
        for message in request.messages:
            if not self._should_include_history_message(message):
                continue
            # When web search was used, the final user turn is rebuilt below as a
            # search-grounded task. Keeping the raw /search or /검색 command as the
            # final user message makes many models treat it as an unsupported tool
            # request and ignore the retrieved results.
            if has_web_search_results and id(message) == latest_user_message_id:
                continue
            filtered_history.append(message)

        for message in filtered_history[-MAX_CHAT_HISTORY_MESSAGES:]:
            role = str(message.role)
            if role not in {"system", "user", "assistant"}:
                continue

            content = str(message.content).strip()
            if not content:
                continue
            if strip_latest_file_context and id(message) == latest_user_message_id:
                metadata = getattr(message, "metadata", {}) or {}
                if metadata.get("transient_file_context"):
                    original_content = str(
                        metadata.get("transient_original_user_content") or ""
                    ).strip()
                    if original_content:
                        content = original_content

            messages.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        search_task_message = self.web_search_context.build_final_user_message(
            latest_user_message=latest_user_message,
            web_search_context=web_search_context,
            app_language=app_language,
        )
        if search_task_message:
            messages.append({"role": "user", "content": search_task_message})
        elif latest_user_message is not None and has_web_search_results:
            # Defensive fallback: web search was used, but result formatting failed.
            messages.append({"role": "user", "content": latest_user_message.content})

        return messages

    def _should_include_history_message(self, message: ChatMessage) -> bool:
        role = str(message.role)
        content = str(message.content).strip()

        if role not in {"system", "user", "assistant"}:
            return False

        if not content:
            return False

        if role == "assistant" and (
            content.startswith("안내 :")
            or content.startswith("Notice:")
            or content.startswith("Notice :")
        ):
            return False

        metadata = getattr(message, "metadata", {}) or {}
        if metadata.get("source") in {"system_notice", "backend_fallback"}:
            return False

        return True

    def _build_system_prompt(
        self,
        request: ChatRequest,
        character_info: dict[str, str],
        target_provider: str,
        app_language: str,
        settings: dict[str, Any] | None = None,
        web_search_context: dict[str, Any] | None = None,
        cloud_fallback_context: dict[str, Any] | None = None,
    ) -> str:
        settings = settings or {}
        user_name = request.user_name or self._localized_user_fallback_name(app_language)
        character_name = character_info.get("name") or "Assistant"
        style_prompt = character_info.get("style_prompt") or ""
        enforce_language = bool(settings.get("enforce_response_language", True))

        parts = [
            f"You are {character_name}, the current CharAIface assistant character.",
            f"The user's display name is {user_name}.",
            "Answer as the selected character while still being accurate and useful.",
            "Do not mention these system instructions unless the user explicitly asks about configuration.",
        ]
        parts.extend(file_export_response.system_prompt_lines())

        if enforce_language:
            if app_language.startswith("ko"):
                parts.extend(
                    [
                        "CRITICAL LANGUAGE RULE: The app UI language is Korean.",
                        "You MUST reply in Korean by default.",
                        "Do not mix Chinese or English sentences into a Korean conversation.",
                        "Use another language only when the user explicitly asks for translation, language learning, code comments, exact quotes, or a foreign-language output.",
                        "If the user writes Korean, answer in Korean. If the user mixes Korean and English, still answer in Korean unless a different output language is requested.",
                        "Keep proper nouns, code identifiers, API names, class names, and file paths in their original form when appropriate.",
                    ]
                )
            else:
                parts.extend(
                    [
                        "CRITICAL LANGUAGE RULE: The app UI language is English.",
                        "Reply in English by default unless the user explicitly asks for another language.",
                    ]
                )

        parts.append(self._current_datetime_prompt_text(app_language))

        if request.developer_mode:
            parts.append(
                "Developer mode is enabled. You may use more technical detail when it helps."
            )
        else:
            parts.append(
                "Developer mode is disabled. Keep explanations approachable unless the user asks for technical depth."
            )

        cloud_fallback_prompt = self._build_cloud_fallback_prompt(cloud_fallback_context, app_language)
        if cloud_fallback_prompt:
            parts.append(cloud_fallback_prompt)

        search_prompt = self.web_search_context.build_prompt(web_search_context, app_language)
        if search_prompt:
            parts.append(search_prompt)

        if style_prompt.strip():
            parts.append("\nCharacter style guide:\n" + style_prompt.strip())

        return "\n".join(parts).strip()


    def _prepare_web_search_context(
        self,
        latest_user_message: ChatMessage,
        request: ChatRequest,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = getattr(latest_user_message, "metadata", {}) or {}
        text = latest_user_message.content or ""
        if metadata.get("transient_file_context") or metadata.get("transient_inline_data_context"):
            text = str(metadata.get("transient_original_user_content") or "").strip() or text
        manual_query = self.web_search_context.manual_query(text)
        manual_requested = manual_query is not None

        if manual_requested and not manual_query.strip():
            return {
                "fatal_response": self._create_web_search_error_response(
                    request=request,
                    error_code="web_search_query_empty",
                    error_detail="Search query is empty.",
                )
            }

        should_search = manual_requested or self.web_search_context.should_auto_search(text, settings)
        if not should_search:
            return {"used": False}

        if not bool(settings.get("web_search_enabled")):
            if manual_requested:
                return {
                    "fatal_response": self._create_web_search_error_response(
                        request=request,
                        error_code="web_search_disabled",
                        error_detail="Web search is disabled in settings.",
                    )
                }
            return {"used": False}

        raw_query = manual_query.strip() if manual_query is not None else self.web_search_context.auto_query(text)
        query, context_source = self.web_search_context.resolve_contextual_query(
            query=raw_query,
            request=request,
        )
        config = self.web_search_context.config_from_settings(settings)
        query = self.web_search_context.normalize_query_for_region(
            query=query,
            original_text=text,
            config=config,
            settings=settings,
        )

        try:
            result = self.web_search_service.search(query=query, config=config)
        except (httpx.HTTPStatusError, httpx.HTTPError, WebSearchError, Exception) as error:
            # Once a web search is explicitly requested or automatically triggered,
            # do not pass the original prompt to the model after an API failure.
            # Small local models often infer that they need to explain their lack
            # of browsing/API access, which is misleading: the application tried
            # the search tool and the provider call failed. Return a UI-level
            # failure response instead so the avatar can enter panic state and
            # developer details can stay gated behind developer mode.
            return {
                "fatal_response": self._create_web_search_error_response(
                    request=request,
                    error_code="web_search_failed",
                    error_detail=str(error),
                )
            }

        return {
            "used": True,
            "manual": manual_requested,
            "query": query,
            "raw_query": raw_query,
            "context_source": context_source,
            "provider": result.provider,
            "region_country_code": config.country_code,
            "region_location": config.location,
            "preferred_unit_system": self.web_search_context.preferred_unit_system(settings),
            "result": result,
            "result_count": len(result.results),
        }


    def _create_web_search_error_response(
        self,
        request: ChatRequest,
        error_code: str,
        error_detail: str,
    ) -> ChatResponse:
        language = self._request_language(request)
        developer_mode = bool(getattr(request, "developer_mode", False))

        if language.startswith("ko"):
            if developer_mode:
                content = (
                    "검색에 실패했습니다.\n\n"
                    f"- error_code: {error_code}\n"
                    f"- error_detail: {error_detail}"
                )
            else:
                content = "검색에 실패했습니다."
        else:
            if developer_mode:
                content = (
                    "Search failed.\n\n"
                    f"- error_code: {error_code}\n"
                    f"- error_detail: {error_detail}"
                )
            else:
                content = "Search failed."

        return self._create_assistant_response(
            content=content,
            route="command",
            model="web_search",
            paid_model_used=False,
            metadata={
                "source": "web_search",
                "error": True,
                "panic": True,
                "error_code": error_code,
                "error_detail": error_detail,
                "developer_detail_visible": developer_mode,
            },
        )

    def _cloud_fallback_context_from_response(self, response: ChatResponse) -> dict[str, Any]:
        metadata = getattr(response.message, "metadata", {}) or {}
        return {
            "used": True,
            "provider": metadata.get("provider"),
            "model": getattr(response.message, "metadata", {}).get("model") or getattr(response.message, "metadata", {}).get("selected_model"),
            "error_code": metadata.get("error_code"),
            "error_detail": metadata.get("error_detail"),
        }

    def _cloud_fallback_metadata(self, cloud_fallback_context: dict[str, Any] | None) -> dict[str, Any]:
        if not cloud_fallback_context or not cloud_fallback_context.get("used"):
            return {}
        metadata: dict[str, Any] = {
            "cloud_ai_fallback_to_local": True,
            "paid_model_unavailable": True,
        }
        if cloud_fallback_context.get("provider"):
            metadata["cloud_ai_provider"] = cloud_fallback_context.get("provider")
        if cloud_fallback_context.get("error_code"):
            metadata["cloud_ai_error_code"] = cloud_fallback_context.get("error_code")
        if cloud_fallback_context.get("error_detail"):
            metadata["cloud_ai_error_detail"] = cloud_fallback_context.get("error_detail")
        return metadata

    def _build_cloud_fallback_prompt(
        self,
        cloud_fallback_context: dict[str, Any] | None,
        language: str,
    ) -> str:
        if not cloud_fallback_context or not cloud_fallback_context.get("used"):
            return ""

        if language.startswith("ko"):
            return (
                "Cloud/Paid model fallback instruction:\n"
                "The originally selected paid/cloud model could not be used for this turn. "
                "You are the local model continuing the user's original request. "
                "Begin your next answer with a short, natural character-style notice similar to "
                "'유료모델을 사용할 수 없는 것 같지만, 짧게나마 생각해볼게요.' "
                "Then answer the user's actual request as well as you can. "
                "Do not explain API authentication, provider permissions, security policy, or system limitations unless the user explicitly asks for /cloudaistatus or technical details."
            )

        return (
            "Cloud/Paid model fallback instruction:\n"
            "The originally selected paid/cloud model could not be used for this turn. "
            "You are the local model continuing the user's original request. "
            "Begin your next answer with a short, natural notice such as "
            "'The paid model seems unavailable, but I'll think through it briefly.' "
            "Then answer the user's actual request as well as you can. "
            "Do not explain API authentication, provider permissions, security policy, or system limitations unless the user explicitly asks for /cloudaistatus or technical details."
        )

    def _build_cloud_ai_status(self, settings: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(settings.get("cloud_ai_enabled"))
        provider = str(settings.get("cloud_ai_provider") or "none").strip().lower()
        model = str(settings.get("cloud_model") or "").strip()
        base_url = str(settings.get("cloud_ai_base_url") or "").strip()
        auth_mode = str(settings.get("cloud_ai_auth_mode") or "secure_store").strip()
        credential_id = str(settings.get("cloud_ai_credential_id") or "").strip()
        api_key_env = str(settings.get("cloud_ai_api_key_env") or "").strip() or None

        if not enabled:
            return {
                "configured": False,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "disabled",
                "error_code": "cloud_ai_disabled",
                "error_detail": "Cloud AI is disabled in settings.",
            }

        if not provider or provider == "none" or not model:
            return {
                "configured": False,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "not_configured",
                "error_code": "cloud_ai_not_configured",
                "error_detail": "Cloud AI provider or model is not configured.",
            }

        credential_config = CloudCredentialConfig(
            provider=provider,
            auth_mode=auth_mode,
            credential_id=credential_id,
            api_key_env=api_key_env,
        )

        try:
            api_key = CloudAuthManager.get_api_key(credential_config)
        except Exception as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "credential_error",
                "error_code": "cloud_ai_credential_error",
                "error_detail": str(error),
            }

        if not api_key:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "missing_api_key",
                "error_code": "cloud_ai_api_key_missing",
                "error_detail": "Cloud AI API key was not found.",
            }

        try:
            self._probe_cloud_ai_provider(provider=provider, base_url=base_url, api_key=api_key)
        except httpx.HTTPStatusError as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "http_error",
                "error_code": "cloud_ai_http_error",
                "http_status": error.response.status_code,
                "error_detail": self._safe_response_text(error.response),
            }
        except httpx.HTTPError as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "request_failed",
                "error_code": "cloud_ai_request_failed",
                "error_detail": str(error),
            }
        except Exception as error:
            return {
                "configured": True,
                "available": False,
                "provider": provider,
                "model": model,
                "state": "error",
                "error_code": "cloud_ai_unknown_error",
                "error_detail": str(error),
            }

        return {
            "configured": True,
            "available": True,
            "provider": provider,
            "model": model,
            "state": "ready",
            "error_code": None,
            "error_detail": None,
        }

    def _probe_cloud_ai_provider(self, provider: str, base_url: str, api_key: str) -> None:
        provider = normalize_cloud_provider(provider)
        handler_name = CLOUD_PROVIDER_PROBE_HANDLERS.get(provider)
        if handler_name is None:
            raise ValueError(f"Unsupported cloud AI provider: {provider}")
        getattr(self, handler_name)(base_url=base_url, api_key=api_key)

    def _probe_openai_provider(self, base_url: str, api_key: str) -> None:
        url = cloud_provider_base_url("openai", base_url).rstrip("/")
        response = httpx.get(f"{url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=5.0)
        response.raise_for_status()

    def _probe_openrouter_provider(self, base_url: str, api_key: str) -> None:
        url = cloud_provider_base_url("openrouter", base_url).rstrip("/")
        response = httpx.get(f"{url}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=5.0)
        response.raise_for_status()

    def _probe_anthropic_provider(self, base_url: str, api_key: str) -> None:
        url = cloud_provider_base_url("anthropic", base_url).rstrip("/")
        response = httpx.get(
            f"{url}/models",
            headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
            timeout=5.0,
        )
        response.raise_for_status()

    def _probe_gemini_provider(self, base_url: str, api_key: str) -> None:
        url = cloud_provider_base_url("gemini", base_url).rstrip("/")
        response = httpx.get(f"{url}/models", params={"key": api_key}, timeout=5.0)
        response.raise_for_status()

    def _create_cloud_ai_status_response(self, request: ChatRequest) -> ChatResponse:
        settings = self._effective_settings(request)
        status = self._build_cloud_ai_status(settings)
        language = self._request_language(request, settings)
        is_korean = language.startswith("ko")
        developer_mode = bool(getattr(request, "developer_mode", False))

        if is_korean:
            lines = [
                "Cloud AI Status",
                "",
                f"- 사용 가능: {bool(status.get('available'))}",
                f"- 설정됨: {bool(status.get('configured'))}",
                f"- provider: {status.get('provider') or 'none'}",
                f"- model: {status.get('model') or 'not selected'}",
                f"- state: {status.get('state') or 'unknown'}",
                f"- error_code: {status.get('error_code') or 'none'}",
            ]
            if status.get("http_status"):
                lines.append(f"- http_status: {status.get('http_status')}")
            if status.get("error_detail") and developer_mode:
                lines.append(f"- error_detail: {status.get('error_detail')}")
        else:
            lines = [
                "Cloud AI Status",
                "",
                f"- available: {bool(status.get('available'))}",
                f"- configured: {bool(status.get('configured'))}",
                f"- provider: {status.get('provider') or 'none'}",
                f"- model: {status.get('model') or 'not selected'}",
                f"- state: {status.get('state') or 'unknown'}",
                f"- error_code: {status.get('error_code') or 'none'}",
            ]
            if status.get("http_status"):
                lines.append(f"- http_status: {status.get('http_status')}")
            if status.get("error_detail") and developer_mode:
                lines.append(f"- error_detail: {status.get('error_detail')}")

        return self._create_assistant_response(
            content="\n".join(lines),
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "cloudaistatus",
                "cloud_ai_status": status,
            },
        )

    def _current_datetime_prompt_text(self, language: str) -> str:
        now = datetime.now().astimezone()
        timezone_name = now.tzname() or "local time"

        display_text = now.strftime("%Y-%m-%d %H:%M:%S")
        iso_text = now.isoformat(timespec="seconds")

        if language == "ko":
            return (
                f"현재 시스템 날짜/시간: {display_text} "
                f"({timezone_name}, ISO: {iso_text}).\n"
                "사용자가 오늘, 지금, 내일, 이번 주, 최근 날짜, 일정, 시간 관련 맥락을 물어보면 "
                "위의 현재 시스템 날짜/시간을 기준으로 답하세요.\n"
                "단, 제공된 현재 시간만으로 알 수 없는 실시간 외부 정보가 필요한 경우에는 "
                "그 한계를 명확히 말하세요."
            )

        return (
            f"Current system date/time: {display_text} "
            f"({timezone_name}, ISO: {iso_text}).\n"
            "Use the current date/time above when the user asks about today, now, "
            "tomorrow, this week, recent relative dates, schedules, or time-sensitive context.\n"
            "If the question requires external real-time information beyond this timestamp, "
            "clearly state that limitation."
        )

    def _character_pack_roots(self) -> list[Path]:
        candidates = [
            self.project_root / "resources" / "builtin" / "characters",
            self.project_root / "resources" / "characters",
            self.project_root / "resources" / "character",
            self.project_root / "resource" / "characters",
            self.project_root / "resource" / "character",
        ]

        roots: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            if resolved in seen:
                continue
            if candidate.exists():
                roots.append(candidate)
                seen.add(resolved)

        return roots

    def _load_character_info(
        self,
        character_id: str | None,
        app_language: str | None = None,
        target_provider: str = "",
        settings: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        default_info = {
            "id": character_id or "unknown",
            "name": "Assistant",
            "style_prompt": "",
        }

        if not character_id:
            return default_info

        for root in self._character_pack_roots():
            if not root.exists():
                continue

            candidate_dirs: list[Path] = []
            if (root / "manifest.json").exists():
                candidate_dirs.append(root)

            candidate_dirs.extend(
                pack_dir
                for pack_dir in sorted(root.iterdir())
                if pack_dir.is_dir()
            )

            for pack_dir in candidate_dirs:
                manifest_path = pack_dir / "manifest.json"
                if not manifest_path.exists():
                    continue

                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                if str(manifest.get("id", "")) != character_id:
                    continue

                style_prompt = self._read_character_style_prompt(
                    pack_dir=pack_dir,
                    manifest=manifest,
                    app_language=app_language or "",
                    target_provider=target_provider,
                    settings=settings or {},
                )

                return {
                    "id": character_id,
                    "name": str(manifest.get("name") or character_id),
                    "style_prompt": style_prompt,
                }

        return default_info

    def _read_character_style_prompt(
        self,
        pack_dir: Path,
        manifest: dict[str, Any],
        app_language: str,
        target_provider: str = "",
        settings: dict[str, Any] | None = None,
    ) -> str:
        settings = settings or {}
        # When character style emphasis is off, prefer style.short*.md if present.
        # When it is on, use the full style guide for stronger character behavior.
        use_short_style = not bool(settings.get("emphasize_character_style", True))

        short_prompt = self._read_character_style_prompt_variant(
            pack_dir=pack_dir,
            manifest=manifest,
            app_language=app_language,
            variant="short",
        )

        if use_short_style and short_prompt.strip():
            return short_prompt.strip()

        full_prompt = self._read_character_style_prompt_variant(
            pack_dir=pack_dir,
            manifest=manifest,
            app_language=app_language,
            variant="full",
        )

        if full_prompt.strip():
            return full_prompt.strip()

        return short_prompt.strip()

    def _read_character_style_prompt_variant(
        self,
        pack_dir: Path,
        manifest: dict[str, Any],
        app_language: str,
        variant: str,
    ) -> str:
        prompts: list[str] = []
        loaded_paths: set[Path] = set()

        def append_style_file(path: Path) -> None:
            resolved_path = path.resolve()
            if resolved_path in loaded_paths or not path.exists():
                return
            try:
                text = path.read_text(encoding="utf-8").strip()
            except Exception:
                return
            if text:
                prompts.append(text)
                loaded_paths.add(resolved_path)

        normalized_language = (app_language or "").strip().lower()
        is_korean = normalized_language.startswith("ko")

        if variant == "short":
            base_manifest_keys = ["style_short_file", "style_file_short", "short_style_file"]
            base_fallback_names = [
                "style.short.md",
                "style_short.md",
                "style.local.md",
                "style_local.md",
                "short.md",
            ]
            if is_korean:
                language_keys = ["ko", "ko-kr", "korean"]
                localized_manifest_keys = [
                    "style_short_file_ko",
                    "style_file_short_ko",
                    "short_style_file_ko",
                    "style_short_file_korean",
                ]
                localized_fallback_names = [
                    "style.short.ko.md",
                    "style.ko.short.md",
                    "style_short_ko.md",
                    "style.local.ko.md",
                    "style_ko_local.md",
                    "short.ko.md",
                ]
            else:
                language_keys = ["en", "en-us", "english"]
                localized_manifest_keys = [
                    "style_short_file_en",
                    "style_file_short_en",
                    "short_style_file_en",
                    "style_short_file_english",
                ]
                localized_fallback_names = [
                    "style.short.en.md",
                    "style.en.short.md",
                    "style_short_en.md",
                    "style.local.en.md",
                    "short.en.md",
                ]

            localized_map_names = [
                "localized_short_style_files",
                "short_style_files",
                "localized_style_short_files",
            ]

        else:
            base_manifest_keys = ["style_file"]
            base_fallback_names = ["style.md"]
            if is_korean:
                language_keys = ["ko", "ko-kr", "korean"]
                localized_manifest_keys = ["style_file_ko", "style_file_korean"]
                localized_fallback_names = ["style.ko.md", "style_ko.md", "style.korean.md"]
            else:
                language_keys = ["en", "en-us", "english"]
                localized_manifest_keys = ["style_file_en", "style_file_english"]
                localized_fallback_names = ["style.en.md", "style_en.md", "style.english.md"]

            localized_map_names = ["localized_style_files", "style_files"]

        for key in base_manifest_keys:
            value = manifest.get(key)
            if value:
                append_style_file(pack_dir / str(value))

        if not prompts:
            for fallback_name in base_fallback_names:
                append_style_file(pack_dir / fallback_name)

        for map_name in localized_map_names:
            localized_style_files = manifest.get(map_name) or {}
            if isinstance(localized_style_files, dict):
                for key in language_keys:
                    value = localized_style_files.get(key)
                    if value:
                        append_style_file(pack_dir / str(value))

        for key in localized_manifest_keys:
            value = manifest.get(key)
            if value:
                append_style_file(pack_dir / str(value))

        for fallback_name in localized_fallback_names:
            append_style_file(pack_dir / fallback_name)

        return "\n\n".join(prompts).strip()

    def _load_settings(self) -> dict[str, Any]:
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _effective_settings(self, request: ChatRequest | None = None) -> dict[str, Any]:
        """Return file settings overlaid with the desktop request snapshot.

        The desktop UI persists settings to resources/data/settings.json, but the
        backend can be running as a separate process and may see an older file or
        a file that predates newly added fields.  The request snapshot is the
        current in-memory AppSettings from the desktop process, so it should win
        over the file for chat-time behavior such as web search options.
        """
        settings = self._load_settings()
        snapshot = getattr(request, "settings_snapshot", None) if request is not None else None
        if isinstance(snapshot, dict):
            for key, value in snapshot.items():
                settings[key] = value
        return settings

    def _request_language(
        self,
        request: ChatRequest,
        settings: dict[str, Any] | None = None,
    ) -> str:
        request_language = str(getattr(request, "language", "") or "").strip().lower()
        if request_language:
            return request_language

        settings = settings or self._effective_settings(request)
        settings_language = str(settings.get("language") or "").strip().lower()
        if settings_language:
            return settings_language

        return "ko"

    def _localized_text(self, key: str, language: str, **kwargs) -> str:
        language_key = "ko" if str(language or "").lower().startswith("ko") else "en"
        previous_language = self.localization.current_language
        try:
            self.localization.set_language(language_key)
            return self.localization.t(key, **kwargs)
        finally:
            self.localization.set_language(previous_language)

    def _localized_user_fallback_name(self, language: str) -> str:
        if language.startswith("ko"):
            return "사용자"
        return "User"

    def _localized_backend_message(self, request: ChatRequest, ko: str, en: str) -> str:
        language = self._request_language(request)
        if language.startswith("ko"):
            return ko
        return en

    def _create_status_response(self, request: ChatRequest) -> ChatResponse:
        settings = self._effective_settings(request)
        user_name = request.user_name or self._localized_user_fallback_name(
            self._request_language(request, settings)
        )
        character_id = request.character_id or "unknown"
        route = self._select_route(request, settings)

        if route == "cloud_ai":
            model = str(settings.get("cloud_model") or "")
            paid_model_used = True
        else:
            model = str(settings.get("local_model") or DEFAULT_LOCAL_MODEL)
            paid_model_used = False

        content = (
            "Status\n\n"
            f"- user_name: {user_name}\n"
            f"- character_id: {character_id}\n"
            f"- developer_mode: {request.developer_mode}\n"
            f"- language: {self._request_language(request, settings)}\n"
            f"- message_count: {len(request.messages)}\n"
            f"- ai_route_policy: {self._route_policy(settings)}\n"
            f"- cloud_ai_usage_weight_percent: {self._cloud_ai_usage_weight(settings)}\n"
            f"- selected_route: {route}\n"
            f"- selected_model: {model}\n"
            f"- paid_model_used: {paid_model_used}\n"
            f"- cloud_ai_available: {self._build_cloud_ai_status(settings).get('available')}\n"
            f"- backend_memory: {self._format_mb(self.system_status_service.build_payload(sample_seconds=0.0).get('process', {}).get('memory_rss_mb'))}"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "status",
                "ai_route_policy": self._route_policy(settings),
                "cloud_ai_usage_weight_percent": self._cloud_ai_usage_weight(settings),
                "selected_route": route,
                "selected_model": model,
                "selected_paid_model_used": paid_model_used,
            },
        )

    def _create_help_response(self) -> ChatResponse:
        content = (
            "Help\n\n"
            "Available commands:\n"
            "- /help: Show this command list.\n"
            "- /clear: Clear only the visible chat messages. The current ChatSession data is kept.\n"
            "- /status: Show current user, character, route, model, language, session state, and backend memory summary.\n"
            "- /health: Show backend, local AI, cloud AI, and overall AI health.\n"
            "- /systemstatus: Show backend process CPU and memory usage.\n"
            "- /cloudaistatus: Show cloud AI availability and the reason if unavailable.\n"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "help",
            },
        )


    def _create_system_status_response(self) -> ChatResponse:
        payload = self.system_status_service.build_payload(sample_seconds=0.2)
        process = payload.get("process", {})
        content = (
            "System Status\n\n"
            "Backend process:\n"
            f"- pid: {process.get('pid', 'unknown')}\n"
            f"- process: {process.get('process_name', 'unknown')}\n"
            f"- memory_rss: {self._format_mb(process.get('memory_rss_mb'))}\n"
            f"- memory_peak_rss: {self._format_mb(process.get('memory_peak_rss_mb'))}\n"
            f"- cpu_usage: {self._format_percent(process.get('cpu_percent'))}\n"
            f"- cpu_sample_seconds: {process.get('cpu_sample_seconds', 'unknown')}\n"
            f"- threads: {process.get('thread_count', 'unknown')}\n"
            f"- uptime_seconds: {process.get('uptime_seconds', 'unknown')}"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "systemstatus",
                "system_status": payload,
            },
        )

    def _format_mb(self, value) -> str:
        if value is None:
            return "unknown"
        try:
            return f"{float(value):.1f} MB"
        except (TypeError, ValueError):
            return str(value)

    def _format_percent(self, value) -> str:
        if value is None:
            return "unknown"
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return str(value)

    def _create_health_response(self) -> ChatResponse:
        health = self.health_service.build_payload()
        status = health.get("status", "error")
        errors = health.get("errors", [])

        content = (
            f"Health: {status}\n\n"
            f"- backend_api: {health.get('backend_api')}\n"
            f"- chat_api: {health.get('chat_api')}\n"
            f"- chat_service: {health.get('chat_service')}\n"
            f"- local_ai_available: {health.get('checks', {}).get('local_ai_available')}\n"
            f"- cloud_ai_available: {health.get('checks', {}).get('cloud_ai_available')}\n"
            f"- ai_available: {health.get('checks', {}).get('ai_available')}\n"
            f"- errors: {errors}\n"
            f"- server_time_utc: {health.get('server_time_utc')}"
        )

        return self._create_assistant_response(
            content=content,
            route="command",
            model="system_command",
            paid_model_used=False,
            metadata={
                "source": "chat_service",
                "command": "health",
                "health": health,
            },
        )

    def _create_local_error_response(
        self,
        request: ChatRequest,
        model: str,
        error_code: str,
        error_detail: str,
    ) -> ChatResponse:
        language = self._request_language(request)
        is_korean = language.startswith("ko")

        if not request.developer_mode:
            if error_code == "model_timeout":
                content = self._localized_text("local_ai.error.model_timeout", language)
            else:
                content = self._localized_text("local_ai.error.response_failed", language)
        elif is_korean:
            content = (
                f"{self._localized_text('local_ai.error.response_failed', language)}\n\n"
                f"- model: {model}\n"
                f"- error_code: {error_code}\n"
                f"- error_detail: {error_detail}"
            )
        else:
            content = (
                f"{self._localized_text('local_ai.error.response_failed', language)}\n\n"
                f"- model: {model}\n"
                f"- error_code: {error_code}\n"
                f"- error_detail: {error_detail}"
            )

        return self._create_assistant_response(
            content=content,
            route="local_error",
            model=model,
            paid_model_used=False,
            metadata={
                "source": "ollama",
                "error": True,
                "error_code": error_code,
                "error_detail": error_detail,
            },
        )

    def _create_cloud_error_response(
        self,
        request: ChatRequest,
        model: str,
        provider: str,
        error_code: str,
        error_detail: str,
    ) -> ChatResponse:
        paid_model_unavailable = bool(model and provider != "none" and error_code != "model_timeout")
        language = self._request_language(request)
        is_korean = language.startswith("ko")

        if paid_model_unavailable and not request.developer_mode:
            title = self._localized_text("cloud_ai.error.paid_model_unavailable", language)
            provider_message = self._extract_provider_error_message(error_detail)
            display_message = self._translate_provider_error_message(
                provider_message or error_detail,
                language=language,
            )

            if display_message:
                label = self._localized_text("common.message_label", language)
                content = f"{title}\n\n- {label}: {display_message}"
            else:
                content = title

        elif error_code == "model_timeout" and not request.developer_mode:
            content = self._localized_text("cloud_ai.error.model_timeout", language)

        elif is_korean:
            title = (
                self._localized_text("cloud_ai.error.paid_model_unavailable", language)
                if paid_model_unavailable
                else self._localized_text("cloud_ai.error.response_failed", language)
            )
            content = (
                f"{title}\n\n"
                f"- provider: {provider}\n"
                f"- model: {model}\n"
                f"- error_code: {error_code}\n"
                f"- error_detail: {error_detail}"
            )
        else:
            title = (
                self._localized_text("cloud_ai.error.paid_model_unavailable", language)
                if paid_model_unavailable
                else self._localized_text("cloud_ai.error.response_failed", language)
            )
            content = (
                f"{title}\n\n"
                f"- provider: {provider}\n"
                f"- model: {model}\n"
                f"- error_code: {error_code}\n"
                f"- error_detail: {error_detail}"
            )

        return self._create_assistant_response(
            content=content,
            route="cloud_error",
            model=model,
            paid_model_used=False,
            metadata={
                "source": "cloud_ai",
                "provider": provider,
                "error": True,
                "error_code": error_code,
                "error_detail": error_detail,
                "paid_model_unavailable": paid_model_unavailable,
            },
        )

    def _render_markdown_requested(self, latest_user_message: ChatMessage | None) -> bool:
        if latest_user_message is None:
            return False

        metadata = latest_user_message.metadata or {}
        return bool(metadata.get("render_markdown"))

    def _create_assistant_response(
        self,
        content: str,
        route: ChatRoute,
        model: str,
        paid_model_used: bool,
        metadata: dict | None = None,
    ) -> ChatResponse:
        response_metadata = {
            "route": route,
            "model": model,
            "paid_model_used": paid_model_used,
        }

        if metadata:
            response_metadata.update(metadata)

        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content=content,
                metadata=response_metadata,
            )
        )


    def _extract_provider_error_message(self, error_detail: str) -> str:
        text = str(error_detail or "").strip()
        if not text:
            return ""

        candidates = [text]
        if ":" in text:
            candidates.append(text.split(":", 1)[1].strip())

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except (TypeError, ValueError):
                continue

            message = self._find_message_in_error_payload(data)
            if message:
                return message

        if len(text) > 300:
            return text[:300] + "..."
        return text

    def _find_message_in_error_payload(self, payload: Any) -> str:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
            elif isinstance(error, str) and error.strip():
                return error.strip()

            message = payload.get("message") or payload.get("detail")
            if isinstance(message, str) and message.strip():
                return message.strip()

            for value in payload.values():
                nested = self._find_message_in_error_payload(value)
                if nested:
                    return nested

        if isinstance(payload, list):
            for item in payload:
                nested = self._find_message_in_error_payload(item)
                if nested:
                    return nested

        return ""

    def _translate_provider_error_message(self, message: str, language: str) -> str:
        text = str(message or "").strip()
        if not text:
            return ""

        if not language.startswith("ko"):
            return text

        lowered = text.lower()
        if "api key" in lowered and ("missing" in lowered or "not found" in lowered):
            return "Cloud AI API Key를 찾을 수 없습니다. 설정에서 API Key 저장 상태를 확인하세요."
        if "incorrect api key" in lowered or "invalid api key" in lowered:
            return "Cloud AI API Key가 올바르지 않습니다. 새 Key를 저장한 뒤 다시 시도하세요."
        if "insufficient_quota" in lowered or "quota" in lowered:
            return "Cloud AI 사용량 한도 또는 결제 한도에 도달했습니다."
        if "rate limit" in lowered or "too many requests" in lowered:
            return "Cloud AI 요청이 너무 많아 제한되었습니다. 잠시 후 다시 시도하세요."
        if "model" in lowered and ("not found" in lowered or "does not exist" in lowered):
            return "선택한 Cloud AI 모델을 찾을 수 없습니다. 모델 목록을 새로고침한 뒤 다시 선택하세요."
        if "billing" in lowered or "payment" in lowered or "credit" in lowered:
            return "Cloud AI 결제, 크레딧, 또는 과금 설정 확인이 필요합니다."
        if "timeout" in lowered or "timed out" in lowered:
            return "Cloud AI 요청 시간이 초과되었습니다. 네트워크 상태나 Provider 상태를 확인하세요."

        return text

    def _safe_response_text(self, response: httpx.Response) -> str:
        try:
            text = response.text.strip()
        except Exception:
            return ""

        if len(text) > 800:
            return text[:800] + "..."

        return text
