from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop.characters.character_pack_archive import export_folder_to_charpack


PACKAGING_COPY_IGNORE = shutil.ignore_patterns(
    ".DS_Store",
    "Thumbs.db",
    "__pycache__",
)

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

    shutil.copytree(source, target, ignore=PACKAGING_COPY_IGNORE)

    builtin_characters_dir = target / "characters"
    if builtin_characters_dir.exists():
        for pack_dir in sorted(builtin_characters_dir.iterdir()):
            if not pack_dir.is_dir():
                continue
            if not (pack_dir / "manifest.json").is_file():
                continue
            charpack_path = target / f"{pack_dir.name}.charpack"
            export_folder_to_charpack(pack_dir, charpack_path)
        shutil.rmtree(builtin_characters_dir)

    print(f"[CharAIface] Prepared packaging assets: {target}")


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
