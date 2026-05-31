from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from PySide6.QtGui import QIcon


APP_ICON_STEM = "char_aiface"
SOURCE_ICON_NAME = f"{APP_ICON_STEM}.png"
WINDOWS_ICON_NAME = f"{APP_ICON_STEM}.ico"
MACOS_ICON_NAME = f"{APP_ICON_STEM}.icns"
FAVICON_NAME = "favicon.ico"


_ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)
_ICO_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)
_ICNS_SIZES: tuple[int, ...] = (16, 32, 64, 128, 256, 512, 1024)


def resolve_project_root(reference_file: str | Path | None = None) -> Path:
    """Return the project/resource root for source and frozen execution.

    Development layout:
        <project>/desktop/utils/app_icon.py -> parents[2] == <project>

    PyInstaller layout:
        sys._MEIPASS is used when available.  This is intentionally conservative;
        external release layouts can still place resources next to the bundle and
        pass that path explicitly later if needed.
    """
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()

    if reference_file is None:
        return Path(__file__).resolve().parents[2]

    return Path(reference_file).resolve().parents[1]


def icon_dir(project_root: Path) -> Path:
    return project_root / "resources" / "icons"


def source_icon_path(project_root: Path) -> Path:
    return icon_dir(project_root) / SOURCE_ICON_NAME


def generated_icon_paths(project_root: Path) -> dict[str, Path]:
    icons = icon_dir(project_root)
    return {
        "png": icons / SOURCE_ICON_NAME,
        "ico": icons / WINDOWS_ICON_NAME,
        "icns": icons / MACOS_ICON_NAME,
        "favicon": icons / FAVICON_NAME,
    }


def _is_outdated(target: Path, source: Path) -> bool:
    if not target.exists():
        return True
    try:
        return target.stat().st_mtime < source.stat().st_mtime
    except OSError:
        return True


def _load_source_image(source: Path):
    from PIL import Image

    image = Image.open(source)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    return image


def _resized_images(image, sizes: Iterable[int]):
    from PIL import Image

    result = []
    for size in sizes:
        result.append(image.resize((size, size), Image.Resampling.LANCZOS))
    return result


def ensure_generated_icons(project_root: Path) -> dict[str, Path]:
    """Generate .ico/.icns/favicon from resources/icons/char_aiface.png.

    This function is best-effort.  Missing Pillow, unsupported ICNS saving, or an
    absent source PNG should never block app startup.  The returned dictionary
    contains the standard paths whether generation succeeded or not.
    """
    paths = generated_icon_paths(project_root)
    source = paths["png"]

    if not source.exists():
        return paths

    icons = icon_dir(project_root)
    icons.mkdir(parents=True, exist_ok=True)

    try:
        image = _load_source_image(source)
    except Exception:
        return paths

    try:
        ico_path = paths["ico"]
        if _is_outdated(ico_path, source):
            image.save(ico_path, format="ICO", sizes=[(size, size) for size in _ICO_SIZES])
    except Exception:
        pass

    try:
        favicon_path = paths["favicon"]
        if _is_outdated(favicon_path, source):
            image.save(favicon_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    except Exception:
        pass

    try:
        icns_path = paths["icns"]
        if _is_outdated(icns_path, source):
            # Pillow can write ICNS when the platform build includes support.
            # Keep this best-effort so Windows/dev environments do not fail.
            image.save(icns_path, format="ICNS", sizes=[(size, size) for size in _ICNS_SIZES])
    except Exception:
        pass

    return paths


def load_app_icon(project_root: Path | None = None) -> QIcon:
    """Load the application icon.

    Priority:
        1. resources/icons/char_aiface.png
        2. generated resources/icons/char_aiface.ico
        3. generated resources/icons/char_aiface.icns
        4. empty QIcon, letting callers use Qt/OS fallback icons
    """
    root = project_root or resolve_project_root()
    paths = ensure_generated_icons(root)

    for key in ("png", "ico", "icns"):
        path = paths[key]
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon

    return QIcon()
