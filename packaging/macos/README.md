# macOS Packaging

macOS packaging starts with a PyInstaller `.app` bundle build.

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

DMG generation is intentionally left as a follow-up step. For alpha packaging,
first confirm that the `.app` bundle runs correctly.

Possible later tools:

- `create-dmg`
- `hdiutil`

## Signing and Notarization

Codesigning and notarization are not configured yet. For public distribution,
macOS signing and notarization should be handled before a stable release.

## Smoke Test

Run:

```bash
open dist/macos/CharAIface.app
```

Then verify the checklist in `packaging/README.md`.
