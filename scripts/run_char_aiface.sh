#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -f ".venv/bin/activate" ]]; then
  source ".venv/bin/activate"
fi

if command -v python >/dev/null 2>&1; then
  python ./scripts/run_char_aiface.py "$@"
else
  python3 ./scripts/run_char_aiface.py "$@"
fi
