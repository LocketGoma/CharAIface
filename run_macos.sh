#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NEEDS_INSTALL=0

if [[ ! -f ".venv/bin/activate" ]]; then
    NEEDS_INSTALL=1
elif [[ ! -f "requirements.txt" ]]; then
    echo "[ERROR] requirements.txt was not found."
    echo "        Make sure this file is placed in the CharAIface project root."
    exit 1
else
    # If environment check fails, try reinstalling once.
    if ! .venv/bin/python scripts/check_env.py >/dev/null 2>&1; then
        NEEDS_INSTALL=1
    fi
fi

if [[ "$NEEDS_INSTALL" -eq 1 ]]; then
    echo "[CharAIface] Install is required. Running macOS installer..."
    bash "$SCRIPT_DIR/scripts/install_macos.sh"
fi

exec "$SCRIPT_DIR/scripts/run_char_aiface.sh" "$@"
