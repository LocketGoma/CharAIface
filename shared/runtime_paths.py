from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "CharAIface"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_root() -> Path:
    """Return the root that contains bundled runtime resources.

    In source checkouts this is the repository root. In PyInstaller builds this
    is the extraction/content root exposed through sys._MEIPASS.
    """
    if is_frozen() and sys.platform == "darwin":
        executable = Path(sys.executable).resolve()
        contents_dir = next(
            (
                parent
                for parent in executable.parents
                if parent.name == "Contents" and parent.parent.suffix == ".app"
            ),
            None,
        )
        if contents_dir is not None:
            resources_dir = contents_dir / "Resources"
            if resources_dir.exists():
                return resources_dir.resolve()

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return runtime_root() / "resources" / Path(*parts)


def user_documents_root() -> Path:
    if sys.platform == "win32":
        documents = _windows_known_folder_documents()
        if documents is not None:
            return documents
        return Path.home() / "Documents"

    return Path.home() / "Documents"


def user_data_root() -> Path:
    """Return the writable per-user app data directory."""
    override = os.environ.get("CHARAIFACE_USER_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "win32":
        return user_documents_root() / APP_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser() / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def user_resource_path(*parts: str) -> Path:
    return user_data_root() / Path(*parts)


def ensure_user_data_dirs() -> Path:
    root = user_data_root()
    root.mkdir(parents=True, exist_ok=True)
    user_resource_path("characters").mkdir(parents=True, exist_ok=True)
    user_resource_path("chat_sessions").mkdir(parents=True, exist_ok=True)
    return root


def _windows_known_folder_documents() -> Path | None:
    if sys.platform != "win32":
        return None

    try:
        import ctypes
    except Exception:
        return None

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    fid = GUID(
        0xFDD39AD0,
        0x238F,
        0x46AF,
        (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
    )
    path_ptr = ctypes.c_void_p()

    try:
        result = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(fid),
            0,
            None,
            ctypes.byref(path_ptr),
        )
        if result != 0 or not path_ptr.value:
            return None
        return Path(ctypes.wstring_at(path_ptr.value))
    except Exception:
        return None
    finally:
        if path_ptr.value:
            try:
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            except Exception:
                pass
