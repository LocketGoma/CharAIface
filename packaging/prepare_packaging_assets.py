from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop.characters.character_pack_archive import export_folder_to_charpack

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare assets for PyInstaller packaging."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    target = args.target.resolve()

    if not source.exists():
        raise FileNotFoundError(f"Source asset directory not found: {source}")

    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(source, target)

    builtin_characters_dir = target / "characters"
    if builtin_characters_dir.exists():
        for pack_dir in sorted(builtin_characters_dir.iterdir()):
            if not pack_dir.is_dir():
                continue
            if not (pack_dir / "manifest.json").is_file():
                continue
            charpack_path = target / f"{pack_dir.name}.charpack"
            export_folder_to_charpack(pack_dir, charpack_path)

    print(f"[CharAIface] Prepared packaging assets: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
