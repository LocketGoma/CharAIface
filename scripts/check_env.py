from __future__ import annotations

import importlib.metadata
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.local_ai.ollama_manager import _find_ollama_cli

REQUIRED_DIRS: list[str] = [
    "backend",
    "desktop",
    "shared",
    "resources",
]

OPTIONAL_DIRS: list[str] = [
]


def _ok(message: str) -> None:
    print(f"[OK] {message}")


def _warn(message: str) -> None:
    print(f"[WARN] {message}")


def _error(message: str) -> None:
    print(f"[ERROR] {message}")


def _check_python() -> bool:
    version = sys.version_info
    print(f"[CharAIface] Python: {sys.version}")
    print(f"[CharAIface] Platform: {platform.platform()}")

    if version.major != 3:
        _error("Python 3 is required.")
        return False

    if version.minor < 12:
        _warn("Python 3.12+ is recommended. Current Python may work, but is not the primary target.")
    else:
        _ok("Python version looks good.")

    return True


def _normalize_requirement_name(raw: str) -> str | None:
    line = raw.strip()

    if not line or line.startswith("#"):
        return None

    if line.startswith(("-", "--")):
        return None

    line = line.split("#", 1)[0].strip()
    if not line:
        return None

    line = line.split(";", 1)[0].strip()
    line = re.split(r"\[", line, maxsplit=1)[0].strip()
    name = re.split(r"\s*(?:==|>=|<=|~=|!=|>|<)\s*", line, maxsplit=1)[0].strip()
    name = name.split(" @ ", 1)[0].strip()

    if not name:
        return None

    return name


def _read_requirement_names() -> list[str]:
    if not REQUIREMENTS_FILE.exists():
        _error("requirements.txt was not found.")
        _error(f"Expected path: {REQUIREMENTS_FILE}")
        raise FileNotFoundError(REQUIREMENTS_FILE)

    names: list[str] = []

    for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        name = _normalize_requirement_name(line)
        if name:
            names.append(name)

    unique_names: list[str] = []
    seen: set[str] = set()

    for name in names:
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        unique_names.append(name)

    return unique_names


def _check_requirements() -> bool:
    try:
        requirement_names = _read_requirement_names()
    except FileNotFoundError:
        return False

    if not requirement_names:
        _warn("requirements.txt exists, but no package names were detected.")
        return True

    success = True

    for package_name in requirement_names:
        try:
            version = importlib.metadata.version(package_name)
            _ok(f"Package installed: {package_name} ({version})")
        except importlib.metadata.PackageNotFoundError:
            _error(f"Package missing: {package_name}")
            success = False
        except Exception as exc:
            _error(f"Package check failed: {package_name} ({exc})")
            success = False

    return success


def _check_project_layout() -> bool:
    success = True

    for relative_path in REQUIRED_DIRS:
        path = PROJECT_ROOT / relative_path
        if path.exists() and path.is_dir():
            _ok(f"Required directory found: {relative_path}")
        else:
            _error(f"Required directory missing: {relative_path}")
            success = False

    for relative_path in OPTIONAL_DIRS:
        path = PROJECT_ROOT / relative_path
        if path.exists() and path.is_dir():
            _ok(f"Optional directory found: {relative_path}")
        else:
            _warn(f"Optional directory missing: {relative_path}")

    run_script = PROJECT_ROOT / "scripts" / "run_char_aiface.py"
    if run_script.exists():
        _ok("Launcher found: run_char_aiface.py")
    else:
        _error("Launcher missing: run_char_aiface.py")
        success = False

    if REQUIREMENTS_FILE.exists():
        _ok("requirements.txt found.")
    else:
        _error("requirements.txt missing.")
        success = False

    return success


def _check_character_packs() -> bool:
    success = True
    user_characters_dir = PROJECT_ROOT / "resources" / "characters"
    default_charpack = user_characters_dir / "default_sakura.charpack"

    if default_charpack.is_file():
        _ok(f"Built-in character pack found: {default_charpack.relative_to(PROJECT_ROOT)}")
    else:
        _error(f"Built-in character pack missing: {default_charpack.relative_to(PROJECT_ROOT)}")
        success = False

    if not user_characters_dir.exists():
        _warn("resources/characters/ directory was not found.")
        _warn("This is allowed for development; it will be created on first launch when needed.")
        return success

    folder_packs = [
        path
        for path in user_characters_dir.iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    ]
    charpacks = [
        path
        for path in user_characters_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".charpack"
    ]

    if folder_packs or charpacks:
        _ok(f"Tracked character packs found: folders={len(folder_packs)}, charpacks={len(charpacks)}")
        return success

    _warn("No tracked character packs were found under resources/characters/.")
    _warn("This is allowed because the built-in character pack is packaged separately.")
    return success


def _is_port_open(host: str, port: int, timeout_seconds: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _check_backend_port() -> None:
    if _is_port_open("127.0.0.1", 10420):
        _warn("Port 10420 is already in use.")
        _warn("If CharAIface is not running, a previous backend process may still be alive.")
    else:
        _ok("Backend port 10420 is available.")


def _check_ollama() -> None:
    cli_path = _find_ollama_cli()
    if cli_path is None:
        _warn("Ollama was not found in PATH or standard install locations.")
        _warn("Local AI will not work until Ollama is installed and available.")
        return

    try:
        result = subprocess.run(
            [cli_path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except FileNotFoundError:
        _warn(f"Ollama executable disappeared before version check: {cli_path}")
        _warn("Local AI will not work until Ollama is installed and available.")
        return
    except Exception as exc:
        _warn(f"Ollama check failed for {cli_path}: {exc}")
        return

    output = (result.stdout or result.stderr or "").strip()
    if result.returncode == 0:
        _ok(f"Ollama found: {output} ({cli_path})")
    else:
        _warn(f"Ollama command returned non-zero exit code from {cli_path}: {output}")


def main() -> int:
    print("[CharAIface] Environment check started.")
    print(f"[CharAIface] Project root: {PROJECT_ROOT}")

    success = True
    success = _check_python() and success
    success = _check_project_layout() and success
    success = _check_requirements() and success

    success = _check_character_packs() and success
    _check_backend_port()
    _check_ollama()

    print("")

    if success:
        print("[CharAIface] Environment check completed.")
        return 0

    print("[CharAIface] Environment check failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
