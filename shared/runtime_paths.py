from __future__ import annotations

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
