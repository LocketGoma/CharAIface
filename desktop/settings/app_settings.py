import locale
import os
from typing import Literal

from pydantic import BaseModel, Field

from desktop.core.frontend_helper import (
    default_web_search_api_key_env,
    default_web_search_credential_id,
)
from shared.addons import FILE_IMPORT_EXPORT_ADDON_ID


LocalAIProvider = Literal["ollama"]
RuntimeInstallPolicy = Literal["never", "ask"]
ModelInstallPolicy = Literal["never", "ask", "auto"]
AIRoutePolicy = Literal["local_only", "cloud_only", "local_first", "cloud_first", "auto"]
CloseButtonBehavior = Literal["exit", "minimize_to_tray"]
CloudAIAuthMode = Literal["secure_store", "env_var"]
WebSearchAuthMode = Literal["secure_store", "env_var"]
WebSearchProvider = Literal["none", "tavily", "firecrawl"]
DEFAULT_WEB_SEARCH_PROVIDER: WebSearchProvider = "tavily"
UserCountryPreset = Literal["auto_language", "kr", "jp", "us", "eu", "custom", "ip_auto"]
PreferredUnitSystem = Literal["metric", "imperial"]
CloudAIProvider = Literal[
    "none",
    "openai",
    "openrouter",
    "anthropic",
    "gemini",
    "custom",
]


def default_language_from_system() -> str:
    language = ""

    try:
        language = locale.getlocale()[0] or ""
    except Exception:
        language = ""

    if not language:
        language = (
            os.environ.get("LANG")
            or os.environ.get("LANGUAGE")
            or os.environ.get("LC_ALL")
            or os.environ.get("LC_MESSAGES")
            or ""
        )

    return "ko" if language.lower().startswith("ko") else "en"


class AppSettings(BaseModel):
    setup_wizard_completed: bool = False

    language: str = Field(default_factory=default_language_from_system)
    fallback_language: str = "en"

    # User country / search locale settings
    # auto_language: Korean UI => KR, English UI => US.
    # ip_auto stores the latest detected public-IP country in user_country_code/location.
    user_country_preset: UserCountryPreset = "auto_language"
    user_country_code: str = "KR"
    user_country_location: str = "South Korea"
    preferred_unit_system: PreferredUnitSystem = "metric"

    theme_id: str = "light"
    chat_font_family: str = "맑은 고딕"
    chat_font_size: int = 10

    selected_character_id: str = "default_sakura"
    user_name: str = "익명의 선생님"

    developer_mode: bool = False
    enable_tray_icon: bool = True
    close_button_behavior: CloseButtonBehavior = "minimize_to_tray"

    conversation_markdown_enabled: bool = True
    typewriter_interval_ms: int = 30
    enforce_response_language: bool = True
    emphasize_character_style: bool = True

    expand_chat_over_character_area: bool = True
    avatar_occluded_opacity: float = 0.3
    enable_avatar_embarrassed_when_occluded: bool = True

    # Add-on module state. Builtin modules use default values when absent; these
    # dictionaries persist user overrides and per-module settings.
    enabled_addons: dict[str, bool] = Field(
        default_factory=lambda: {FILE_IMPORT_EXPORT_ADDON_ID: True}
    )
    addon_settings: dict[str, dict[str, object]] = Field(default_factory=dict)

    # Local AI runtime
    local_ai_provider: LocalAIProvider = "ollama"
    local_ai_base_url: str = "http://127.0.0.1:11434"
    auto_start_local_ai_server: bool = True

    # never: 설치 시도 안 함
    # ask: 사용자 확인 후 설치 시도
    runtime_install_policy: RuntimeInstallPolicy = "ask"

    # Local model names
    local_model: str = "qwen2.5:3b"
    style_model: str = "qwen2.5:3b"

    # AI routing
    ai_route_policy: AIRoutePolicy = "auto"
    # 0: strongly prefer local AI, 100: strongly prefer cloud AI when available.
    cloud_ai_usage_weight_percent: int = 50

    # Cloud AI routing / API settings
    cloud_ai_enabled: bool = False
    cloud_ai_provider: CloudAIProvider = "openai"
    # Usually hidden in UI. Used only for custom or explicit advanced provider routing.
    cloud_ai_base_url: str = ""
    cloud_ai_auth_mode: CloudAIAuthMode = "secure_store"
    cloud_ai_credential_id: str = "CharAIface/openai/api_key"
    cloud_ai_api_key_env: str = "OPENAI_API_KEY"
    cloud_model: str = ""
    cloud_ai_models: list[str] = Field(
        default_factory=lambda: [
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-5.1-mini",
            "gpt-5.1",
        ]
    )

    # never: 모델 다운로드 안 함
    # ask: 사용자 확인 후 다운로드
    # auto: 사용자 확인 없이 다운로드
    model_install_policy: ModelInstallPolicy = "ask"

    warn_large_local_model: bool = True
    model_download_timeout_seconds: int = 600

    # Local model update settings
    # If true, the application will periodically check for updates to the installed
    # local AI model. The interval is specified in days and must be between 1
    # and 60. When an update is detected, the user will be prompted before
    # downloading and applying the new model. The last known digest and last
    # checked timestamp are persisted to avoid repeated prompts.
    local_model_update_check_enabled: bool = False
    local_model_update_check_interval_days: int = 7
    local_model_update_last_checked_at: str = ""
    local_model_update_last_known_digest: str = ""

    # Web search / local AI tool settings
    web_search_enabled: bool = False
    web_search_auto_enabled: bool = False
    web_search_provider: WebSearchProvider = DEFAULT_WEB_SEARCH_PROVIDER
    web_search_auth_mode: WebSearchAuthMode = "secure_store"
    web_search_credential_id: str = Field(
        default_factory=lambda data: default_web_search_credential_id(
            str(data.get("web_search_provider") or DEFAULT_WEB_SEARCH_PROVIDER)
        )
    )
    web_search_api_key_env: str = Field(
        default_factory=lambda data: default_web_search_api_key_env(
            str(data.get("web_search_provider") or DEFAULT_WEB_SEARCH_PROVIDER)
        )
    )
    web_search_base_url: str = ""
    web_search_max_results: int = 5
    web_search_timeout_seconds: int = 20

    window_width: int = 980
    window_height: int = 720

    extra: dict[str, object] = Field(default_factory=dict)
