from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class CloudAuthMode(StrEnum):
    SECURE_STORE = "secure_store"
    ENV_VAR = "env_var"


@dataclass(frozen=True)
class CloudCredentialConfig:
    provider: str
    auth_mode: str
    credential_id: str
    api_key_env: str | None = None


class CloudAuthManager:
    SERVICE_NAME = "CharAIface"

    @staticmethod
    def default_credential_id(provider: str) -> str:
        normalized = (provider or "custom").strip().lower().replace(" ", "_")
        if not normalized or normalized == "none":
            normalized = "openai"
        return f"CharAIface/{normalized}/api_key"

    @classmethod
    def save_api_key(cls, credential_id: str, api_key: str) -> None:
        keyring = cls._load_keyring()
        credential_id = credential_id.strip()
        api_key = api_key.strip()

        if not credential_id:
            raise ValueError("Credential ID is empty.")
        if not api_key:
            raise ValueError("API key is empty.")

        keyring.set_password(cls.SERVICE_NAME, credential_id, api_key)

    @classmethod
    def get_secure_api_key(cls, credential_id: str) -> str | None:
        if not credential_id:
            return None

        keyring = cls._load_keyring()
        return keyring.get_password(cls.SERVICE_NAME, credential_id)

    @classmethod
    def delete_api_key(cls, credential_id: str) -> None:
        if not credential_id:
            return

        keyring = cls._load_keyring()
        try:
            keyring.delete_password(cls.SERVICE_NAME, credential_id)
        except Exception as error:
            if error.__class__.__name__ != "PasswordDeleteError":
                raise

    @classmethod
    def get_api_key(cls, config: CloudCredentialConfig) -> str | None:
        auth_mode = (config.auth_mode or "").strip().lower()

        if auth_mode == CloudAuthMode.SECURE_STORE:
            return cls.get_secure_api_key(config.credential_id)

        if auth_mode == CloudAuthMode.ENV_VAR:
            if not config.api_key_env:
                return None
            return os.getenv(config.api_key_env)

        return None

    @classmethod
    def has_api_key(cls, config: CloudCredentialConfig) -> bool:
        try:
            return bool(cls.get_api_key(config))
        except Exception:
            return False

    @staticmethod
    def _load_keyring():
        try:
            import keyring
        except ImportError as error:
            raise RuntimeError(
                "keyring is not installed. Install it with: pip install keyring"
            ) from error

        return keyring
