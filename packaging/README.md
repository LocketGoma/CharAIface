# CharAIface Packaging

This folder contains alpha packaging scaffolding for CharAIface.

The release goal is a small bootstrap bundle: users download one zip file from
GitHub Releases, extract it, and run the included installer.  The installer uses
the runtime archive placed next to it, combines that runtime with the embedded
app payload, and creates the local runnable CharAIface installation.

## Current Direction

The preferred release target is the bootstrap installer in `packaging/bootstrap`.
The existing PyInstaller one-folder output remains useful for smoke tests,
runtime inspection, and emergency alpha builds.

Recommended order:

1. Build and test the bootstrap installer payload
2. Prepare OS-specific standalone runtime roots
3. Archive those runtimes with `packaging/runtime/build_runtime_archive.py`
4. Build a small installer executable
5. Bundle the installer executable and matching runtime archive into one zip
6. Upload only that zip as the user-facing GitHub Release download

Fat PyInstaller app bundles are intentionally not the final release shape.
CharAIface includes PySide6, FastAPI, pandas, tree-sitter packages, and resource
files; putting everything into the user-facing installer makes the installer too
large.

## Bootstrap Installer Direction

The bootstrap installer flow is:

```text
GitHub Release
  user downloads: CharAIface-bootstrap-<platform>.zip

Extracted bundle
  CharAIfaceInstaller
  charaiface-runtime-<platform>.zip

CharAIfaceInstaller
  detects OS/architecture
  uses the adjacent runtime archive
  falls back to runtime download only when no local archive is present
  verifies SHA-256 checksum
  extracts runtime into the install directory
  copies embedded app code/resources
  writes a local launcher

User
  runs the reconstructed local launcher
```

The runtime archive can still be hosted as a release asset or another static
download URL as a fallback, but the preferred alpha release shape is one zip
that already contains both the installer and runtime archive.

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

- Runtime archive generation is not finalized yet.
- Installer UI is not configured yet; the current bootstrap installer is CLI-first
  and prompts for an install directory when run interactively.
- macOS signing and notarization are not configured yet.
- DMG generation is documented as a follow-up step.
- App data currently follows the existing resource/data layout; this may be
  split into a user data directory before public release.
