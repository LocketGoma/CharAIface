# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).resolve().parents[1]
ENTRY = ROOT / "scripts" / "run_char_aiface.py"


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


datas = [
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "CHARPACK.md"), "."),
    (str(ROOT / "LICENSE"), "."),
]
datas += add_resource_tree(ROOT / "resources" / "app", "resources/app")
datas += add_resource_tree(ROOT / "resources" / "builtin", "resources/builtin")
datas += add_resource_tree(ROOT / "resources" / "characters", "resources/characters")
datas += add_resource_tree(ROOT / "resources" / "data" / "search_context", "resources/data/search_context")
datas += add_resource_tree(ROOT / "resources" / "icons", "resources/icons")
datas += add_resource_tree(ROOT / "resources" / "locales", "resources/locales")
datas += add_resource_tree(ROOT / "resources" / "models", "resources/models")
datas += add_resource_tree(ROOT / "resources" / "themes", "resources/themes")
datas.append((str(ROOT / "resources" / "data" / "settings.json.example"), "resources/data"))

hiddenimports = []
for package_name in (
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.protocols",
    "uvicorn.lifespan",
    "fastapi",
    "pandas",
    "openpyxl",
    "pygments",
    "tree_sitter",
    "tree_sitter_language_pack",
    "charset_normalizer",
    "keyring",
):
    hiddenimports += collect_submodules(package_name)

datas += collect_data_files("tree_sitter_language_pack")


a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "resources" / "icons" / "char_aiface.icns"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
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
