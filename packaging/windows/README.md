# Windows Packaging

Windows packaging starts with a self-contained PyInstaller one-folder build. The
folder contains the Python runtime and project dependencies.

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

## Installer

For alpha testing, the `dist\windows\CharAIface` folder can still be zipped.
For a normal installer, use Inno Setup with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build_installer.ps1
```

Expected output:

```text
dist\windows-installer\CharAIfaceSetup.exe
```

The installer includes the full PyInstaller output; users do not need to install
Python separately.

## Smoke Test

Run:

```powershell
.\dist\windows\CharAIface\CharAIface.exe
```

Then verify the checklist in `packaging/README.md`.
