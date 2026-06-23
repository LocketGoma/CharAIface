# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


EXCLUDED_RESOURCE_NAMES = {
    ".DS_Store",
    ".gitkeep",
    "Thumbs.db",
}

EXCLUDED_RESOURCE_PARTS = {
    "__pycache__",
    "chat_sessions",
    "exports",
    "file_analysis",
    "logs",
}

COMMON_EXCLUDES = [
    "PySide6.QtCharts",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtOpenGL",
    "PySide6.QtPdf",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "numpy.tests",
    "pandas.tests",
    "pytest",
    "unittest",
]


def add_resource_tree(source: Path, target: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if not source.exists():
        return result

    for path in source.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(source)
        if path.name in EXCLUDED_RESOURCE_NAMES:
            continue
        if any(part in EXCLUDED_RESOURCE_PARTS for part in relative.parts):
            continue

        result.append((str(path), str(Path(target) / relative.parent)))

    return result


def add_builtin_charpacks(source: Path, target: str) -> list[tuple[str, str]]:
    if not source.exists():
        return []
    return [
        (str(path), target)
        for path in sorted(source.glob("*.charpack"))
        if path.is_file()
    ]


def build_datas(
    root: Path,
    *,
    builtin_resource_root: Path,
    packaging_settings_root: Path,
) -> list[tuple[str, str]]:
    datas = [
        (str(root / "README.md"), "."),
        (str(root / "CHARPACK.md"), "."),
        (str(root / "LICENSE"), "."),
    ]
    datas += add_resource_tree(root / "resources" / "addons", "resources/addons")
    datas += add_resource_tree(root / "resources" / "app", "resources/app")
    datas += add_builtin_charpacks(builtin_resource_root, "resources/builtin")
    datas += add_resource_tree(
        root / "resources" / "data" / "search_context",
        "resources/data/search_context",
    )
    datas += add_resource_tree(root / "resources" / "icons", "resources/icons")
    datas += add_resource_tree(root / "resources" / "locales", "resources/locales")
    datas += add_resource_tree(root / "resources" / "models", "resources/models")
    datas += add_resource_tree(root / "resources" / "themes", "resources/themes")
    datas += add_resource_tree(packaging_settings_root, "resources/data")
    datas += collect_data_files("tree_sitter_language_pack")
    return datas


def build_hiddenimports(keyring_backend: str) -> list[str]:
    hiddenimports = [
        "backend.app.main",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        keyring_backend,
        "keyring.backends.null",
    ]
    hiddenimports += collect_submodules("pygments.lexers")
    hiddenimports += collect_submodules("tree_sitter_language_pack")
    return hiddenimports
