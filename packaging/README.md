# CharAIface Packaging

This folder contains alpha packaging scaffolding for CharAIface.

The goal is to build packages that include the Python runtime and Python
dependencies so end users do not need to install Python, create a virtual
environment, or run `pip install`.

## Current Direction

The first packaging target is PyInstaller one-folder output.

Recommended order:

1. Windows one-folder build
2. Windows zip smoke test
3. macOS `.app` bundle build
4. macOS dmg packaging
5. Optional Windows installer with Inno Setup or NSIS

One-file builds are intentionally not the first target. CharAIface includes
PySide6, FastAPI, pandas, tree-sitter packages, and resource files; one-folder
output is easier to inspect and debug during alpha.

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

- Installer generation is not configured yet.
- macOS signing and notarization are not configured yet.
- DMG generation is documented as a follow-up step.
- App data currently follows the existing resource/data layout; this may be
  split into a user data directory before public release.
