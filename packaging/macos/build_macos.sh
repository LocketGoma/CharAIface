#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
SPEC_PATH="$SCRIPT_DIR/CharAIface.spec"
DIST_PATH="$PROJECT_ROOT/dist/macos"
WORK_PATH="$PROJECT_ROOT/build/macos"
PYINSTALLER_CONFIG_DIR="$PROJECT_ROOT/build/pyinstaller-config/macos"
PACKAGING_BUILTIN_SOURCE_ROOT="$PROJECT_ROOT/resources/builtin"
PACKAGING_BUILTIN_ROOT="$PROJECT_ROOT/build/packaging-assets/macos/resources/builtin"
PACKAGING_SETTINGS_ROOT="$PROJECT_ROOT/build/packaging-assets/macos/resources/data"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[ERROR] .venv Python was not found: $VENV_PYTHON"
  echo "Run ./run_macos.sh once or create the virtual environment first."
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

"$VENV_PYTHON" "$PROJECT_ROOT/packaging/prepare_packaging_assets.py" \
  --source "$PACKAGING_BUILTIN_SOURCE_ROOT" \
  --target "$PACKAGING_BUILTIN_ROOT" \
  --settings-source "$PROJECT_ROOT/resources/data/settings.json.example" \
  --settings-target "$PACKAGING_SETTINGS_ROOT"
export CHARAIFACE_PACKAGING_BUILTIN_ROOT="$PACKAGING_BUILTIN_ROOT"
export CHARAIFACE_PACKAGING_SETTINGS_ROOT="$PACKAGING_SETTINGS_ROOT"

"$VENV_PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  "$SPEC_PATH"

"$VENV_PYTHON" "$PROJECT_ROOT/packaging/verify_packaged_resources.py" \
  --resources-root "$DIST_PATH/CharAIface.app/Contents/Resources/resources"

echo "[CharAIface] macOS build completed: $DIST_PATH/CharAIface.app"
