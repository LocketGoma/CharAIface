import json
from pathlib import Path

from pydantic import ValidationError

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

        if "runtime_install_policy" not in migrated:
            migrated["runtime_install_policy"] = "ask"

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
            migrated["cloud_ai_provider"] = self._guess_cloud_ai_provider(
                str(migrated.get("cloud_model", default_settings.cloud_model))
            )

        provider = str(migrated.get("cloud_ai_provider", "openai")).strip().lower()

        if "cloud_ai_base_url" not in migrated:
            migrated["cloud_ai_base_url"] = self._default_cloud_base_url(provider)

        if "cloud_ai_auth_mode" not in migrated:
            migrated["cloud_ai_auth_mode"] = "secure_store"

        if "cloud_ai_credential_id" not in migrated:
            migrated["cloud_ai_credential_id"] = self._default_cloud_credential_id(provider)

        if "cloud_ai_api_key_env" not in migrated:
            migrated["cloud_ai_api_key_env"] = self._default_cloud_api_key_env(provider)

        if "cloud_model" not in migrated:
            migrated["cloud_model"] = ""

        cloud_models = migrated.get("cloud_ai_models")
        if cloud_models is None:
            cloud_models = self._default_cloud_models(provider)
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

        provider = str(
            migrated.get("web_search_provider", default_settings.web_search_provider)
        ).strip().lower()
        if provider not in {"none", "tavily", "firecrawl"}:
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
            credential_id = self._default_web_search_credential_id(provider)
        migrated["web_search_credential_id"] = credential_id

        api_key_env = str(migrated.get("web_search_api_key_env", "")).strip()
        if not api_key_env:
            api_key_env = self._default_web_search_api_key_env(provider)
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

    def _default_web_search_credential_id(self, provider: str) -> str:
        provider = (provider or "tavily").strip().lower()
        if provider == "firecrawl":
            return "CharAIface/firecrawl/api_key"
        if provider == "none":
            return ""
        return "CharAIface/tavily/api_key"

    def _default_web_search_api_key_env(self, provider: str) -> str:
        provider = (provider or "tavily").strip().lower()
        if provider == "firecrawl":
            return "FIRECRAWL_API_KEY"
        if provider == "none":
            return ""
        return "TAVILY_API_KEY"

    def _guess_cloud_ai_provider(self, cloud_model: str) -> str:
        normalized = cloud_model.lower()

        if normalized.startswith("openrouter/"):
            return "openrouter"
        if normalized.startswith("anthropic/") or normalized.startswith("claude-"):
            return "anthropic"
        if normalized.startswith("gemini") or normalized.startswith("google/"):
            return "gemini"
        if normalized.startswith("custom/"):
            return "custom"

        return "openai"

    def _default_cloud_api_key_env(self, provider: str) -> str:
        if provider == "openrouter":
            return "OPENROUTER_API_KEY"
        if provider == "anthropic":
            return "ANTHROPIC_API_KEY"
        if provider == "gemini":
            return "GEMINI_API_KEY"
        if provider == "none":
            return ""

        return "OPENAI_API_KEY"

    def _default_cloud_credential_id(self, provider: str) -> str:
        normalized = (provider or "custom").strip().lower().replace(" ", "_")
        if not normalized or normalized == "none":
            normalized = "openai"
        return f"CharAIface/{normalized}/api_key"

    def _default_cloud_base_url(self, provider: str) -> str:
        if provider == "openrouter":
            return "https://openrouter.ai/api/v1"
        return ""

    def _default_cloud_model(self, provider: str) -> str:
        models = self._default_cloud_models(provider)
        if models:
            return models[0]
        return ""

    def _default_cloud_models(self, provider: str) -> list[str]:
        if provider == "openrouter":
            return [
                "openai/gpt-4.1-mini",
                "openai/gpt-4.1",
                "anthropic/claude-3-5-sonnet-latest",
                "google/gemini-2.0-flash",
            ]
        if provider == "anthropic":
            return [
                "claude-3-5-sonnet-latest",
                "claude-3-5-haiku-latest",
                "claude-3-opus-latest",
            ]
        if provider == "gemini":
            return [
                "gemini-2.0-flash",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ]
        if provider == "custom":
            return ["custom/model-id"]
        if provider == "none":
            return []
        return [
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-5.1-mini",
            "gpt-5.1",
        ]
