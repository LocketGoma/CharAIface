from __future__ import annotations

from typing import Any, Iterable, Mapping

from shared.addons.base import AddonModule
from shared.addons.external import ExternalManifestAddon, load_external_addons


ADDON_PROMPT_BLOCK_HEADER = "Enabled add-on modules:"
MODULE_ID_CONFLICT_ISSUE = "Module id conflicts with already loaded module: {module_id}"
PROVIDED_FEATURE_CONFLICT_ISSUE = (
    "Provided feature conflicts with already loaded module: {owners}"
)


def _builtin_modules() -> tuple[AddonModule, ...]:
    modules: list[AddonModule] = []
    try:
        from resources.addons.file_import_export import FileImportExportAddon
    except Exception as error:
        print(f"[Addons] File Import / Export add-on unavailable: {error}")
    else:
        modules.append(FileImportExportAddon())
    return tuple(modules)


class AddonRegistry:
    def __init__(self, modules: Iterable[AddonModule]) -> None:
        self._modules = tuple(modules)
        self._modules_by_id: dict[str, AddonModule] = {}
        for module in self._modules:
            if module.id not in self._modules_by_id and module.is_available():
                self._modules_by_id[module.id] = module

    def all(self) -> tuple[AddonModule, ...]:
        return self._modules

    def get(self, addon_id: str) -> AddonModule | None:
        return self._modules_by_id.get(addon_id)

    def enabled(self, settings_snapshot: Mapping[str, Any] | None) -> tuple[AddonModule, ...]:
        return tuple(
            module for module in self._modules if module.is_enabled(settings_snapshot)
        )

    def prompt_block(
        self,
        *,
        settings_snapshot: Mapping[str, Any] | None,
        app_language: str,
    ) -> str:
        prompts = [
            prompt
            for module in self.enabled(settings_snapshot)
            if "prompt" in module.manifest.capabilities
            for prompt in [
                module.prompt_contribution(
                    settings_snapshot=settings_snapshot,
                    app_language=app_language,
                ).strip()
            ]
            if prompt
        ]
        if not prompts:
            return ""
        return f"{ADDON_PROMPT_BLOCK_HEADER}\n" + "\n\n".join(prompts)


def _compose_modules() -> tuple[AddonModule, ...]:
    modules: list[AddonModule] = list(_BUILTIN_MODULES)
    claimed_ids = {module.id for module in modules if module.is_available()}
    claimed_features: dict[str, str] = {}
    for module in modules:
        if not module.is_available():
            continue
        for feature in module.manifest.provided_features:
            claimed_features.setdefault(feature, module.id)

    for module in load_external_addons():
        issue = module.load_issue
        if module.id in claimed_ids:
            issue = _module_id_conflict_issue(module.id)
        else:
            conflicting_features = [
                feature
                for feature in module.manifest.provided_features
                if feature in claimed_features
            ]
            if conflicting_features:
                issue = _provided_feature_conflict_issue(
                    _feature_conflict_owners(conflicting_features, claimed_features)
                )

        if issue:
            module = ExternalManifestAddon(
                manifest=module.manifest,
                module_dir=module.module_dir,
                registry_key=module.registry_key,
                load_issue=issue,
            )
        else:
            claimed_ids.add(module.id)
            for feature in module.manifest.provided_features:
                claimed_features.setdefault(feature, module.id)
        modules.append(module)

    return tuple(modules)


def _module_id_conflict_issue(module_id: str) -> str:
    return MODULE_ID_CONFLICT_ISSUE.format(module_id=module_id)


def _provided_feature_conflict_issue(owners: str) -> str:
    return PROVIDED_FEATURE_CONFLICT_ISSUE.format(owners=owners)


def _feature_conflict_owners(
    features: list[str],
    claimed_features: Mapping[str, str],
) -> str:
    return ", ".join(
        f"{feature} ({claimed_features[feature]})"
        for feature in features
    )


_BUILTIN_MODULES = _builtin_modules()
builtin_addon_registry = AddonRegistry(modules=_BUILTIN_MODULES)
addon_registry = AddonRegistry(modules=_compose_modules())


def is_addon_enabled(addon_id: str, settings_snapshot: Mapping[str, Any] | None) -> bool:
    module = addon_registry.get(addon_id)
    return bool(module and module.is_enabled(settings_snapshot))


def addon_settings(addon_id: str, settings_snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    module = addon_registry.get(addon_id)
    if module is None:
        return {}
    return module.settings(settings_snapshot)


def addon_display_name(addon_id: str, language: str) -> str:
    module = addon_registry.get(addon_id)
    if module is None:
        return addon_id
    return module.manifest.display_name(language)


def enabled_addon_prompt_block(
    *,
    settings_snapshot: Mapping[str, Any] | None,
    app_language: str,
) -> str:
    return addon_registry.prompt_block(
        settings_snapshot=settings_snapshot,
        app_language=app_language,
    )
