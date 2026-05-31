from __future__ import annotations


CLOUD_AI_PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "none": {
        "api_key_env": "",
        "credential_id": "CharAIface/openai/api_key",
        "api_key_url": "",
        "base_url": "",
        "model": "",
        "models": [],
    },
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "credential_id": "CharAIface/openai/api_key",
        "api_key_url": "https://platform.openai.com/api-keys",
        "base_url": "",
        "model": "gpt-4.1-mini",
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-5.1-mini", "gpt-5.1"],
    },
    "openrouter": {
        "api_key_env": "OPENROUTER_API_KEY",
        "credential_id": "CharAIface/openrouter/api_key",
        "api_key_url": "https://openrouter.ai/settings/keys",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1-mini",
        "models": [
            "openai/gpt-4.1-mini",
            "openai/gpt-4.1",
            "anthropic/claude-3-5-sonnet-latest",
            "google/gemini-2.0-flash",
        ],
    },
    "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "credential_id": "CharAIface/anthropic/api_key",
        "api_key_url": "https://console.anthropic.com/settings/keys",
        "base_url": "",
        "model": "claude-3-5-sonnet-latest",
        "models": [
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
        ],
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "credential_id": "CharAIface/gemini/api_key",
        "api_key_url": "https://aistudio.google.com/app/apikey",
        "base_url": "",
        "model": "gemini-2.0-flash",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    },
    "custom": {
        "api_key_env": "CUSTOM_API_KEY",
        "credential_id": "CharAIface/custom/api_key",
        "api_key_url": "",
        "base_url": "",
        "model": "custom/model-id",
        "models": ["custom/model-id"],
    },
}

WEB_SEARCH_PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "none": {
        "credential_id": "",
        "api_key_env": "",
        "api_key_url": "",
        "base_url": "",
    },
    "tavily": {
        "credential_id": "CharAIface/tavily/api_key",
        "api_key_env": "TAVILY_API_KEY",
        "api_key_url": "https://app.tavily.com/",
        "base_url": "",
    },
    "firecrawl": {
        "credential_id": "CharAIface/firecrawl/api_key",
        "api_key_env": "FIRECRAWL_API_KEY",
        "api_key_url": "https://www.firecrawl.dev/app/api-keys",
        "base_url": "",
    },
}

CLOUD_MODEL_PROVIDER_PREFIX_RULES = (
    (("openrouter/",), "openrouter"),
    (("anthropic/", "claude-"), "anthropic"),
    (("gemini", "google/"), "gemini"),
    (("custom/",), "custom"),
)

KNOWN_CLOUD_PROVIDER_IDS = tuple(CLOUD_AI_PROVIDER_DEFAULTS.keys())
KNOWN_WEB_SEARCH_PROVIDER_IDS = tuple(WEB_SEARCH_PROVIDER_DEFAULTS.keys())


def normalize_provider(provider: str, default: str = "") -> str:
    return str(provider or default).strip().lower()


def cloud_ai_provider_defaults(provider: str) -> dict[str, object]:
    normalized = normalize_provider(provider, "openai")
    return CLOUD_AI_PROVIDER_DEFAULTS.get(normalized, CLOUD_AI_PROVIDER_DEFAULTS["openai"])


def web_search_provider_defaults(provider: str) -> dict[str, object]:
    normalized = normalize_provider(provider, "tavily")
    return WEB_SEARCH_PROVIDER_DEFAULTS.get(normalized, WEB_SEARCH_PROVIDER_DEFAULTS["tavily"])


def default_cloud_api_key_env(provider: str) -> str:
    return str(cloud_ai_provider_defaults(provider).get("api_key_env", ""))


def default_cloud_credential_id(provider: str) -> str:
    return str(cloud_ai_provider_defaults(provider).get("credential_id", ""))


def default_cloud_base_url(provider: str) -> str:
    return str(cloud_ai_provider_defaults(provider).get("base_url", ""))


def default_cloud_models(provider: str) -> list[str]:
    return [str(model) for model in cloud_ai_provider_defaults(provider).get("models", [])]


def default_web_search_api_key_env(provider: str) -> str:
    return str(web_search_provider_defaults(provider).get("api_key_env", ""))


def default_web_search_credential_id(provider: str) -> str:
    return str(web_search_provider_defaults(provider).get("credential_id", ""))


def guess_cloud_ai_provider(cloud_model: str) -> str:
    normalized = str(cloud_model or "").lower()
    for prefixes, provider in CLOUD_MODEL_PROVIDER_PREFIX_RULES:
        if normalized.startswith(prefixes):
            return provider
    return "openai"
