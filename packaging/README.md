# CharAIface Packaging

This folder contains alpha packaging scaffolding for CharAIface.

The release goal is a normal self-contained desktop package. Users should not
need to install Python, create a virtual environment, or download a separate
runtime package. The release artifact includes the Python runtime and all
project dependencies.

## Current Direction

The preferred alpha target is:

- macOS: PyInstaller `.app` bundle wrapped in a DMG.
- Windows: PyInstaller one-folder build wrapped in a `.7z` archive.

This is intentionally larger than a bootstrap package, but it is simpler and
more typical for Python desktop apps at this stage.

Recommended order:

1. Build the platform PyInstaller output
2. Smoke-test the generated app/folder
3. Wrap the output in the platform release format
4. Upload that artifact as the user-facing GitHub Release download

CharAIface includes PySide6, FastAPI, pandas, openpyxl, tree-sitter packages,
and resource files. A self-contained package will be larger than a native app,
but it avoids asking users to install Python or manage dependencies.

## Packaging Direction

The macOS flow is:

```text
build_macos.sh
  creates dist/macos/CharAIface.app

build_dmg.sh
  creates dist/macos/CharAIface-macos.dmg
```

The Windows flow is:

```text
build_windows.ps1
  creates dist/windows/CharAIface/

7-Zip
  reads dist/windows/CharAIface/
  creates dist/CharAIface-windows.7z
```

## Included Runtime Files

The PyInstaller specs include:

- `scripts/run_char_aiface.py`
- `desktop/`
- `backend/`
- `shared/`
- `resources/`
- `README.md`
- `CHARPACK.md`
- `LICENSE`

Default built-in character `.charpack` files are tracked under
`resources/characters/` and copied into the packaged `resources/builtin/`
directory during the packaging asset preparation step. The private
`resources/builtin/` source folder can remain outside source control.

Packaged builds copy `resources/data/settings.json.example` to both
`resources/data/settings.json` and `resources/data/settings.json.example`.
The template is intentionally English-based so release builds start in English
without a build-time settings rewrite step.

The specs must not include:

- `.git/`
- `.venv/`
- `.env`
- user secrets
- user API keys
- generated `__pycache__/`
- `.pytest_cache/`
- temporary build output

## Runtime Path Notes

Packaged builds use `shared.runtime_paths` to resolve bundled resources. In
source checkouts this points at the repository root. In PyInstaller builds it
points at PyInstaller's bundled content root.

The launcher uses `scripts/run_char_aiface.py`.

In source mode it starts the backend with:

```text
python -m uvicorn backend.app.main:app
```

In frozen mode it starts a second copy of the packaged executable with:

```text
CharAIface --backend-only
```

The desktop UI runs in the primary process.

## Build Checklist

After building, manually verify:

- App launches without a system Python install
- Backend health check works
- Default character appears
- Settings opens
- Local AI status is shown
- Missing Ollama state is handled cleanly
- TXT/MD/CSV/XLSX/source files can be attached
- File-analysis answers use tool results
- Assistant answers can be exported as TXT/MD/CSV/PDF
- Export link opens the file
- `.charpack` import works
- `.charpack` export works for user packs
- Settings persist after restart
- `.env`, API keys, sessions, and local user data were not accidentally bundled

## Known Alpha Limitations

- macOS signing and notarization are not configured yet.
- Windows installer signing is not configured because the current release path is `.7z`.
- Packaged user data is stored outside the app bundle/folder through
  `shared.runtime_paths.app_data_root()`. Source/development runs keep writable
  data inside the repository.
