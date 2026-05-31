#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "[CharAIface] macOS install started."
echo "[CharAIface] Project root: $PROJECT_ROOT"

PYTHON_BIN=""

if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "[ERROR] Python 3 was not found."
    echo "        Please install Python 3.12 or newer, then run this script again."
    exit 1
fi

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
PYTHON_MAJOR="$($PYTHON_BIN -c 'import sys; print(sys.version_info.major)')"
PYTHON_MINOR="$($PYTHON_BIN -c 'import sys; print(sys.version_info.minor)')"

echo "[CharAIface] Python: $PYTHON_BIN ($PYTHON_VERSION)"

if [[ "$PYTHON_MAJOR" -lt 3 ]]; then
    echo "[ERROR] Python 3 is required."
    exit 1
fi

if [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 12 ]]; then
    echo "[WARN] Python 3.12+ is recommended. Current version: $PYTHON_VERSION"
    echo "       Install may still continue, but unsupported issues can occur."
fi

if [[ ! -d ".venv" ]]; then
    echo "[CharAIface] Creating virtual environment: .venv"
    "$PYTHON_BIN" -m venv .venv
else
    echo "[CharAIface] Existing virtual environment found: .venv"
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"

echo "[CharAIface] Upgrading pip..."
python -m pip install --upgrade pip

if [[ ! -f "requirements.txt" ]]; then
    echo "[ERROR] requirements.txt was not found."
    echo "        Make sure you are running this script from the CharAIface project root."
    exit 1
fi

echo "[CharAIface] Installing dependencies..."
pip install -r requirements.txt

if [[ -f "scripts/check_env.py" ]]; then
    echo "[CharAIface] Running environment check..."
    python scripts/check_env.py
else
    echo "[WARN] scripts/check_env.py was not found. Skipping environment check."
fi

echo ""
echo "[CharAIface] Install completed."
echo "Run the app with:"
echo "  ./run_macos.sh"
