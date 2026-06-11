from __future__ import annotations

import argparse
import json
import sys
from tempfile import TemporaryDirectory
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from desktop.characters.character_registry import DEFAULT_CHARACTER_ID, CharacterRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify required resources in a packaged CharAIface build."
    )
    parser.add_argument("--resources-root", type=Path, required=True)
    return parser.parse_args()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required resource file is missing: {path}")


def main() -> int:
    args = parse_args()
    resources_root = args.resources_root.resolve()

    require_file(resources_root / "locales" / "ui.csv")
    require_file(resources_root / "themes" / "light.json")
    require_file(resources_root / "themes" / "dark.json")
    require_file(resources_root / "data" / "settings.json")
    require_file(resources_root / "data" / "settings.json.example")
    require_file(resources_root / "builtin" / f"{DEFAULT_CHARACTER_ID}.charpack")

    settings = json.loads((resources_root / "data" / "settings.json").read_text(encoding="utf-8"))
    if str(settings.get("language", "")).lower() != "en":
        raise RuntimeError("Packaged default settings must use language='en'.")

    with TemporaryDirectory(prefix="charaiface_verify_user_characters_") as temp_name:
        registry = CharacterRegistry(
            builtin_characters_dir=resources_root / "builtin",
            user_characters_dir=Path(temp_name),
        )
        registry.load()
        default_pack = registry.get_default_pack()

        if default_pack is None:
            raise RuntimeError("No valid default character pack was loaded.")
        if default_pack.id != DEFAULT_CHARACTER_ID:
            raise RuntimeError(
                "Unexpected default character pack: "
                f"{default_pack.id!r}, expected {DEFAULT_CHARACTER_ID!r}"
            )

    print(
        "[CharAIface] Packaged resources verified: "
        f"{resources_root} ({default_pack.id})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
