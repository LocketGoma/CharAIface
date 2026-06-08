#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
SPEC_PATH="$SCRIPT_DIR/CharAIfaceInstaller.spec"
DIST_PATH="$PROJECT_ROOT/dist/bootstrap"
WORK_PATH="$PROJECT_ROOT/build/bootstrap-installer/pyinstaller"
PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/pyinstaller-config/bootstrap"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[ERROR] .venv Python was not found: $VENV_PYTHON"
  exit 1
fi

if ! "$VENV_PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "[ERROR] PyInstaller is not installed in .venv."
  echo "Install it with: .venv/bin/python -m pip install pyinstaller"
  exit 1
fi

cd "$PROJECT_ROOT"
mkdir -p "$PYINSTALLER_CONFIG_DIR"
export PYINSTALLER_CONFIG_DIR

"$VENV_PYTHON" "$PROJECT_ROOT/packaging/bootstrap/build_installer_payload.py"

"$VENV_PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  "$SPEC_PATH"

echo "[CharAIface] Bootstrap installer built: $DIST_PATH/CharAIfaceInstaller"
