from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.cloud_auth_manager import (
    CloudAuthManager,
    CloudCredentialConfig,
)


router = APIRouter(prefix="/cloud-ai", tags=["cloud-ai"])

CLOUD_AI_TIMEOUT_SECONDS = 10.0
CLOUD_AI_MODEL_LIST_TIMEOUT_SECONDS = 30.0
RECENT_MODEL_MAX_AGE_DAYS = 365


class CloudAITestRequest(BaseModel):
    provider: str
    auth_mode: Literal["secure_store", "env_var"] = "secure_store"
    credential_id: str
    api_key_env: str | None = None
    base_url: str = ""
    model: str = ""


class CloudAIModelsRequest(BaseModel):
    provider: str
    auth_mode: Literal["secure_store", "env_var"] = "secure_store"
    credential_id: str
    api_key_env: str | None = None
    base_url: str = ""


@router.post("/test-connection")
def test_cloud_ai_connection(request: CloudAITestRequest) -> dict[str, Any]:
    config = CloudCredentialConfig(
        provider=request.provider,
        auth_mode=request.auth_mode,
        credential_id=request.credential_id,
        api_key_env=request.api_key_env,
    )

    try:
        api_key = CloudAuthManager.get_api_key(config)
    except Exception as error:
        return {
            "ok": False,
            "provider": request.provider,
            "state": "credential_error",
            "error_code": "cloud_ai_credential_error",
            "error_detail": str(error),
        }

    if not api_key:
        return {
            "ok": False,
            "provider": request.provider,
            "state": "missing_api_key",
            "error_code": "cloud_ai_api_key_missing",
        }

    try:
        return _check_provider(request, api_key)
    except httpx.HTTPStatusError as error:
        return {
            "ok": False,
            "provider": request.provider,
            "state": "http_error",
            "error_code": "cloud_ai_http_error",
            "http_status": error.response.status_code,
            "error_detail": _safe_response_text(error.response),
        }
    except httpx.HTTPError as error:
        return {
            "ok": False,
            "provider": request.provider,
            "state": "request_failed",
            "error_code": "cloud_ai_request_failed",
            "error_detail": str(error),
        }
    except Exception as error:
        return {
            "ok": False,
            "provider": request.provider,
            "state": "error",
            "error_code": "cloud_ai_unknown_error",
            "error_detail": str(error),
        }


@router.post("/models")
def list_cloud_ai_models(request: CloudAIModelsRequest) -> dict[str, Any]:
    provider = request.provider.strip().lower()

    if provider == "none":
        return {
            "ok": False,
            "provider": provider,
            "state": "provider_disabled",
            "error_code": "cloud_ai_provider_disabled",
            "models": [],
        }

    config = CloudCredentialConfig(
        provider=request.provider,
        auth_mode=request.auth_mode,
        credential_id=request.credential_id,
        api_key_env=request.api_key_env,
    )

    try:
        api_key = CloudAuthManager.get_api_key(config)
    except Exception as error:
        return {
            "ok": False,
            "provider": provider,
            "state": "credential_error",
            "error_code": "cloud_ai_credential_error",
            "error_detail": str(error),
            "models": [],
        }

    # OpenRouter's public catalog can be listed without a key.
    # Other providers need a key to return account-appropriate results.
    if provider != "openrouter" and not api_key:
        return {
            "ok": False,
            "provider": provider,
            "state": "missing_api_key",
            "error_code": "cloud_ai_api_key_missing",
            "models": [],
        }

    try:
        models = _fetch_provider_models(request, api_key or "")
        return {
            "ok": True,
            "provider": provider,
            "state": "ready",
            "error_code": None,
            "models": models,
            "count": len(models),
        }
    except httpx.HTTPStatusError as error:
        return {
            "ok": False,
            "provider": provider,
            "state": "http_error",
            "error_code": "cloud_ai_http_error",
            "http_status": error.response.status_code,
            "error_detail": _safe_response_text(error.response),
            "models": [],
        }
    except httpx.HTTPError as error:
        return {
            "ok": False,
            "provider": provider,
            "state": "request_failed",
            "error_code": "cloud_ai_request_failed",
            "error_detail": str(error),
            "models": [],
        }
    except Exception as error:
        return {
            "ok": False,
            "provider": provider,
            "state": "error",
            "error_code": "cloud_ai_unknown_error",
            "error_detail": str(error),
            "models": [],
        }


def _check_provider(request: CloudAITestRequest, api_key: str) -> dict[str, Any]:
    provider = request.provider.strip().lower()

    if provider == "openai":
        base_url = request.base_url.strip() or "https://api.openai.com/v1"
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _ready_response(provider)

    if provider == "openrouter":
        base_url = request.base_url.strip() or "https://openrouter.ai/api/v1"
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _ready_response(provider)

    if provider == "anthropic":
        base_url = request.base_url.strip() or "https://api.anthropic.com/v1"
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _ready_response(provider)

    if provider == "gemini":
        base_url = (
            request.base_url.strip()
            or "https://generativelanguage.googleapis.com/v1beta"
        )
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            params={"key": api_key},
            timeout=CLOUD_AI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return _ready_response(provider)

    return {
        "ok": False,
        "provider": provider,
        "state": "unsupported_provider",
        "error_code": "cloud_ai_provider_unsupported",
    }


def _fetch_provider_models(request: CloudAIModelsRequest, api_key: str) -> list[str]:
    provider = request.provider.strip().lower()

    if provider == "openai":
        base_url = request.base_url.strip() or "https://api.openai.com/v1"
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=CLOUD_AI_MODEL_LIST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return _filter_openai_model_items(data.get("data", []))

    if provider == "openrouter":
        base_url = request.base_url.strip() or "https://openrouter.ai/api/v1"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers=headers,
            timeout=CLOUD_AI_MODEL_LIST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return _filter_openrouter_model_items(data.get("data", []))

    if provider == "anthropic":
        base_url = request.base_url.strip() or "https://api.anthropic.com/v1"
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=CLOUD_AI_MODEL_LIST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return _filter_anthropic_model_items(data.get("data", []))

    if provider == "gemini":
        base_url = (
            request.base_url.strip()
            or "https://generativelanguage.googleapis.com/v1beta"
        )
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            params={"key": api_key},
            timeout=CLOUD_AI_MODEL_LIST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return _filter_gemini_models(data.get("models", []))

    if provider == "custom":
        base_url = request.base_url.strip()
        if not base_url:
            return []

        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers=headers,
            timeout=CLOUD_AI_MODEL_LIST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        return _unique_sorted(_extract_id_list(data.get("data", [])))

    return []


def _extract_id_list(items: Any) -> list[str]:
    model_ids: list[str] = []
    if not isinstance(items, list):
        return model_ids

    for item in items:
        model_id = _model_id_from_item(item)
        if model_id and model_id not in model_ids:
            model_ids.append(model_id)

    return model_ids


def _model_id_from_item(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or item.get("name") or "").strip()
    return str(item).strip()


def _filter_openai_model_items(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []

    filtered: list[tuple[str, datetime | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        model_id = _model_id_from_item(item)
        if not model_id:
            continue
        if not _is_recent_unix_timestamp(item.get("created")):
            continue
        if not _is_openai_chat_model_name(model_id):
            continue

        filtered.append((model_id, _datetime_from_unix_timestamp(item.get("created"))))

    return _unique_sorted_by_created(filtered)


def _filter_openrouter_model_items(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []

    filtered: list[tuple[str, datetime | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        model_id = _model_id_from_item(item)
        if not model_id:
            continue
        if not _is_recent_unix_timestamp(item.get("created")):
            continue
        if _is_non_chat_model_name(model_id):
            continue

        filtered.append((model_id, _datetime_from_unix_timestamp(item.get("created"))))

    return _unique_sorted_by_created(filtered)


def _filter_anthropic_model_items(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []

    filtered: list[tuple[str, datetime | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        model_id = _model_id_from_item(item)
        if not model_id:
            continue
        if not _is_recent_iso_datetime(item.get("created_at")):
            continue

        filtered.append((model_id, _datetime_from_iso(item.get("created_at"))))

    return _unique_sorted_by_created(filtered)


def _is_openai_chat_model_name(model_id: str) -> bool:
    normalized = model_id.lower()
    allowed_prefixes = (
        "gpt-",
        "chatgpt-",
        "o1",
        "o3",
        "o4",
        "o5",
    )

    if not normalized.startswith(allowed_prefixes):
        return False

    return not _is_non_chat_model_name(model_id)


def _is_non_chat_model_name(model_id: str) -> bool:
    normalized = model_id.lower()
    blocked_fragments = (
        "embedding",
        "audio",
        "transcribe",
        "tts",
        "whisper",
        "dall-e",
        "image",
        "moderation",
        "realtime",
        "search-preview",
    )
    return any(fragment in normalized for fragment in blocked_fragments)


def _datetime_from_unix_timestamp(value: Any) -> datetime | None:
    try:
        created_seconds = int(value)
    except (TypeError, ValueError):
        return None

    try:
        return datetime.fromtimestamp(created_seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _datetime_from_iso(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _is_recent_unix_timestamp(value: Any) -> bool:
    parsed = _datetime_from_unix_timestamp(value)
    if parsed is None:
        return True
    return _is_recent_datetime(parsed)


def _is_recent_iso_datetime(value: Any) -> bool:
    parsed = _datetime_from_iso(value)
    if parsed is None:
        return True
    return _is_recent_datetime(parsed)


def _is_recent_datetime(value: datetime) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_MODEL_MAX_AGE_DAYS)
    return value >= cutoff


def _unique_sorted_by_created(items: list[tuple[str, datetime | None]]) -> list[str]:
    unique: dict[str, datetime | None] = {}
    for model_id, created_at in items:
        model_text = str(model_id).strip()
        if model_text and model_text not in unique:
            unique[model_text] = created_at

    return sorted(
        unique.keys(),
        key=lambda model_id: (
            unique[model_id] is not None,
            unique[model_id] or datetime.min.replace(tzinfo=timezone.utc),
            model_id.lower(),
        ),
        reverse=True,
    )


def _filter_gemini_models(models: Any) -> list[str]:
    model_ids: list[str] = []
    if not isinstance(models, list):
        return model_ids

    for item in models:
        if not isinstance(item, dict):
            continue

        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue

        name = str(item.get("name") or "").strip()
        if name.startswith("models/"):
            name = name.removeprefix("models/")

        if not name:
            continue
        if _is_legacy_gemini_model_name(name):
            continue
        if name not in model_ids:
            model_ids.append(name)

    return _unique_sorted(model_ids)


def _is_legacy_gemini_model_name(model_id: str) -> bool:
    normalized = model_id.lower()

    legacy_fragments = (
        "gemini-1.0",
        "gemini-1.5",
        "aqa",
        "embedding",
        "text-embedding",
    )
    return any(fragment in normalized for fragment in legacy_fragments)


def _unique_sorted_by_created(items: list[tuple[str, datetime | None]]) -> list[str]:
    unique: dict[str, datetime | None] = {}
    for model_id, created_at in items:
        model_text = str(model_id).strip()
        if model_text and model_text not in unique:
            unique[model_text] = created_at

    return sorted(
        unique.keys(),
        key=lambda model_id: (
            unique[model_id] is not None,
            unique[model_id] or datetime.min.replace(tzinfo=timezone.utc),
            model_id.lower(),
        ),
        reverse=True,
    )


def _filter_gemini_models(models: Any) -> list[str]:
    model_ids: list[str] = []
    if not isinstance(models, list):
        return model_ids

    for item in models:
        if not isinstance(item, dict):
            continue

        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue

        name = str(item.get("name") or "").strip()
        if name.startswith("models/"):
            name = name.removeprefix("models/")

        if name and name not in model_ids:
            model_ids.append(name)

    return _unique_sorted(model_ids)


def _unique_sorted(model_ids: list[str]) -> list[str]:
    unique: list[str] = []
    for model_id in model_ids:
        model_text = str(model_id).strip()
        if model_text and model_text not in unique:
            unique.append(model_text)

    return sorted(unique, key=lambda value: value.lower())


def _safe_response_text(response: httpx.Response) -> str:
    try:
        text = response.text
    except Exception:
        return ""

    text = text.strip()
    if len(text) > 500:
        return text[:500] + "..."
    return text


def _ready_response(provider: str) -> dict[str, Any]:
    return {
        "ok": True,
        "provider": provider,
        "state": "ready",
        "error_code": None,
    }
