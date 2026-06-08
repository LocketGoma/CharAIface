from __future__ import annotations

import argparse
import json
import platform
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "packaging" / "bootstrap" / "installer_config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bundle the bootstrap installer with a local runtime archive."
    )
    parser.add_argument("--installer", type=Path, default=None)
    parser.add_argument("--runtime-archive", type=Path, required=True)
    parser.add_argument("--platform", dest="platform_key", default=None)
    parser.add_argument(
        "--target",
        type=Path,
        default=ROOT / "dist" / "release",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    platform_key = args.platform_key or detect_platform_key()
    runtime_info = config["runtime_packages"].get(platform_key)
    if runtime_info is None:
        raise RuntimeError(f"Unsupported platform: {platform_key}")

    runtime_archive = args.runtime_archive.expanduser().resolve()
    if not runtime_archive.is_file():
        raise FileNotFoundError(f"Runtime archive not found: {runtime_archive}")
    if runtime_archive.name != runtime_info["filename"]:
        raise RuntimeError(
            "Runtime archive filename must match installer_config.json: "
            f"{runtime_info['filename']}"
        )

    installer = (args.installer or default_installer_path()).expanduser().resolve()
    if not installer.is_file():
        raise FileNotFoundError(f"Installer executable not found: {installer}")

    target_dir = args.target.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = target_dir / f"CharAIface-bootstrap-{platform_key}.zip"

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(installer, installer.name)
        archive.write(runtime_archive, runtime_archive.name)
        archive.writestr(
            "README.txt",
            "CharAIface installer bundle\n\n"
            "1. Extract this zip file.\n"
            f"2. Run {installer.name}.\n"
            "3. Choose the install location when prompted.\n"
            "4. The installer will use the runtime archive included next to it.\n",
        )

    print(f"[CharAIface] Release bundle written: {bundle_path}")
    return 0


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def default_installer_path() -> Path:
    suffix = ".exe" if platform.system().lower() == "windows" else ""
    return ROOT / "dist" / "bootstrap" / f"CharAIfaceInstaller{suffix}"


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
