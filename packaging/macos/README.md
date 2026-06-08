# macOS Packaging

macOS packaging uses a self-contained PyInstaller `.app` bundle wrapped in a DMG.
The `.app` contains the Python runtime and project dependencies.

## Requirements

- macOS
- Python matching the project requirement, preferably Python 3.12
- Project dependencies installed in `.venv`
- PyInstaller installed in the active environment

Install PyInstaller if needed:

```bash
.venv/bin/python -m pip install pyinstaller
```

## Build

From the project root:

```bash
./packaging/macos/build_macos.sh
```

Expected output:

```text
dist/macos/CharAIface.app
```

## DMG

After the `.app` bundle is smoke-tested, create the DMG:

```bash
./packaging/macos/build_dmg.sh
```

Expected output:

```text
dist/macos/CharAIface-macos.dmg
```

The DMG contains:

- `CharAIface.app`
- an `Applications` shortcut

## Signing and Notarization

Codesigning and notarization are not configured yet. For public distribution,
macOS signing and notarization should be handled before a stable release.

## Smoke Test

Run:

```bash
open dist/macos/CharAIface.app
```

Then verify the checklist in `packaging/README.md`.
