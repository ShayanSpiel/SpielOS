#!/bin/sh
# SpielOS installer — installs everything needed, then offers first-run init.
#
# One line:
#   curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/SpielOS/main/install.sh | sh
#
# The script is idempotent: re-running it upgrades an existing install.
# Override the install source with SPIELOS_SOURCE=<name-or-path>
# (e.g. a git URL for a branch build). SPIELOS_REPO is the older name for
# the same override and still works.

set -eu

SOURCE="${SPIELOS_SOURCE:-${SPIELOS_REPO:-spielos}}"
TARGET_DIR="${SPIELOS_DIR:-$(pwd)}"

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

printf '%s' "${DIM}   installing/updating spielos ...${RESET}"
# --force re-pins the package to the requested source even when an older
# install exists, so re-running the installer always upgrades in place.
if pipx install --force "$SOURCE" >/dev/null 2>&1; then
    printf '%s\n' " done"
    INSTALLED_VERSION=$(spielos --version 2>/dev/null | sed -n 's/^spielos //p')
    [ -n "$INSTALLED_VERSION" ] || fail "the package installed, but 'spielos --version' did not return a runtime version."
    step "spielos $INSTALLED_VERSION ready at $(command -v spielos) ${DIM}(global tool — not your project folder)${RESET}"
else
    printf '%s\n' ""
    fail "'pipx install $SOURCE' failed — run it manually to see why."
fi

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) info "note: '$HOME/.local/bin' is not on your PATH; add it to your shell profile." ;;
esac

# ---- 4. the home: selected project folder ---------------------------------
#
# pipx installs the CLI globally; the SpielOS HOME (the files that matter)
# is created by init in the folder you are standing in. Auto-create it here
# when safe: interactively we ask; through a pipe (curl | sh) we proceed
# only in an empty directory so nothing of yours is ever touched.

if [ -t 0 ]; then
    printf '\n%s\n' "${BOLD}SpielOS project folder${RESET}"
    printf '%s' "Path [${TARGET_DIR}]: "
    read -r selected_dir < /dev/tty || selected_dir=""
    if [ -n "$selected_dir" ]; then TARGET_DIR="$selected_dir"; fi
fi
TARGET_DIR=$("$PY" -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$TARGET_DIR")

INIT_RAN=0
HOME_UPDATED=0
if [ -d "$TARGET_DIR/.agents/company" ]; then
    info "updating the existing SpielOS home ..."
    if spielos update --dir "$TARGET_DIR"; then
        HOME_VERSION=$("$PY" -c 'import re,sys; text=open(sys.argv[1], encoding="utf-8").read(); match=re.search(r"^VERSION\s*=\s*[\"'\"']([^\"'\"']+)", text, re.M); print(match.group(1) if match else "")' "$TARGET_DIR/.agents/company/runtime/config.py")
        [ "$HOME_VERSION" = "$INSTALLED_VERSION" ] || fail "home update version mismatch: package is $INSTALLED_VERSION but home is ${HOME_VERSION:-unknown}."
        HOME_UPDATED=1
        step "existing SpielOS home updated to $HOME_VERSION"
    else
        fail "the CLI was upgraded, but the existing home update failed. Run 'spielos update --dir $TARGET_DIR' to see the diagnostic."
    fi
elif [ ! -f "$TARGET_DIR/opencode.json" ]; then
    do_init=0
    if [ -t 0 ]; then
        printf '\n%s\n' "${BOLD}Create your SpielOS home in this folder?${RESET}"
        printf '%s\n' "${DIM}  $TARGET_DIR${RESET}"
        printf '%s' "Proceed? [Y/n] "
        read -r answer < /dev/tty || answer=""
        case "$answer" in
            n|N|no|No) ;;
            *) do_init=1 ;;
        esac
    elif [ -z "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
        do_init=1  # piped install + empty directory: safe to proceed
    fi
    if [ "$do_init" = 1 ]; then
        if spielos init --dir "$TARGET_DIR" -y </dev/null; then
            INIT_RAN=1
        else
            info "init failed — run 'spielos init' to retry."
        fi
    fi
fi

if [ "$INIT_RAN" = 0 ] && [ "$HOME_UPDATED" = 0 ]; then
    printf '%s\n' ""
    printf '%s\n' "${BOLD}Next:${RESET} run ${BOLD}spielos init --dir /path/to/project${RESET}"
    printf '%s\n' "${DIM}That creates the harness home (.agents/, .spielos/) — the CLI alone does not.${RESET}"
fi
printf '%s\n' "${DIM}Docs: https://spielos.xyz · .agents/company/README.md after init${RESET}"
