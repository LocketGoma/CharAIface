from __future__ import annotations


ANTHROPIC_VERSION = "2023-06-01"

CLOUD_PROVIDER_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}

CLOUD_PROVIDERS_WITH_PUBLIC_MODEL_CATALOG = {"openrouter"}


def normalize_cloud_provider(provider: str) -> str:
    return str(provider or "").strip().lower()


def cloud_provider_base_url(provider: str, configured_base_url: str = "") -> str:
    configured = str(configured_base_url or "").strip()
    if configured:
        return configured
    return CLOUD_PROVIDER_DEFAULT_BASE_URLS.get(normalize_cloud_provider(provider), "")
