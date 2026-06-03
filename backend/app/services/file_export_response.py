from __future__ import annotations

from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Any


FILE_EXPORT_RESPONSE_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "app"
    / "file_export_response_patterns.json"
)


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    try:
        with FILE_EXPORT_RESPONSE_CONFIG_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"[Export] Failed to load response patterns: {error}")
        return {}

    return payload if isinstance(payload, dict) else {}


def system_prompt_lines() -> tuple[str, ...]:
    return _config_list("system_prompt_lines")


def repair_refusal(content: str, *, request_content: str) -> str:
    if not _looks_like_request(request_content):
        return content
    if not _looks_like_refusal(content):
        return content

    cleaned = _remove_refusal_blocks(content)
    if cleaned:
        return cleaned

    return _fallback_response()


def _config_list(key: str) -> tuple[str, ...]:
    values = _load_config().get(key)
    if not isinstance(values, list):
        return ()
    return tuple(str(value).strip() for value in values if str(value).strip())


def _fallback_response() -> str:
    value = _load_config().get("fallback_response")
    return str(value).strip() if str(value or "").strip() else ""


def _looks_like_request(content: str) -> bool:
    normalized = str(content or "").strip().lower()
    if not normalized:
        return False
    return any(marker.lower() in normalized for marker in _config_list("request_markers"))


def _looks_like_refusal(content: str) -> bool:
    normalized = str(content or "").strip().lower()
    if not normalized:
        return False
    return any(marker.lower() in normalized for marker in _config_list("refusal_markers"))


def _remove_refusal_blocks(content: str) -> str:
    blocks = re.split(r"\n\s*\n", str(content or "").strip())
    kept_blocks = [
        block.strip()
        for block in blocks
        if block.strip() and not _looks_like_refusal(block)
    ]
    if kept_blocks:
        return "\n\n".join(kept_blocks).strip()

    kept_lines = [
        line.rstrip()
        for line in str(content or "").splitlines()
        if line.strip() and not _looks_like_refusal(line)
    ]
    return "\n".join(kept_lines).strip()
