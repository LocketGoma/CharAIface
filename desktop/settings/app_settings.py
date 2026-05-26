from typing import Literal

from pydantic import BaseModel, Field


LocalAIProvider = Literal["ollama"]
RuntimeInstallPolicy = Literal["never", "ask"]
ModelInstallPolicy = Literal["never", "ask", "auto"]
AIRoutePolicy = Literal["local_only", "cloud_only", "local_first", "cloud_first", "auto"]
CloudAIAuthMode = Literal["secure_store", "env_var"]
CloudAIProvider = Literal[
    "none",
    "openai",
    "openrouter",
    "anthropic",
    "gemini",
    "custom",
]


class AppSettings(BaseModel):
    language: str = "ko"
    fallback_language: str = "en"

    theme_id: str = "light"

    selected_character_id: str = "default_sakura"
    user_name: str = "익명의 선생님"

    developer_mode: bool = False

    conversation_markdown_enabled: bool = True
    enforce_response_language: bool = True
    emphasize_character_style: bool = True

    expand_chat_over_character_area: bool = True
    avatar_occluded_opacity: float = 0.3
    enable_avatar_embarrassed_when_occluded: bool = True

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

    window_width: int = 980
    window_height: int = 720

    extra: dict[str, object] = Field(default_factory=dict)
