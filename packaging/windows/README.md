# Windows Packaging

Windows packaging starts with a PyInstaller one-folder build.

## Requirements

- Windows 10 or newer
- Python matching the project requirement, preferably Python 3.12
- Project dependencies installed in `.venv`
- PyInstaller installed in the active environment

Install PyInstaller if needed:

```powershell
.\.venv\Scripts\python -m pip install pyinstaller
```

## Build

From the project root:

```powershell
.\packaging\windows\build_windows.ps1
```

Expected output:

```text
dist\windows\CharAIface\
  CharAIface.exe
  _internal\
```

## Distribution

For alpha testing, zip the `dist\windows\CharAIface` folder.

Installer support can be added later with Inno Setup or NSIS after the one-folder
build is stable.

## Smoke Test

Run:

```powershell
.\dist\windows\CharAIface\CharAIface.exe
```

Then verify the checklist in `packaging/README.md`.
