from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from shared.addons.base import AddonManifest, AddonModule, addon_manifest_from_mapping
from shared.addons.manifest_loader import (
    ADDON_MANIFEST_FILENAME,
    DEFAULT_PROMPT_FILENAME,
    read_addon_manifest_payload,
)
from shared.runtime_paths import addon_modules_root


EXTERNAL_ADDON_SOURCE = "external"
EXTERNAL_REGISTRY_KEY_PREFIX = "external"
SAFE_EXTERNAL_CAPABILITIES = {"prompt", "settings_page"}
MANIFEST_ID_MISSING_ISSUE = "Manifest id is missing."
UNSAFE_EXTERNAL_CAPABILITIES_ISSUE = (
    "External manifest-only modules can only provide prompt/settings_page "
    "capabilities for now: {capabilities}"
)


class ExternalManifestAddon(AddonModule):
    source = EXTERNAL_ADDON_SOURCE

    def __init__(
        self,
        *,
        manifest: AddonManifest,
        module_dir: Path,
        registry_key: str,
        load_issue: str = "",
    ) -> None:
        self.manifest = manifest
        self.module_dir = module_dir
        self._registry_key = registry_key
        self.load_issue = load_issue

    @property
    def registry_key(self) -> str:
        return self._registry_key

    def prompt_contribution(
        self,
        *,
        settings_snapshot: Mapping[str, Any] | None,
        app_language: str,
    ) -> str:
        if "prompt" not in self.manifest.capabilities:
            return ""

        prompt_path = self._safe_module_file(
            self.manifest.prompt_file or DEFAULT_PROMPT_FILENAME
        )
        if prompt_path is None:
            return ""

        try:
            return prompt_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            print(f"[Addons] Failed to load external prompt {prompt_path}: {error}")
            return ""

    def _safe_module_file(self, relative_path: str) -> Path | None:
        raw_path = Path(str(relative_path or "").strip())
        if not raw_path or raw_path.is_absolute() or ".." in raw_path.parts:
            return None

        path = (self.module_dir / raw_path).resolve()
        try:
            path.relative_to(self.module_dir.resolve())
        except ValueError:
            return None
        return path if path.is_file() else None


def load_external_addons() -> tuple[ExternalManifestAddon, ...]:
    root = addon_modules_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"[Addons] Failed to prepare external module directory {root}: {error}")
        return ()

    modules: list[ExternalManifestAddon] = []
    for module_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        module = _load_external_addon(module_dir)
        if module is not None:
            modules.append(module)
    return tuple(modules)


def _load_external_addon(module_dir: Path) -> ExternalManifestAddon | None:
    manifest_path = module_dir / ADDON_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None

    payload, issue = read_addon_manifest_payload(manifest_path)
    if issue:
        return _external_addon_with_issue(
            module_dir,
            load_issue=issue,
        )

    payload.setdefault("id", module_dir.name)
    manifest = addon_manifest_from_mapping(payload)
    if not manifest.id:
        return _external_addon_with_issue(
            module_dir,
            load_issue=MANIFEST_ID_MISSING_ISSUE,
        )

    safe_capabilities, unsafe_capabilities = _split_external_capabilities(manifest)
    if unsafe_capabilities:
        manifest = replace(
            manifest,
            capabilities=safe_capabilities,
        )
        load_issue = UNSAFE_EXTERNAL_CAPABILITIES_ISSUE.format(
            capabilities=", ".join(unsafe_capabilities)
        )
    else:
        load_issue = ""

    return ExternalManifestAddon(
        manifest=manifest,
        module_dir=module_dir,
        registry_key=external_addon_registry_key(module_dir, manifest),
        load_issue=load_issue,
    )


def _external_addon_with_issue(
    module_dir: Path,
    *,
    load_issue: str,
) -> ExternalManifestAddon:
    manifest = AddonManifest(
        id=module_dir.name,
        name=module_dir.name,
        version="0.0.0",
        description="",
        default_enabled=False,
        provided_features=(module_dir.name.casefold(),),
    )
    return ExternalManifestAddon(
        manifest=manifest,
        module_dir=module_dir,
        registry_key=external_addon_registry_key(module_dir, manifest),
        load_issue=load_issue,
    )


def external_addon_registry_key(module_dir: Path, manifest: AddonManifest) -> str:
    return f"{EXTERNAL_REGISTRY_KEY_PREFIX}:{module_dir.name}:{manifest.id}"


def _split_external_capabilities(
    manifest: AddonManifest,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    safe: list[str] = []
    unsafe: list[str] = []
    for capability in manifest.capabilities:
        if capability in SAFE_EXTERNAL_CAPABILITIES:
            safe.append(capability)
        else:
            unsafe.append(capability)
    return tuple(safe), tuple(unsafe)
