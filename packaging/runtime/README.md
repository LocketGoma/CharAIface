# CharAIface Runtime Archives

This folder documents the standalone-runtime direction used by the bootstrap
installer.

## Target Shape

The installer extracts a runtime archive into:

```text
<install_dir>/runtime/
```

The extracted runtime must contain:

```text
macOS:
  <install_dir>/runtime/bin/python

Windows:
  <install_dir>/runtime/python.exe
```

All Python dependencies required by CharAIface should already be installed into
that runtime before the archive is created. Users should not need to install
Python, create a virtual environment, or run `pip`.

## Recommended Source Runtime

Use a relocatable standalone Python distribution per platform, then install the
project dependencies into that runtime.

For the alpha packaging track, the exact source distribution is still a release
decision. The runtime archive contract above is the stable part that the
installer relies on.

## Archive A Prepared Runtime

After preparing a platform runtime root, create the release archive:

```bash
.venv/bin/python packaging/runtime/build_runtime_archive.py \
  --python-root path/to/prepared-python-root
```

Expected output:

```text
dist/runtime/charaiface-runtime-<platform>.zip
```

The filename is read from `packaging/bootstrap/installer_config.json`, so the
runtime archive and installer stay aligned.

## Bundle With Installer

After building the installer executable:

```bash
.venv/bin/python packaging/bootstrap/build_release_bundle.py \
  --runtime-archive dist/runtime/charaiface-runtime-macos-arm64.zip
```

Expected output:

```text
dist/release/CharAIface-bootstrap-macos-arm64.zip
```

GitHub Releases should expose that zip as the normal user-facing download.
