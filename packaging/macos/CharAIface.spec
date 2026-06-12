# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path


ROOT = Path(SPECPATH).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))

from pyinstaller_spec_common import COMMON_EXCLUDES, build_datas, build_hiddenimports

ENTRY = ROOT / "scripts" / "run_char_aiface.py"
BUILTIN_RESOURCE_ROOT = Path(
    os.environ.get("CHARAIFACE_PACKAGING_BUILTIN_ROOT", ROOT / "resources" / "builtin")
)
PACKAGING_SETTINGS_ROOT = Path(
    os.environ.get("CHARAIFACE_PACKAGING_SETTINGS_ROOT", ROOT / "resources" / "data")
)

datas = build_datas(
    ROOT,
    builtin_resource_root=BUILTIN_RESOURCE_ROOT,
    packaging_settings_root=PACKAGING_SETTINGS_ROOT,
)
hiddenimports = build_hiddenimports("keyring.backends.macOS")
excludes = COMMON_EXCLUDES


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
