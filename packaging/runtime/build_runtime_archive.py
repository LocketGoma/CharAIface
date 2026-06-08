from __future__ import annotations

import argparse
import json
import platform
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "packaging" / "bootstrap" / "installer_config.json"

EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}

EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "pip-cache",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive a prepared standalone Python runtime for CharAIface."
    )
    parser.add_argument(
        "--python-root",
        type=Path,
        required=True,
        help="Prepared relocatable Python runtime root to place under <install_dir>/runtime.",
    )
    parser.add_argument("--platform", dest="platform_key", default=None)
    parser.add_argument("--target", type=Path, default=ROOT / "dist" / "runtime")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    platform_key = args.platform_key or detect_platform_key()
    runtime_info = config["runtime_packages"].get(platform_key)
    if runtime_info is None:
        raise RuntimeError(f"Unsupported platform: {platform_key}")

    python_root = args.python_root.expanduser().resolve()
    validate_python_root(python_root, platform_key)

    target_dir = args.target.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / runtime_info["filename"]

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(python_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(python_root)
            if should_skip(path, relative):
                continue
            archive.write(path, relative.as_posix())

    print(f"[CharAIface] Runtime archive written: {archive_path}")
    return 0


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_python_root(python_root: Path, platform_key: str) -> None:
    if not python_root.is_dir():
        raise FileNotFoundError(f"Python runtime root not found: {python_root}")

    python_path = python_root / ("python.exe" if platform_key.startswith("windows") else "bin/python")
    if not python_path.is_file():
        raise FileNotFoundError(f"Runtime Python executable not found: {python_path}")


def should_skip(path: Path, relative: Path) -> bool:
    if path.name in EXCLUDED_NAMES:
        return True
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def detect_platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        return "macos-x64"
    if system == "windows":
        return "windows-x64"
    raise RuntimeError(f"Unsupported OS: {platform.system()}")


if __name__ == "__main__":
    raise SystemExit(main())
