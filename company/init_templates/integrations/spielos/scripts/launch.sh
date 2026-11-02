#!/bin/sh
# Launch only the bundled runtime. No package installation or network bootstrap.
set -eu
PLUGIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -n "${SPIELOS_PYTHON:-}" ]; then
    if "$SPIELOS_PYTHON" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
        exec "$SPIELOS_PYTHON" -I -B "$PLUGIN_DIR/scripts/entry.py" "$@"
    fi
    printf '%s\n' 'The selected Python cannot run SpielOS. Choose Python 3.11 or newer in SpielOS setup.' >&2
    exit 1
fi
for candidate in python3.14 python3.13 python3.12 python3.11 python3 python /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -I -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
        exec "$candidate" -I -B "$PLUGIN_DIR/scripts/entry.py" "$@"
    fi
done
printf '%s\n' 'SpielOS needs Python 3.11 or newer on this Mac or Linux computer. Run the SpielOS setup skill for help. No company files were changed.' >&2
exit 1
