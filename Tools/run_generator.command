#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/run_generator.sh" "$@"
status=$?

if [[ $status -ne 0 ]]; then
    echo
    echo "Character Set Generator exited with status $status."
    read -r -p "Press Enter to close this window..."
fi

exit "$status"
