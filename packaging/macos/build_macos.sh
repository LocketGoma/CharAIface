#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
SPEC_PATH="$SCRIPT_DIR/CharAIface.spec"
DIST_PATH="$PROJECT_ROOT/dist/macos"
WORK_PATH="$PROJECT_ROOT/build/macos"

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

"$VENV_PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST_PATH" \
  --workpath "$WORK_PATH" \
  "$SPEC_PATH"

echo "[CharAIface] macOS build completed: $DIST_PATH/CharAIface.app"
