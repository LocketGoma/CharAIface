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

        if "runtime_install_policy" not in migrated:
            migrated["runtime_install_policy"] = "ask"

        if "local_ai_provider" not in migrated:
            migrated["local_ai_provider"] = "ollama"

        if "local_ai_base_url" not in migrated:
            migrated["local_ai_base_url"] = "http://127.0.0.1:11434"

        if "auto_start_local_ai_server" not in migrated:
            migrated["auto_start_local_ai_server"] = True

        if "model_download_timeout_seconds" not in migrated:
            migrated["model_download_timeout_seconds"] = 600

        self._migrate_cloud_ai_settings(migrated)

        return migrated

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
