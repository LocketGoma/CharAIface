import json
from pathlib import Path

from pydantic import ValidationError

from desktop.core.frontend_helper import (
    KNOWN_WEB_SEARCH_PROVIDER_IDS,
    default_cloud_api_key_env,
    default_cloud_base_url,
    default_cloud_credential_id,
    default_cloud_models,
    default_web_search_api_key_env,
    default_web_search_credential_id,
    guess_cloud_ai_provider,
    normalize_provider,
)
from desktop.settings.app_settings import AppSettings


class SettingsRepository:
    def __init__(self, settings_path: str | Path) -> None:
        self.settings_path = Path(settings_path)

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            settings = AppSettings()
            self.save(settings)
            return settings

        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            data = self._migrate_settings_data(data)

            settings = AppSettings(**data)
            self.save(settings)
            return settings

        except (json.JSONDecodeError, ValidationError) as error:
            print(f"[Settings] Failed to load settings: {error}")
            print("[Settings] Falling back to default settings.")

            settings = AppSettings()
            self.save(settings)
            return settings

    def save(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)

        text = settings.model_dump_json(indent=2)
        self.settings_path.write_text(text, encoding="utf-8")

    def _migrate_settings_data(self, data: dict) -> dict:
        migrated = dict(data)

        if "model_install_policy" not in migrated:
            auto_download = bool(migrated.pop("auto_download_models", True))
            ask_before_download = bool(
                migrated.pop("ask_before_model_download", True)
            )

            if not auto_download:
                migrated["model_install_policy"] = "never"
            elif ask_before_download:
                migrated["model_install_policy"] = "ask"
            else:
                migrated["model_install_policy"] = "auto"

        migrated.pop("auto_download_models", None)
        migrated.pop("ask_before_model_download", None)

        if "language" not in migrated:
            migrated["language"] = AppSettings().language
        self._migrate_user_country_settings(migrated)
        preferred_unit_system = str(
            migrated.get("preferred_unit_system", AppSettings().preferred_unit_system)
        ).strip().lower()
        if preferred_unit_system not in {"metric", "imperial"}:
            preferred_unit_system = AppSettings().preferred_unit_system
        migrated["preferred_unit_system"] = preferred_unit_system

        if "runtime_install_policy" not in migrated:
            migrated["runtime_install_policy"] = "ask"

        migrated["enable_tray_icon"] = bool(
            migrated.get("enable_tray_icon", AppSettings().enable_tray_icon)
        )

        close_behavior = str(
            migrated.get("close_button_behavior", AppSettings().close_button_behavior)
        ).strip().lower()
        if close_behavior not in {"exit", "minimize_to_tray"}:
            close_behavior = AppSettings().close_button_behavior
        migrated["close_button_behavior"] = close_behavior

        if "local_ai_provider" not in migrated:
            migrated["local_ai_provider"] = "ollama"

        if "local_ai_base_url" not in migrated:
            migrated["local_ai_base_url"] = "http://127.0.0.1:11434"

        if "auto_start_local_ai_server" not in migrated:
            migrated["auto_start_local_ai_server"] = True

        # Migrate the old lightweight test default to the new practical Korean-capable default.
        # This only affects missing values or the previous built-in default, not custom user choices.
        if "local_model" not in migrated or str(migrated.get("local_model", "")).strip() == "llama3.2:1b":
            migrated["local_model"] = AppSettings().local_model

        if "style_model" not in migrated or str(migrated.get("style_model", "")).strip() == "llama3.2:1b":
            migrated["style_model"] = migrated.get("local_model", AppSettings().style_model)

        if "model_download_timeout_seconds" not in migrated:
            migrated["model_download_timeout_seconds"] = 600

        # Local model update settings were introduced in a later version. Set default
        # values when they are missing to avoid KeyError during application startup.
        if "local_model_update_check_enabled" not in migrated:
            migrated["local_model_update_check_enabled"] = False
        if "local_model_update_check_interval_days" not in migrated:
            migrated["local_model_update_check_interval_days"] = 7
        if "local_model_update_last_checked_at" not in migrated:
            migrated["local_model_update_last_checked_at"] = ""
        if "local_model_update_last_known_digest" not in migrated:
            migrated["local_model_update_last_known_digest"] = ""

        if "ai_route_policy" not in migrated:
            migrated["ai_route_policy"] = "auto"

        try:
            cloud_weight = int(migrated.get("cloud_ai_usage_weight_percent", AppSettings().cloud_ai_usage_weight_percent))
        except (TypeError, ValueError):
            cloud_weight = AppSettings().cloud_ai_usage_weight_percent
        migrated["cloud_ai_usage_weight_percent"] = max(0, min(100, round(cloud_weight / 5) * 5))

        chat_font_family = str(migrated.get("chat_font_family", "") or "").strip()
        if not chat_font_family:
            language = str(migrated.get("language", AppSettings().language) or AppSettings().language).strip().lower()
            chat_font_family = "맑은 고딕" if language.startswith("ko") else "Noto Sans"
        migrated["chat_font_family"] = chat_font_family
        try:
            chat_font_size = int(migrated.get("chat_font_size", AppSettings().chat_font_size))
        except (TypeError, ValueError):
            chat_font_size = AppSettings().chat_font_size
        migrated["chat_font_size"] = max(1, min(200, chat_font_size))

        self._migrate_cloud_ai_settings(migrated)
        self._migrate_web_search_settings(migrated)

        return migrated


    def _migrate_user_country_settings(self, migrated: dict) -> None:
        default_settings = AppSettings()
        preset = str(migrated.get("user_country_preset", default_settings.user_country_preset)).strip().lower()
        allowed = {"auto_language", "kr", "jp", "us", "eu", "custom", "ip_auto"}
        if preset not in allowed:
            preset = "auto_language"

        migrated["user_country_preset"] = preset

        if "user_country_code" not in migrated:
            language = str(migrated.get("language", default_settings.language)).lower()
            migrated["user_country_code"] = "KR" if language.startswith("ko") else "US"

        if "user_country_location" not in migrated:
            code = str(migrated.get("user_country_code", "")).strip().upper()
            migrated["user_country_location"] = {
                "KR": "South Korea",
                "JP": "Japan",
                "US": "United States",
            }.get(code, "")

    def _migrate_cloud_ai_settings(self, migrated: dict) -> None:
        default_settings = AppSettings()

        if "cloud_ai_enabled" not in migrated:
            migrated["cloud_ai_enabled"] = False

        if "cloud_ai_provider" not in migrated:
            migrated["cloud_ai_provider"] = guess_cloud_ai_provider(
                str(migrated.get("cloud_model", default_settings.cloud_model))
            )

        provider = normalize_provider(migrated.get("cloud_ai_provider", "openai"), "openai")

        if "cloud_ai_base_url" not in migrated:
            migrated["cloud_ai_base_url"] = default_cloud_base_url(provider)

        if "cloud_ai_auth_mode" not in migrated:
            migrated["cloud_ai_auth_mode"] = "secure_store"

        if "cloud_ai_credential_id" not in migrated:
            migrated["cloud_ai_credential_id"] = default_cloud_credential_id(provider)

        if "cloud_ai_api_key_env" not in migrated:
            migrated["cloud_ai_api_key_env"] = default_cloud_api_key_env(provider)

        if "cloud_model" not in migrated:
            migrated["cloud_model"] = ""

        cloud_models = migrated.get("cloud_ai_models")
        if cloud_models is None:
            cloud_models = default_cloud_models(provider)
        elif isinstance(cloud_models, str):
            cloud_models = cloud_models.replace(",", "\n").splitlines()
        elif not isinstance(cloud_models, list):
            cloud_models = [migrated["cloud_model"]]

        normalized_models: list[str] = []
        for model in cloud_models:
            model_text = str(model).strip()
            if model_text and model_text not in normalized_models:
                normalized_models.append(model_text)

        cloud_model = str(migrated.get("cloud_model", "")).strip()
        if cloud_model and cloud_model not in normalized_models:
            normalized_models.insert(0, cloud_model)

        if not normalized_models:
            normalized_models = list(default_settings.cloud_ai_models)

        migrated["cloud_ai_models"] = normalized_models


    def _migrate_web_search_settings(self, migrated: dict) -> None:
        default_settings = AppSettings()

        provider = normalize_provider(
            migrated.get("web_search_provider", default_settings.web_search_provider),
            default_settings.web_search_provider,
        )
        if provider not in KNOWN_WEB_SEARCH_PROVIDER_IDS:
            provider = default_settings.web_search_provider
        migrated["web_search_provider"] = provider

        auth_mode = str(
            migrated.get("web_search_auth_mode", default_settings.web_search_auth_mode)
        ).strip().lower()
        if auth_mode not in {"secure_store", "env_var"}:
            auth_mode = default_settings.web_search_auth_mode
        migrated["web_search_auth_mode"] = auth_mode

        migrated["web_search_enabled"] = bool(migrated.get("web_search_enabled", False))
        migrated["web_search_auto_enabled"] = bool(
            migrated.get("web_search_auto_enabled", False)
        )

        credential_id = str(migrated.get("web_search_credential_id", "")).strip()
        if not credential_id:
            credential_id = default_web_search_credential_id(provider)
        migrated["web_search_credential_id"] = credential_id

        api_key_env = str(migrated.get("web_search_api_key_env", "")).strip()
        if not api_key_env:
            api_key_env = default_web_search_api_key_env(provider)
        migrated["web_search_api_key_env"] = api_key_env

        migrated["web_search_base_url"] = str(
            migrated.get("web_search_base_url", "") or ""
        ).strip()

        try:
            max_results = int(migrated.get("web_search_max_results", 5))
        except (TypeError, ValueError):
            max_results = 5
        migrated["web_search_max_results"] = max(1, min(10, max_results))

        try:
            timeout_seconds = int(migrated.get("web_search_timeout_seconds", 20))
        except (TypeError, ValueError):
            timeout_seconds = 20
        migrated["web_search_timeout_seconds"] = max(3, min(120, timeout_seconds))
