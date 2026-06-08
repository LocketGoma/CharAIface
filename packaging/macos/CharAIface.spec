# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parents[1]
ENTRY = ROOT / "scripts" / "run_char_aiface.py"
BUILTIN_RESOURCE_ROOT = Path(
    os.environ.get("CHARAIFACE_PACKAGING_BUILTIN_ROOT", ROOT / "resources" / "builtin")
)


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


def add_resource_tree(source: Path, target: str) -> list[tuple[str, str]]:
    result = []
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


datas = [
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "CHARPACK.md"), "."),
    (str(ROOT / "LICENSE"), "."),
]
datas += add_resource_tree(ROOT / "resources" / "app", "resources/app")
datas += add_builtin_charpacks(BUILTIN_RESOURCE_ROOT, "resources/builtin")
datas += add_resource_tree(ROOT / "resources" / "characters", "resources/characters")
datas += add_resource_tree(ROOT / "resources" / "data" / "search_context", "resources/data/search_context")
datas += add_resource_tree(ROOT / "resources" / "icons", "resources/icons")
datas += add_resource_tree(ROOT / "resources" / "locales", "resources/locales")
datas += add_resource_tree(ROOT / "resources" / "models", "resources/models")
datas += add_resource_tree(ROOT / "resources" / "themes", "resources/themes")
datas.append((str(ROOT / "resources" / "data" / "settings.json.example"), "resources/data"))

hiddenimports = [
    "backend.app.main",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "keyring.backends.macOS",
    "keyring.backends.null",
]
hiddenimports += collect_submodules("pygments.lexers")
hiddenimports += collect_submodules("tree_sitter_language_pack")

datas += collect_data_files("tree_sitter_language_pack")

excludes = [
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


a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CharAIface",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=False,
    icon=str(ROOT / "resources" / "icons" / "char_aiface.icns"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name="CharAIface",
)

app = BUNDLE(
    coll,
    name="CharAIface.app",
    icon=str(ROOT / "resources" / "icons" / "char_aiface.icns"),
    bundle_identifier="com.locketgoma.charaiface",
    info_plist={
        "CFBundleDisplayName": "CharAIface",
        "CFBundleName": "CharAIface",
        "NSHighResolutionCapable": "True",
    },
)
