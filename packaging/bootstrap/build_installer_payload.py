from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

INCLUDED_DIRS = (
    "backend",
    "desktop",
    "resources/app",
    "resources/characters",
    "resources/data/search_context",
    "resources/icons",
    "resources/locales",
    "resources/models",
    "resources/themes",
    "scripts",
    "shared",
)

INCLUDED_FILES = (
    "CHARPACK.md",
    "LICENSE",
    "README.md",
    "pyproject.toml",
)

EXCLUDED_NAMES = {
    ".DS_Store",
    ".env",
    ".gitkeep",
    "Thumbs.db",
}

EXCLUDED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "chat_sessions",
    "exports",
    "file_analysis",
    "logs",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build embedded installer payload.")
    parser.add_argument(
        "--target",
        type=Path,
        default=ROOT / "build" / "bootstrap-installer" / "payload",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.target.resolve()
    app_target = target / "app"

    if target.exists():
        shutil.rmtree(target)

    app_target.mkdir(parents=True, exist_ok=True)

    for relative_dir in INCLUDED_DIRS:
        copy_tree(ROOT / relative_dir, app_target / relative_dir)

    copy_builtin_charpacks(
        ROOT / "resources" / "builtin",
        app_target / "resources" / "builtin",
    )

    for relative_file in INCLUDED_FILES:
        source = ROOT / relative_file
        if source.exists():
            destination = app_target / relative_file
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    print(f"[CharAIface] Installer payload prepared: {target}")
    return 0


def copy_tree(source: Path, target: Path) -> None:
    if not source.exists():
        return

    for path in source.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(source)
        if should_skip(path, relative):
            continue

        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def copy_builtin_charpacks(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*.charpack")):
        if not path.is_file():
            continue
        shutil.copy2(path, target / path.name)


def should_skip(path: Path, relative: Path) -> bool:
    if path.name in EXCLUDED_NAMES:
        return True
    return any(part in EXCLUDED_PARTS for part in relative.parts)


if __name__ == "__main__":
    raise SystemExit(main())
