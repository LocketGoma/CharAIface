from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from shared.addons.base import AddonManifest, addon_manifest_from_mapping
from shared.runtime_paths import resource_path


ADDON_MANIFEST_FILENAME = "addon.json"
DEFAULT_PROMPT_FILENAME = "prompt.md"


def bundled_addon_resource_path(addon_id: str, *parts: str) -> Path:
    return resource_path("addons", addon_id, *parts)


def read_addon_manifest_payload(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, f"Manifest could not be read: {error}"

    if not isinstance(payload, dict):
        return {}, "Manifest must be a JSON object."
    return payload, ""


def load_addon_manifest(
    path: Path,
    *,
    fallback_payload: Mapping[str, Any] | None = None,
) -> AddonManifest:
    payload, issue = read_addon_manifest_payload(path)
    if issue:
        print(f"[Addons] {issue} ({path})")
        payload = {}

    if not payload and fallback_payload is not None:
        payload = dict(fallback_payload)
    return addon_manifest_from_mapping(payload)
