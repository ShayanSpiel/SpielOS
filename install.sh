#!/bin/sh
# SpielOS installer — installs everything needed, then offers first-run init.
#
# One line:
#   curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/SpielOS1/main/install.sh | sh
#
# The script is idempotent: re-running it upgrades an existing install.
# Override the source repository with SPIELOS_REPO=<git-url>.

set -eu

REPO="${SPIELOS_REPO:-https://github.com/ShayanSpiel/SpielOS1.git}"

# ---- output helpers --------------------------------------------------------

if [ -t 1 ]; then
    BOLD=$(printf '\033[1m'); DIM=$(printf '\033[2m')
    GREEN=$(printf '\033[32m'); RED=$(printf '\033[31m'); CYAN=$(printf '\033[36m')
    RESET=$(printf '\033[0m')
else
    BOLD=""; DIM=""; GREEN=""; RED=""; CYAN=""; RESET=""
fi

step() { printf '%s\n' "${GREEN}✓${RESET} $1"; }
info() { printf '%s\n' "${DIM}→${RESET} $1"; }
fail() { printf '%s\n' "${RED}✗ $1${RESET}" >&2; exit 1; }

printf '%s\n' ""
printf '%s\n' "${BOLD}${CYAN}SpielOS${RESET}${DIM} — one durable loop for your AI company${RESET}"
printf '%s\n' ""

# ---- 1. python -------------------------------------------------------------

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0)
        major=${version%%.*}; minor=${version##*.}
        if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then PY="$candidate"; break; fi
        info "$candidate found but needs >= 3.11 (found $version)"
    fi
done
[ -n "$PY" ] || fail "Python 3.11+ is required. Install it from https://python.org (or your package manager) and re-run."

step "Python $($PY --version | cut -d' ' -f2)"

# ---- 2. pipx (installed for you when missing) ------------------------------

if command -v pipx >/dev/null 2>&1; then
    step "pipx $(pipx --version | cut -d' ' -f2)"
else
    printf '%s' "${DIM}   installing pipx ...${RESET}"
    installed_via=""
    if command -v brew >/dev/null 2>&1 && brew install pipx >/dev/null 2>&1; then
        installed_via=brew
    elif $PY -m pip install --user pipx >/dev/null 2>&1 \
        || $PY -m pip install --user --break-system-packages pipx >/dev/null 2>&1; then
        installed_via=pip
        # ~/.local/bin must be reachable before we can call the fresh pipx.
        case ":$PATH:" in
            *":$HOME/.local/bin:"*) ;;
            *) export PATH="$HOME/.local/bin:$PATH" ;;
        esac
    fi
    if [ -n "$installed_via" ] && command -v pipx >/dev/null 2>&1; then
        printf '%s\n' " done"
        step "pipx installed (via $installed_via)"
    else
        printf '%s\n' ""
        fail "could not install pipx automatically. Install it once with 'brew install pipx' or '$PY -m pip install --user pipx', then re-run."
    fi
fi

# ---- 3. spielos ------------------------------------------------------------

printf '%s' "${DIM}   installing spielos ...${RESET}"
if pipx list 2>/dev/null | grep -q '^package spielos'; then
    if pipx upgrade spielos >/dev/null 2>&1 || pipx install "$REPO" >/dev/null 2>&1; then
        printf '%s\n' " done"
        step "spielos upgraded"
    else
        printf '%s\n' ""
        fail "'pipx upgrade spielos' failed — run it manually to see why."
    fi
else
    if pipx install "$REPO" >/dev/null 2>&1; then
        printf '%s\n' " done"
        step "spielos installed from $REPO"
    else
        printf '%s\n' ""
        fail "'pipx install $REPO' failed — run it manually to see why."
    fi
fi

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) info "note: '$HOME/.local/bin' is not on your PATH; add it to your shell profile." ;;
esac

# ---- 4. optional first-run init --------------------------------------------

NEXT="spielos init"
if [ -t 0 ] && [ ! -e "./.agents/company" ] && [ ! -f ./opencode.json ]; then
    existing=$(ls -A 2>/dev/null | grep -v -e '^\.' -e '^\.\.$' | head -3)
    printf '\n%s' "Set up a SpielOS home right here? [Y/n] "
    read -r answer
    case "$answer" in
        n|N|no|No) ;;
        *)
            if spielos init; then exit 0; fi
            NEXT="(run 'spielos init' again to retry)"
            ;;
    esac
fi

printf '%s\n' ""
printf '%s\n' "${BOLD}Next:${RESET} $NEXT"
printf '%s\n' "${DIM}Docs: .agents/company/README.md after init · https://spielos.xyz${RESET}"
