from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    language: str = "ko"
    fallback_language: str = "en"

    theme_id: str = "light"

    selected_character_id: str = "default_sakura"
    user_name: str = "익명의 선생님"

    developer_mode: bool = False

    expand_chat_over_character_area: bool = True
    avatar_occluded_opacity: float = 0.7
    enable_avatar_embarrassed_when_occluded: bool = True

    local_model: str = "llama3.2:1b"
    style_model: str = "llama3.2:1b"
    cloud_model: str = "openai/gpt-5.1"

    auto_download_models: bool = True
    ask_before_model_download: bool = True
    warn_large_local_model: bool = True

    window_width: int = 980
    window_height: int = 720

    extra: dict[str, object] = Field(default_factory=dict)