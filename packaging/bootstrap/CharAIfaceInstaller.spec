# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path(SPECPATH).resolve().parents[1]
ENTRY = ROOT / "packaging" / "bootstrap" / "installer.py"
CONFIG = ROOT / "packaging" / "bootstrap" / "installer_config.json"
PAYLOAD = ROOT / "build" / "bootstrap-installer" / "payload"


datas = [
    (str(CONFIG), "."),
]

if PAYLOAD.exists():
    datas.append((str(PAYLOAD), "payload"))


a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6",
        "pandas",
        "numpy",
        "openpyxl",
        "PIL",
        "fastapi",
        "uvicorn",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CharAIfaceInstaller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
)
