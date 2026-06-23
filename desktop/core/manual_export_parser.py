from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from shared.runtime_paths import resource_path
from resources.addons.file_import_export.types import default_export_suffixes


CONFIG_PATH = resource_path("app", "manual_export_patterns.json")


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"[Export] Failed to load manual export patterns: {error}")
        return {}

    return payload if isinstance(payload, dict) else {}


def is_manual_message_export_request(text: str, *, language: str, has_filename: bool) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    if should_let_model_handle_export_request(text, language=language):
        return False

    has_target = _contains_any(normalized, _markers(language, "target_markers"))
    has_format = _contains_any(normalized, _markers(language, "format_markers"))
    has_strong_export = _contains_any(normalized, _markers(language, "strong_export_markers"))
    has_weak_action = _contains_any(normalized, _markers(language, "weak_action_markers"))
    has_existing_answer = has_existing_answer_export_target(text, language=language)
    has_export_shape = (has_strong_export and has_target) or (has_format and has_weak_action)

    if has_existing_answer and (has_strong_export or has_format or has_filename):
        return True

    return has_export_shape


def should_let_model_handle_export_request(text: str, *, language: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    has_model_task = _contains_any(normalized, _markers(language, "model_task_markers"))
    has_selection = _contains_any(normalized, _markers(language, "selection_markers"))
    has_existing_answer = has_existing_answer_export_target(text, language=language)

    if has_model_task and not has_existing_answer:
        return True

    if has_selection and not _contains_any(normalized, _markers(language, "csv_extract_markers")):
        return True

    return False


def has_existing_answer_export_target(text: str, *, language: str) -> bool:
    normalized = _normalize(text)
    return _contains_any(normalized, _markers(language, "existing_answer_markers"))


def should_extract_csv_like_content(text: str, *, language: str) -> bool:
    normalized = _normalize(text)
    return _contains_any(normalized, _markers(language, "csv_extract_markers"))


def manual_export_suffix(
    text: str,
    *,
    language: str,
    supported_suffixes: set[str] | None = None,
) -> str:
    normalized = _normalize(text)
    for suffix, markers in _suffix_markers(language, supported_suffixes=supported_suffixes).items():
        if _contains_any(normalized, tuple(markers)):
            return suffix
    return ".txt"


def _markers(language: str, key: str) -> tuple[str, ...]:
    common_values = _common_config().get(key)
    localized_values = _localized_config(language).get(key)
    return _normalized_list(common_values) + _normalized_list(localized_values)


def _suffix_markers(
    language: str,
    *,
    supported_suffixes: set[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    values = _merged_suffix_marker_config(language)
    suffixes = _supported_suffixes(supported_suffixes=supported_suffixes)
    result: dict[str, tuple[str, ...]] = {}
    for suffix, markers in values.items():
        normalized_suffix = str(suffix).strip().casefold()
        if normalized_suffix not in suffixes or not isinstance(markers, list):
            continue
        result[normalized_suffix] = tuple(
            _normalize(str(marker)) for marker in markers if _normalize(str(marker))
        )
    return result


def _supported_suffixes(
    *,
    supported_suffixes: set[str] | None = None,
) -> set[str]:
    active_suffixes = {
        str(suffix).strip().casefold()
        for suffix in (supported_suffixes or default_export_suffixes())
        if str(suffix).strip().startswith(".")
    }
    if not active_suffixes:
        active_suffixes = default_export_suffixes()

    values = _load_config().get("supported_suffixes")
    if not isinstance(values, list):
        return active_suffixes
    suffixes = {
        str(value).strip().casefold()
        for value in values
        if str(value).strip().startswith(".")
    }
    return (suffixes & active_suffixes) or active_suffixes


def _merged_suffix_marker_config(language: str) -> dict[str, list[Any]]:
    merged: dict[str, list[Any]] = {}
    for source in (_common_config(), _localized_config(language)):
        values = source.get("suffix_markers")
        if not isinstance(values, dict):
            continue
        for suffix, markers in values.items():
            if not isinstance(markers, list):
                continue
            merged.setdefault(str(suffix), []).extend(markers)
    return merged


def _common_config() -> dict[str, Any]:
    config = _load_config()
    common = config.get("common")
    return common if isinstance(common, dict) else {}


def _localized_config(language: str) -> dict[str, Any]:
    config = _load_config()
    localized = config.get("localized") if isinstance(config.get("localized"), dict) else {}
    language_key = str(language or "").strip().casefold()
    selected = localized.get(language_key)
    if selected is None:
        base_key = language_key.split("-", 1)[0].split("_", 1)[0]
        selected = localized.get(base_key)
    if selected is None:
        selected = {}
    return selected if isinstance(selected, dict) else {}


def _normalized_list(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(_normalize(str(value)) for value in values if _normalize(str(value)))


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().casefold().split())
