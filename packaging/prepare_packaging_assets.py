from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop.characters.character_pack_archive import export_folder_to_charpack


CHARPACK_SUFFIX = ".charpack"
MANIFEST_FILENAME = "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare assets for PyInstaller packaging."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--settings-source", type=Path)
    parser.add_argument("--settings-target", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    target = args.target.resolve()
    settings_source = args.settings_source.resolve() if args.settings_source else None
    settings_target = args.settings_target.resolve() if args.settings_target else None

    if not source.exists():
        raise FileNotFoundError(f"Source asset directory not found: {source}")

    _prepare_builtin_assets(source, target)

    if settings_source is not None or settings_target is not None:
        if settings_source is None or settings_target is None:
            raise ValueError("--settings-source and --settings-target must be used together")
        _prepare_settings_assets(settings_source, settings_target)

    return 0


def _prepare_builtin_assets(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)

    target.mkdir(parents=True, exist_ok=True)

    prepared_count = 0
    for asset_root in _iter_character_asset_roots(source):
        prepared_count += _copy_charpacks(asset_root, target)
        prepared_count += _export_folder_packs(asset_root, target)

    if prepared_count == 0:
        raise FileNotFoundError(
            "No built-in character packs were found under "
            f"{source}. Expected .charpack files or folders with {MANIFEST_FILENAME}."
        )

    print(f"[CharAIface] Prepared packaging assets: {target}")


def _iter_character_asset_roots(source: Path) -> list[Path]:
    roots = [source]
    nested_characters = source / "characters"
    if nested_characters.is_dir():
        roots.append(nested_characters)

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(root)
    return unique_roots


def _copy_charpacks(source: Path, target: Path) -> int:
    copied_count = 0
    for charpack_path in sorted(source.glob(f"*{CHARPACK_SUFFIX}")):
        if not charpack_path.is_file():
            continue
        shutil.copy2(charpack_path, target / charpack_path.name)
        copied_count += 1
    return copied_count


def _export_folder_packs(source: Path, target: Path) -> int:
    exported_count = 0

    if (source / MANIFEST_FILENAME).is_file():
        export_folder_to_charpack(source, target / f"{source.name}{CHARPACK_SUFFIX}")
        return 1

    for pack_dir in sorted(source.iterdir()):
        if not pack_dir.is_dir():
            continue
        if not (pack_dir / MANIFEST_FILENAME).is_file():
            continue
        export_folder_to_charpack(pack_dir, target / f"{pack_dir.name}{CHARPACK_SUFFIX}")
        exported_count += 1

    return exported_count


def _prepare_settings_assets(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Settings template not found: {source}")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source, target / "settings.json")
    shutil.copy2(source, target / "settings.json.example")

    print(f"[CharAIface] Prepared packaging settings: {target}")


if __name__ == "__main__":
    raise SystemExit(main())
