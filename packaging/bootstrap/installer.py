from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


CONFIG_NAME = "installer_config.json"
PAYLOAD_DIR_NAME = "payload"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install CharAIface runtime and app payload.")
    parser.add_argument("--install-dir", type=Path, default=None)
    parser.add_argument("--runtime-archive", type=Path, default=None)
    parser.add_argument("--runtime-url", default=None)
    parser.add_argument("--runtime-sha256", default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--payload-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    platform_key = detect_platform_key()
    runtime_info = config["runtime_packages"].get(platform_key)
    if not runtime_info:
        raise RuntimeError(f"Unsupported platform: {platform_key}")

    install_dir = choose_install_dir(config, args.install_dir)
    payload_dir = resolve_payload_dir(args.payload_dir)
    runtime_archive = resolve_runtime_archive(args.runtime_archive, runtime_info)
    runtime_url = args.runtime_url or build_runtime_url(config, runtime_info)
    runtime_sha256 = args.runtime_sha256 or runtime_info.get("sha256", "")

    print(f"[CharAIface] Platform: {platform_key}")
    print(f"[CharAIface] Install directory: {install_dir}")
    if runtime_archive is not None:
        print(f"[CharAIface] Runtime archive: {runtime_archive}")
        validate_runtime_archive_file(runtime_archive)
    else:
        print(f"[CharAIface] Runtime URL: {runtime_url}")
    print(f"[CharAIface] Payload directory: {payload_dir}")

    if args.dry_run:
        print("[CharAIface] Dry run complete. No files were changed.")
        return 0

    install_dir.mkdir(parents=True, exist_ok=True)

    if runtime_archive is not None:
        verify_runtime_archive(runtime_archive, runtime_sha256, allow_missing_checksum=True)
        install_runtime(runtime_archive, install_dir)
    else:
        if runtime_sha256 == "TODO":
            raise RuntimeError(
                "Runtime checksum is not configured. Set sha256 in installer_config.json "
                "or pass --runtime-sha256."
            )
        with tempfile.TemporaryDirectory(prefix="charaiface-install-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            downloaded_runtime_archive = temp_dir / runtime_info["filename"]
            download_file(runtime_url, downloaded_runtime_archive)
            verify_runtime_archive(
                downloaded_runtime_archive,
                runtime_sha256,
                allow_missing_checksum=False,
            )
            install_runtime(downloaded_runtime_archive, install_dir)

    install_payload(payload_dir, install_dir)
    write_launchers(config, install_dir)
    write_install_manifest(config, platform_key, install_dir)

    print("[CharAIface] Installation complete.")
    return 0


def load_config(config_path: Path | None) -> dict[str, Any]:
    path = config_path or resource_root() / CONFIG_NAME
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resource_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent


def resolve_payload_dir(payload_dir: Path | None) -> Path:
    path = payload_dir or resource_root() / PAYLOAD_DIR_NAME
    if not path.exists():
        raise FileNotFoundError(f"Installer payload not found: {path}")
    return path


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


def default_install_dir(config: dict[str, Any]) -> Path:
    install_dir_name = config.get("install_dir_name", "CharAIface")
    if platform.system().lower() == "windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / install_dir_name
    return Path.home() / "Applications" / install_dir_name


def choose_install_dir(config: dict[str, Any], explicit_install_dir: Path | None) -> Path:
    if explicit_install_dir is not None:
        return explicit_install_dir.expanduser().resolve()

    default_dir = default_install_dir(config)
    if sys.stdin is not None and sys.stdin.isatty():
        response = input(f"Install directory [{default_dir}]: ").strip()
        if response:
            return Path(response).expanduser().resolve()

    return default_dir.expanduser().resolve()


def resolve_runtime_archive(
    explicit_runtime_archive: Path | None,
    runtime_info: dict[str, Any],
) -> Path | None:
    candidates: list[Path] = []
    if explicit_runtime_archive is not None:
        candidates.append(explicit_runtime_archive)

    filename = runtime_info["filename"]
    root = resource_root()
    candidates.extend(
        [
            root / filename,
            root / "runtime" / filename,
            Path(sys.argv[0]).resolve().parent / filename,
        ]
    )

    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if path.is_file():
            return path
    return None


def validate_runtime_archive_file(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise RuntimeError(f"Runtime archive is not a valid zip file: {path}")


def build_runtime_url(config: dict[str, Any], runtime_info: dict[str, Any]) -> str:
    release_base_url = str(config["release_base_url"]).rstrip("/")
    return f"{release_base_url}/{runtime_info['filename']}"


def download_file(url: str, target: Path) -> None:
    print(f"[CharAIface] Downloading runtime: {url}")
    with urllib.request.urlopen(url) as response, target.open("wb") as file:
        shutil.copyfileobj(response, file)


def verify_runtime_archive(
    path: Path,
    expected_sha256: str,
    *,
    allow_missing_checksum: bool,
) -> None:
    if expected_sha256 == "TODO":
        if allow_missing_checksum:
            print("[CharAIface] Runtime checksum is not configured; skipping local archive verification.")
            return
        raise RuntimeError(
            "Runtime checksum is not configured. Set sha256 in installer_config.json "
            "or pass --runtime-sha256."
        )

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    actual = digest.hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise RuntimeError(
            f"Runtime checksum mismatch: expected {expected_sha256}, got {actual}"
        )


def install_runtime(runtime_archive: Path, install_dir: Path) -> None:
    runtime_dir = install_dir / "runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)

    print(f"[CharAIface] Extracting runtime: {runtime_dir}")
    with zipfile.ZipFile(runtime_archive) as archive:
        archive.extractall(runtime_dir)


def install_payload(payload_dir: Path, install_dir: Path) -> None:
    app_source = payload_dir / "app"
    if not app_source.exists():
        raise FileNotFoundError(f"App payload not found: {app_source}")

    app_dir = install_dir / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)

    print(f"[CharAIface] Installing app payload: {app_dir}")
    shutil.copytree(app_source, app_dir)


def write_launchers(config: dict[str, Any], install_dir: Path) -> None:
    launcher_config = config["launcher"]["windows" if platform.system().lower() == "windows" else "macos"]
    launcher_name = launcher_config["launcher_name"]
    launcher_path = install_dir / launcher_name

    python_path = install_dir / launcher_config["python"]
    script_path = install_dir / launcher_config["script"]

    if platform.system().lower() == "windows":
        launcher_path.write_text(
            f'@echo off\r\n"{python_path}" "{script_path}" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher_path.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'"{python_path}" "{script_path}" "$@"\n',
            encoding="utf-8",
        )
        current_mode = launcher_path.stat().st_mode
        launcher_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[CharAIface] Launcher written: {launcher_path}")


def write_install_manifest(config: dict[str, Any], platform_key: str, install_dir: Path) -> None:
    manifest = {
        "app_id": config.get("app_id", "CharAIface"),
        "app_version": config.get("app_version"),
        "platform": platform_key,
    }
    (install_dir / "install_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
