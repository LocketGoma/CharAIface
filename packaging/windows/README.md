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

If PowerShell blocks the script with `PSSecurityException` or
`UnauthorizedAccess`, run it with a process-local execution policy bypass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build_windows.ps1
```

Alternatively, in the current PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\packaging\windows\build_windows.ps1
```

If Windows marked the script as downloaded from the internet, unblock the file
once and retry:

```powershell
Unblock-File .\packaging\windows\build_windows.ps1
```

Expected output:

```text
dist\windows\CharAIface\
  CharAIface.exe
  app\
```

## Release Archive

The current Windows release artifact is a `.7z` archive, not an installer.
After the PyInstaller build succeeds, create the archive from the generated
one-folder app contents:

```powershell
$ArchivePath = Resolve-Path .\dist
$ArchivePath = Join-Path $ArchivePath "CharAIface-windows.7z"
if (Test-Path $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath -Force
}
Push-Location .\dist\windows\CharAIface
& ..\..\..\Tools\7-Zip\7z.exe a -t7z -mx=9 $ArchivePath .\*
Pop-Location
```

Expected output:

```text
dist\CharAIface-windows.7z
```

The archive should contain `CharAIface.exe` and `app\` at the archive root.
Users extract the archive and run `CharAIface.exe`; they do not need to install
Python separately.

The Inno Setup script is kept as optional scaffolding, but it is not the current
release path.

## Smoke Test

Run:

```powershell
.\dist\windows\CharAIface\CharAIface.exe
```

Then verify the checklist in `packaging/README.md`.
