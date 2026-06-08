from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from shared.runtime_paths import resource_path


CONFIG_PATH = resource_path("app", "export_filename_patterns.json")


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"[Export] Failed to load filename parser config: {error}")
        return {}

    return payload if isinstance(payload, dict) else {}


def parse_manual_export_filename(
    text: str,
    *,
    language: str,
    fallback_suffix: str,
) -> Path | None:
    config = _load_config()
    supported_suffixes = _supported_suffixes(config)
    candidate = _extract_candidate(text, language=language, config=config, supported_suffixes=supported_suffixes)
    if candidate is None:
        return None

    filename = _sanitize_filename(candidate, language=language, config=config)
    if not filename:
        return None

    path = Path(filename)
    suffix = path.suffix.casefold()
    if suffix and suffix not in supported_suffixes:
        return None
    if not suffix:
        path = path.with_suffix(fallback_suffix)
    return path


def _extract_candidate(
    text: str,
    *,
    language: str,
    config: dict[str, Any],
    supported_suffixes: set[str],
) -> str | None:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return None

    for pattern in _language_patterns(config, language):
        try:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
        except re.error as error:
            print(f"[Export] Invalid filename parser pattern for {language}: {error}")
            continue
        if match:
            return match.group(1)

    suffix_pattern = "|".join(re.escape(suffix.lstrip(".")) for suffix in sorted(supported_suffixes))
    explicit_file_match = re.search(
        rf'["“”\'「」]?([^"“”\'「」/\\:\n]+?\.(?:{suffix_pattern}))["“”\'「」]?',
        normalized,
        flags=re.IGNORECASE,
    )
    if explicit_file_match:
        return explicit_file_match.group(1)

    return None


def _sanitize_filename(filename: str, *, language: str, config: dict[str, Any]) -> str:
    cleaned = filename.strip()

    for pattern in _cleanup_patterns(config, language):
        try:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        except re.error as error:
            print(f"[Export] Invalid filename cleanup pattern for {language}: {error}")

    cleaned = Path(cleaned).name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")

    if cleaned.casefold() in _blank_values(config):
        return ""
    return cleaned


def _supported_suffixes(config: dict[str, Any]) -> set[str]:
    raw_suffixes = config.get("supported_suffixes") or []
    suffixes = {
        str(suffix).strip().casefold()
        for suffix in raw_suffixes
        if str(suffix).strip().startswith(".")
    }
    return suffixes or {".txt", ".md", ".csv", ".pdf"}


def _language_patterns(config: dict[str, Any], language: str) -> list[str]:
    language_config = _language_config(config, language)
    patterns = language_config.get("candidate_patterns") or []
    return [str(pattern) for pattern in patterns if str(pattern).strip()]


def _cleanup_patterns(config: dict[str, Any], language: str) -> list[str]:
    common_config = config.get("common") if isinstance(config.get("common"), dict) else {}
    language_config = _language_config(config, language)
    patterns = list(common_config.get("trailing_cleanup_patterns") or [])
    patterns.extend(language_config.get("trailing_cleanup_patterns") or [])
    return [str(pattern) for pattern in patterns if str(pattern).strip()]


def _blank_values(config: dict[str, Any]) -> set[str]:
    common_config = config.get("common") if isinstance(config.get("common"), dict) else {}
    values = common_config.get("blank_values") or []
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _language_config(config: dict[str, Any], language: str) -> dict[str, Any]:
    languages = config.get("languages") if isinstance(config.get("languages"), dict) else {}
    language_key = str(language or "").strip().casefold()
    selected = languages.get(language_key)
    if selected is None:
        base_key = language_key.split("-", 1)[0].split("_", 1)[0]
        selected = languages.get(base_key)
    if selected is None:
        selected = languages.get("en") or {}
    return selected if isinstance(selected, dict) else {}
