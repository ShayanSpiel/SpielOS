#!/bin/sh
# Install the CLI; company creation and migrations are explicit operations.
# Local source: SPIELOS_SOURCE=/absolute/path/SpielOS1 sh install.sh
# Explicit home: sh install.sh --init --dir /absolute/path/my-company
# Portable package: --package /inspected/local/package previews only.
# SPIELOS_REPO remains an alias for SPIELOS_SOURCE.

set -eu

SOURCE="${SPIELOS_SOURCE:-${SPIELOS_REPO:-spielos}}"
TARGET_DIR="${SPIELOS_DIR:-$(pwd)}"
PACKAGE=""
INIT_REQUESTED=0
TARGET_SELECTED=0
[ -z "${SPIELOS_DIR:-}" ] || TARGET_SELECTED=1

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

# ---- 0. arguments -----------------------------------------------------------

while [ $# -gt 0 ]; do
    case "$1" in
        --init) INIT_REQUESTED=1; TARGET_SELECTED=1; shift ;;
        --dir) [ $# -ge 2 ] || fail "--dir needs a folder"; TARGET_DIR="$2"; TARGET_SELECTED=1; shift 2 ;;
        --dir=*) TARGET_DIR="${1#--dir=}"; TARGET_SELECTED=1; shift ;;
        --package|--bundle) [ $# -ge 2 ] || fail "$1 needs an inspected local package folder"; PACKAGE="$2"; TARGET_SELECTED=1; shift 2 ;;
        --package=*|--bundle=*) PACKAGE="${1#*=}"; TARGET_SELECTED=1; shift ;;
        --help|-h) printf '%s\n' "Usage: install.sh [--init --dir FOLDER] [--package LOCAL_FOLDER]" "Default: install/upgrade the CLI only. Package import is preview-only."; exit 0 ;;
        *) fail "unknown argument: $1 (use --help)" ;;
    esac
done

printf '%s\n' ""
printf '%s\n' "${BOLD}${CYAN}SpielOS${RESET}${DIM} — portable company workflows${RESET}"
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
    elif $PY -m pip install --user pipx >/dev/null 2>&1; then
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

# pipx may already exist while its application directory is absent from PATH.
PIPX_APP_BIN="${PIPX_BIN_DIR:-$HOME/.local/bin}"
case ":$PATH:" in
    *":$PIPX_APP_BIN:"*) ;;
    *) export PATH="$PIPX_APP_BIN:$PATH" ;;
esac

# ---- 3. spielos ------------------------------------------------------------

printf '%s' "${DIM}   installing/updating spielos ...${RESET}"
# --force re-pins the package to the requested source even when an older
# install exists, so re-running the installer always upgrades in place.
# Run from a neutral directory: inside a project that has its own .venv,
# pipx/uv tooling can otherwise land the environment into that project.
INSTALL_CWD=$(mktemp -d)
if (cd "$INSTALL_CWD" && pipx install --force --python "$PY" "$SOURCE") >/dev/null 2>&1; then
    rmdir "$INSTALL_CWD" 2>/dev/null || rm -rf "$INSTALL_CWD"
    printf '%s\n' " done"
    INSTALLED_VERSION=$(spielos --version 2>/dev/null | sed -n 's/^spielos //p')
    [ -n "$INSTALLED_VERSION" ] || fail "the package installed, but 'spielos --version' did not return a runtime version."
    step "spielos $INSTALLED_VERSION ready at $(command -v spielos) ${DIM}(global tool — not your project folder)${RESET}"
else
    rm -rf "$INSTALL_CWD"
    printf '%s\n' ""
    fail "'pipx install $SOURCE' failed — run it manually to see why."
fi

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) info "note: '$HOME/.local/bin' is not on your PATH; add it to your shell profile." ;;
esac

# ---- 4. explicit selected home ---------------------------------------------

TARGET_DIR=$("$PY" -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$TARGET_DIR")
HOME_READY=0
if [ "$TARGET_SELECTED" = 1 ]; then
    if [ -f "$TARGET_DIR/.agents/company/__main__.py" ]; then
        spielos update --dir "$TARGET_DIR" --keep-stale || fail "selected home refresh failed; inspect the runtime diagnostic"
        HOME_READY=1
        step "selected home product files refreshed; owner content preserved"
    elif [ "$INIT_REQUESTED" = 1 ]; then
        spielos init --dir "$TARGET_DIR" -y </dev/null || fail "explicit company initialization failed"
        HOME_READY=1
    else
        info "no initialized home selected; use --init --dir $TARGET_DIR when you want to create it"
    fi
fi
if [ "$HOME_READY" = 0 ]; then
    printf '%s\n' "Next: spielos init --dir /absolute/path/my-company" "No company home was created or changed automatically."
else
    printf '%s\n' "Editable content: $TARGET_DIR/company/; pinned runtime: .spielos/runtime/company/." "Legacy content moves require a separate exact reviewed migration plan."
fi

# ---- 5. static package preview; never install or execute package code -------
if [ -n "$PACKAGE" ]; then
    [ "$HOME_READY" = 1 ] || fail "package preview needs an explicitly selected initialized home"
    case "$PACKAGE" in *://*|*.git) fail "clone and inspect the package yourself, then pass its local folder" ;; esac
    [ -f "$PACKAGE/package.json" ] || fail "use a new portable package folder containing package.json; legacy Department bundles need reviewed conversion"
    spielos import "$PACKAGE" --home "$TARGET_DIR" --json || fail "portable package preview failed"
    printf '%s\n' "Package preview only: no definitions installed, hooks executed or permissions granted." "Review the exact plan and digest before the separate import apply command."
fi
printf '%s\n' "Docs: https://spielos.xyz; .agents/company/README.md in an initialized home."
