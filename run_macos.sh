#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

INSTALL_SCRIPT="$SCRIPT_DIR/scripts/install_macos.sh"
CHECK_ENV_SCRIPT="$SCRIPT_DIR/scripts/check_env.py"
SCRIPT_LAUNCHER_SH="$SCRIPT_DIR/scripts/run_char_aiface.sh"
ROOT_LAUNCHER_SH="$SCRIPT_DIR/run_char_aiface.sh"
SCRIPT_LAUNCHER_PY="$SCRIPT_DIR/scripts/run_char_aiface.py"
ROOT_LAUNCHER_PY="$SCRIPT_DIR/run_char_aiface.py"

NEEDS_INSTALL=0

if [[ ! -f ".venv/bin/activate" ]]; then
    NEEDS_INSTALL=1
elif [[ ! -f "requirements.txt" ]]; then
    echo "[ERROR] requirements.txt was not found."
    echo "        Make sure this file is placed in the CharAIface project root."
    exit 1
elif [[ -f "$CHECK_ENV_SCRIPT" ]]; then
    # If environment check fails, try reinstalling once.
    if ! .venv/bin/python "$CHECK_ENV_SCRIPT" >/dev/null 2>&1; then
        NEEDS_INSTALL=1
    fi
else
    echo "[WARN] scripts/check_env.py was not found. Skipping environment check."
fi

if [[ "$NEEDS_INSTALL" -eq 1 ]]; then
    echo "[CharAIface] Install is required. Running macOS installer..."

    if [[ ! -f "$INSTALL_SCRIPT" ]]; then
        echo "[ERROR] macOS installer was not found: scripts/install_macos.sh"
        exit 1
    fi

    bash "$INSTALL_SCRIPT"
fi

if [[ -f "$SCRIPT_LAUNCHER_SH" ]]; then
    exec bash "$SCRIPT_LAUNCHER_SH" "$@"
elif [[ -f "$ROOT_LAUNCHER_SH" ]]; then
    exec bash "$ROOT_LAUNCHER_SH" "$@"
elif [[ -f "$SCRIPT_LAUNCHER_PY" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    exec python "$SCRIPT_LAUNCHER_PY" "$@"
elif [[ -f "$ROOT_LAUNCHER_PY" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    exec python "$ROOT_LAUNCHER_PY" "$@"
else
    echo "[ERROR] CharAIface launcher was not found."
    echo "        Checked:"
    echo "        - scripts/run_char_aiface.sh"
    echo "        - run_char_aiface.sh"
    echo "        - scripts/run_char_aiface.py"
    echo "        - run_char_aiface.py"
    exit 1
fi
