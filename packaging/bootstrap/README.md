# CharAIface Bootstrap Installer

This folder contains the bootstrap-installer direction for release builds.

The intended release UX is:

1. The user downloads one platform zip from GitHub Releases.
2. The user extracts the zip and runs the included installer.
3. The installer uses the matching runtime archive placed next to it.
4. The installer combines that runtime with its embedded app payload.
5. The user runs the reconstructed local CharAIface launcher.

The GitHub Release page should expose one user-facing zip per platform. Runtime
archives can still be hosted separately as a fallback, but normal users should
not need to choose or download them manually.

## Files

- `installer.py`: stdlib-only bootstrap installer logic.
- `installer_config.json`: release URL, runtime package filenames, checksums, and launcher paths.
- `build_installer_payload.py`: creates the embedded app/resource payload.
- `build_release_bundle.py`: zips the installer executable with a local runtime archive.
- `CharAIfaceInstaller.spec`: PyInstaller one-file spec for the small installer.
- `build_installer.sh`: macOS/Linux helper for building the installer executable.

## Runtime Archive Contract

The runtime archive is platform-specific and extracted into:

```text
<install_dir>/runtime/
```

The current default launchers expect:

```text
macOS:
  <install_dir>/runtime/bin/python
  <install_dir>/app/scripts/run_char_aiface.py

Windows:
  <install_dir>/runtime/python.exe
  <install_dir>/app/scripts/run_char_aiface.py
```

This means the runtime archive should contain a relocatable Python runtime with
all project dependencies already installed.

## Installer Payload

The installer embeds:

- `backend/`
- `desktop/`
- `shared/`
- `scripts/`
- `resources/`
- project docs and metadata

It excludes user data such as sessions, exports, file-analysis output, logs,
caches, and secrets.

Builtin characters are packaged as root-level `.charpack` files under
`resources/builtin/`. Source image optimization is intentionally not performed
during packaging; resized images should be prepared before building the
`.charpack`.

## Build

From the repository root:

```bash
./packaging/bootstrap/build_installer.sh
```

On Windows:

```powershell
.\packaging\bootstrap\build_installer.ps1
```

Expected output:

```text
dist/bootstrap/CharAIfaceInstaller
```

Then bundle the installer with the matching runtime archive:

```bash
.venv/bin/python packaging/bootstrap/build_release_bundle.py \
  --runtime-archive path/to/charaiface-runtime-macos-arm64.zip
```

Expected output:

```text
dist/release/CharAIface-bootstrap-macos-arm64.zip
```

Before a real release, update `installer_config.json` with:

- the actual GitHub release URL
- runtime archive filenames
- SHA-256 checksums

## Dry Run

The source installer can be checked without downloading or installing:

```bash
.venv/bin/python packaging/bootstrap/installer.py --dry-run \
  --payload-dir build/bootstrap-installer/payload \
  --config packaging/bootstrap/installer_config.json
```
