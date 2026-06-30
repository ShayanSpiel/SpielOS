#!/usr/bin/env bash
# Compatibility shim for Codex plugin cache installs.
# Canonical hook behavior lives in tools/codex_hook.py behind `spiel codex-hook`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "$SCRIPT_DIR/../../../bin/spiel" ]]; then
  exec "$SCRIPT_DIR/../../../bin/spiel" codex-hook
fi

if command -v spiel >/dev/null 2>&1; then
  exec spiel codex-hook
fi

echo "[spiel post] spiel shim not found. Run the SpielOS installer or add ~/.local/bin to PATH."
exit 0
