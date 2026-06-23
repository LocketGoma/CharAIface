from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


AddonCapability = Literal[
    "prompt",
    "file_intake",
    "file_analysis",
    "export",
    "settings_page",
    "desktop_ui",
    "desktop_widget",
    "backend_tool",
]

KNOWN_ADDON_CAPABILITIES = {
    "prompt",
    "file_intake",
    "file_analysis",
    "export",
    "settings_page",
    "desktop_ui",
    "desktop_widget",
    "backend_tool",
}


@dataclass(frozen=True)
class AddonManifest:
    id: str
    name: str
    version: str
    description: str
    default_enabled: bool = False
    capabilities: tuple[AddonCapability, ...] = ()
    prompt_file: str = ""
    settings_schema: dict[str, Any] = field(default_factory=dict)
    settings_ui: dict[str, dict[str, Any]] = field(default_factory=dict)
    capability_labels: dict[str, str] = field(default_factory=dict)
    localized: dict[str, Any] = field(default_factory=dict)
    provided_features: tuple[str, ...] = ()

    def display_name(self, language: str) -> str:
        localized = _localized_manifest_section(self.localized, language)
        return str(localized.get("name") or self.name).strip() or self.id

    def display_description(self, language: str) -> str:
        localized = _localized_manifest_section(self.localized, language)
        return str(localized.get("description") or self.description).strip()

    def setting_label(self, key: str, language: str) -> str:
        return _localized_setting_value(
            key,
            "label",
            language,
            self.settings_ui,
            self.localized,
        ) or _humanize_setting_key(key)

    def setting_description(self, key: str, language: str) -> str:
        return _localized_setting_value(
            key,
            "description",
            language,
            self.settings_ui,
            self.localized,
        )

    def capability_text(self, language: str) -> str:
        labels = [
            self.capability_label(str(capability), language)
            for capability in self.capabilities
        ]
        return ", ".join(label for label in labels if label) or "-"

    def capability_label(self, capability: str, language: str) -> str:
        localized_manifest = _localized_manifest_section(self.localized, language)
        localized_capabilities = localized_manifest.get("capabilities")
        if isinstance(localized_capabilities, dict):
            text = str(localized_capabilities.get(capability) or "").strip()
            if text:
                return text

        text = str(self.capability_labels.get(capability) or "").strip()
        if text:
            return text
        return _humanize_setting_key(capability)


class AddonModule(ABC):
    """Base class for builtin and future external CharAIface add-on modules."""

    manifest: AddonManifest
    source: str = "builtin"
    load_issue: str = ""

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def registry_key(self) -> str:
        return self.id

    def is_available(self) -> bool:
        return not bool(self.load_issue)

    def is_enabled(self, settings_snapshot: Mapping[str, Any] | None) -> bool:
        if not self.is_available():
            return False
        settings = settings_snapshot or {}
        enabled_addons = settings.get("enabled_addons")
        if isinstance(enabled_addons, Mapping) and self.id in enabled_addons:
            return bool(enabled_addons[self.id])
        return self.manifest.default_enabled

    def settings(self, settings_snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
        settings = settings_snapshot or {}
        addon_settings = settings.get("addon_settings")
        module_settings: Any = None
        if isinstance(addon_settings, Mapping):
            module_settings = addon_settings.get(self.id)
        if not isinstance(module_settings, Mapping):
            module_settings = {}
        return {**self.manifest.settings_schema, **dict(module_settings)}

    def prompt_contribution(
        self,
        *,
        settings_snapshot: Mapping[str, Any] | None,
        app_language: str,
    ) -> str:
        return ""


def addon_manifest_from_mapping(payload: Mapping[str, Any]) -> AddonManifest:
    capabilities = payload.get("capabilities")
    settings_schema = payload.get("settings_schema")
    settings_ui = payload.get("settings_ui")
    capability_labels = payload.get("capability_labels")
    localized = payload.get("localized")
    provided_features = payload.get("provided_features")

    addon_id = str(payload.get("id") or "").strip()
    return AddonManifest(
        id=addon_id,
        name=str(payload.get("name") or addon_id or "Untitled add-on").strip(),
        version=str(payload.get("version") or "0.0.0").strip(),
        description=str(payload.get("description") or "").strip(),
        default_enabled=bool(payload.get("default_enabled", False)),
        capabilities=_normalized_capabilities(capabilities),
        prompt_file=str(payload.get("prompt_file") or "").strip(),
        settings_schema=settings_schema if isinstance(settings_schema, dict) else {},
        settings_ui=settings_ui if isinstance(settings_ui, dict) else {},
        capability_labels=capability_labels if isinstance(capability_labels, dict) else {},
        localized=localized if isinstance(localized, dict) else {},
        provided_features=_normalized_feature_ids(provided_features, fallback=addon_id),
    )


def _normalized_capabilities(value: Any) -> tuple[AddonCapability, ...]:
    if not isinstance(value, (list, tuple)):
        return ()

    result: list[AddonCapability] = []
    for item in value:
        capability = str(item or "").strip()
        if capability not in KNOWN_ADDON_CAPABILITIES or capability in result:
            continue
        result.append(capability)  # type: ignore[arg-type]
    return tuple(result)


def _normalized_feature_ids(value: Any, *, fallback: str) -> tuple[str, ...]:
    raw_values = value if isinstance(value, (list, tuple)) else [fallback]
    result: list[str] = []
    for item in raw_values:
        feature_id = _normalized_feature_id(item)
        if feature_id and feature_id not in result:
            result.append(feature_id)
    return tuple(result)


def _normalized_feature_id(value: Any) -> str:
    text = str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")
    return "_".join(part for part in text.split("_") if part)


def _localized_manifest_section(localized: dict[str, Any], language: str) -> dict[str, Any]:
    if not isinstance(localized, dict):
        return {}
    language_key = str(language or "").strip().casefold()
    candidates = [
        language_key,
        language_key.split("-", 1)[0].split("_", 1)[0],
    ]
    for key in candidates:
        value = localized.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _localized_setting_value(
    key: str,
    field_name: str,
    language: str,
    settings_ui: dict[str, dict[str, Any]],
    localized: dict[str, Any],
) -> str:
    localized_manifest = _localized_manifest_section(localized, language)
    localized_settings = localized_manifest.get("settings")
    if isinstance(localized_settings, dict):
        value = localized_settings.get(key)
        if isinstance(value, dict):
            text = str(value.get(field_name) or "").strip()
            if text:
                return text

    value = settings_ui.get(key)
    if isinstance(value, dict):
        text = str(value.get(field_name) or "").strip()
        if text:
            return text
    return ""


def _humanize_setting_key(key: str) -> str:
    words = str(key or "").strip().replace("-", "_").split("_")
    return " ".join(word.capitalize() for word in words if word) or "Setting"
