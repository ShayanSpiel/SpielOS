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

cat <<'MSG'
[spiel post] SpielOS is installed in Codex, but no vault is set up yet.

SpielOS needs one vault folder for strategy files and generated content.
Use the Codex prompt "Set up SpielOS in ~/SpielOS", or run:

  SPIELOS_INSTALL_DIR="$HOME/SpielOS" bash <(curl -fsSL https://spielos.xyz/install)

After setup finishes, /post will save to that vault from any Codex project.
MSG
exit 0
