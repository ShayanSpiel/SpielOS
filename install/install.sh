#!/usr/bin/env bash
# SpielOS installer.
#
# One command. Any Mac/Linux. Any IDE.
#
#   curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash
#
# (The spielos.xyz mirror is preferred when available.)
#
# What this does:
#   1. Detects arch, python, git, curl/wget
#   2. Resolves install path (default ~/.spiel; override with $SPIELOS_INSTALL_DIR)
#   3. Downloads the SpielOS vault (git clone preferred, tarball fallback)
#   4. Starts the local setup wizard at http://localhost:7331
#   5. Waits for the wizard to write files (user clicks "Finish" in browser)
#   6. Installs the `spiel` shim to ~/.local/bin/spiel
#   7. Syncs IDE adapter files to ~/.config/opencode/
#
# On completion: `spiel /post empty` from any IDE works.

set -e
set -o pipefail

# The script must keep working even when its stdin is the curl pipe
# (no TTY). We check the TTY status of stderr (which is always the
# terminal when invoked from a real shell) instead of stdin, so that
# `curl | bash` still works AND the wizard can still auto-open the
# browser when launched from an interactive terminal.
if [[ -t 2 ]]; then
  HAS_TTY=1
else
  HAS_TTY=0
fi

GITHUB_REPO="https://github.com/ShayanSpiel/Spiel-OS.git"
TARBALL_URL="https://github.com/ShayanSpiel/Spiel-OS/archive/refs/heads/main.tar.gz"
RAW_INSTALL_URL="https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh"
VERSION="${SPIELOS_VERSION:-main}"
DEFAULT_INSTALL_DIR="${SPIELOS_INSTALL_DIR:-$HOME/.spiel}"
SHIM_PATH="$HOME/.local/bin/spiel"
WIZARD_PORT="${SPIELOS_WIZARD_PORT:-7331}"
WIZARD_TIMEOUT="${SPIELOS_WIZARD_TIMEOUT:-1800}"  # 30 min max

# ── Helpers ─────────────────────────────────────────────────────

err()  { printf '  %s\n' "$1" >&2; }
ok()   { printf '  ✓ %s\n' "$1"; }
note() { printf '\n  %s\n\n' "$1"; }

detect_arch() {
  local m
  m=$(uname -m 2>/dev/null || echo unknown)
  case "$m" in
    arm64|aarch64) echo "arm64" ;;
    x86_64)        echo "x86_64" ;;
    *)             echo "$m" ;;
  esac
}

# Resolve a path: expand leading ~, normalize, return absolute.
resolve_path() {
  local p="$1"
  if [[ -z "$p" ]]; then
    p="$DEFAULT_INSTALL_DIR"
  fi
  # Expand leading ~ (only if not already absolute)
  if [[ "$p" == ~* ]]; then
    p="$HOME${p#~}"
  fi
  # Make absolute
  if [[ "$p" != /* ]]; then
    p="$PWD/$p"
  fi
  printf '%s' "$p"
}

cleanup() {
  # Kill the wizard subprocess if it's still running
  if [[ -n "${WIZARD_PID:-}" ]]; then
    if kill -0 "$WIZARD_PID" 2>/dev/null; then
      kill "$WIZARD_PID" 2>/dev/null || true
      # Give it 2 seconds to clean up, then SIGKILL
      for _ in 1 2 3 4; do
        kill -0 "$WIZARD_PID" 2>/dev/null || break
        sleep 0.5
      done
      kill -9 "$WIZARD_PID" 2>/dev/null || true
    fi
  fi
}
trap cleanup EXIT INT TERM

# ── Pre-flight ──────────────────────────────────────────────────

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  SpielOS installer                          │"
echo "  │  A markdown-driven marketing team.          │"
echo "  └─────────────────────────────────────────────┘"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  err "python3 is required but not installed."
  err "Install Python 3.10+ from https://python.org or via your package manager."
  exit 1
fi
ok "python3: $(python3 --version)"

HAS_GIT=0
if command -v git >/dev/null 2>&1; then
  HAS_GIT=1
  ok "git: $(git --version | head -1)"
fi

HAS_CURL=0
if command -v curl >/dev/null 2>&1; then
  HAS_CURL=1
fi
HAS_WGET=0
if command -v wget >/dev/null 2>&1; then
  HAS_WGET=1
fi
if [[ $HAS_CURL -eq 0 && $HAS_WGET -eq 0 ]]; then
  err "curl or wget is required to download SpielOS."
  exit 1
fi

ARCH=$(detect_arch)
ok "arch: $ARCH"

# ── Install path ───────────────────────────────────────────────

# We never `read` from stdin (that breaks `curl | bash`).
# Override via $SPIELOS_INSTALL_DIR or a CLI arg.
INSTALL_DIR=$(resolve_path "$DEFAULT_INSTALL_DIR")

# If directory exists and is non-empty, check it's a SpielOS install
if [[ -d "$INSTALL_DIR" ]]; then
  if [[ -f "$INSTALL_DIR/team/md.md" ]]; then
    note "Existing SpielOS install detected at $INSTALL_DIR"
    ok "Re-running the wizard on the existing install..."
  else
    err "Directory $INSTALL_DIR is not a SpielOS install."
    err "Pick a different path (set \$SPIELOS_INSTALL_DIR) or remove it first."
    exit 1
  fi
else
  note "Installing SpielOS to $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
fi

# ── Download ────────────────────────────────────────────────────

cd "$INSTALL_DIR"
if [[ ! -f "team/md.md" ]]; then
  if [[ $HAS_GIT -eq 1 ]]; then
    note "Cloning $GITHUB_REPO ..."
    if ! git clone --depth 1 --branch "$VERSION" "$GITHUB_REPO" "$INSTALL_DIR.tmp" 2>/dev/null; then
      err "git clone failed; falling back to tarball..."
      rm -rf "$INSTALL_DIR.tmp"
      if [[ $HAS_CURL -eq 1 ]]; then
        curl -fsSL "$TARBALL_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
      else
        wget -qO- "$TARBALL_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
      fi
    else
      rm -rf "$INSTALL_DIR"
      mv "$INSTALL_DIR.tmp" "$INSTALL_DIR"
    fi
  else
    note "Downloading SpielOS tarball..."
    if [[ $HAS_CURL -eq 1 ]]; then
      curl -fsSL "$TARBALL_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
    else
      wget -qO- "$TARBALL_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
    fi
  fi
fi
ok "SpielOS downloaded to $INSTALL_DIR"

# ── Run wizard ──────────────────────────────────────────────────

note "Opening the setup wizard"
echo "  → URL:  http://localhost:$WIZARD_PORT/"
echo "  → Fill the 10 steps (about 5 minutes)"
echo "  → Click 'Finish & install' to write the files"
echo "  → Then:  spiel /post empty  (from any IDE)"
echo ""

# The wizard needs a real browser to fill the form. The user opens the
# URL in their browser, fills the form, clicks Finish, and the wizard
# writes the files. The install script then continues.
#
# If the user is in an interactive terminal, try to open the browser.
# If piped, just print the URL.

WIZARD_PID=""
if [[ $HAS_CURL -eq 1 ]]; then
  ok "Starting wizard at http://localhost:$WIZARD_PORT/ ..."
  cd "$INSTALL_DIR"
  python3 "$INSTALL_DIR/install/wizard/serve.py" \
    --port "$WIZARD_PORT" \
    --target "$INSTALL_DIR" </dev/null &
  WIZARD_PID=$!
else
  err "curl is required to run the wizard."
  exit 1
fi

# Try to open the browser (only if we have a display tool)
if [[ $HAS_TTY -eq 1 ]]; then
  if command -v open >/dev/null 2>&1; then
    (sleep 0.5; open "http://localhost:$WIZARD_PORT/") 2>/dev/null || true
  elif command -v xdg-open >/dev/null 2>&1; then
    (sleep 0.5; xdg-open "http://localhost:$WIZARD_PORT/") 2>/dev/null || true
  fi
fi

# Wait for the wizard to write its marker file (which it does on Finish)
# or for the user to Ctrl+C.
note "Waiting for the wizard to finish (max ${WIZARD_TIMEOUT}s)..."
INSTALL_STATE="$INSTALL_DIR/.install-state.json"

ELAPSED=0
while [[ ! -f "$INSTALL_STATE" ]] && kill -0 "$WIZARD_PID" 2>/dev/null; do
  sleep 1
  ELAPSED=$((ELAPSED + 1))
  if [[ $ELAPSED -ge $WIZARD_TIMEOUT ]]; then
    err "Wizard timed out after ${WIZARD_TIMEOUT}s"
    break
  fi
done

# Stop the wizard (it may have already exited)
if kill -0 "$WIZARD_PID" 2>/dev/null; then
  kill "$WIZARD_PID" 2>/dev/null || true
  for _ in 1 2 3 4; do
    kill -0 "$WIZARD_PID" 2>/dev/null || break
    sleep 0.3
  done
  kill -9 "$WIZARD_PID" 2>/dev/null || true
fi
wait "$WIZARD_PID" 2>/dev/null || true
WIZARD_PID=""

# ── Post-wizard steps (if user finished) ────────────────────────

if [[ -f "$INSTALL_STATE" && -f "$INSTALL_DIR/.env" ]]; then
  ok "Wizard completed."

  # Install the shim
  mkdir -p "$(dirname "$SHIM_PATH")"
  if [[ -L "$SHIM_PATH" || -f "$SHIM_PATH" ]]; then
    rm -f "$SHIM_PATH"
  fi
  cp "$INSTALL_DIR/bin/spiel" "$SHIM_PATH"
  chmod 0755 "$SHIM_PATH"
  ok "Shim installed: $SHIM_PATH"

  # Create ~/.spiel symlink for shim resolution (if needed)
  if [[ "$INSTALL_DIR" != "$HOME/.spiel" ]]; then
    if [[ -L "$HOME/.spiel" ]]; then
      rm -f "$HOME/.spiel"
    fi
    if [[ ! -e "$HOME/.spiel" ]]; then
      ln -s "$INSTALL_DIR" "$HOME/.spiel"
      ok "Symlink: $HOME/.spiel → $INSTALL_DIR"
    fi
  fi

  # Sync IDE adapters
  if python3 "$INSTALL_DIR/tools/sync_adapters.py" --install </dev/null >/dev/null 2>&1; then
    ok "IDE adapters synced to ~/.config/opencode/"
  fi

  # Check PATH
  case ":$PATH:" in
    *":$(dirname "$SHIM_PATH"):"*) ok "Shim is on PATH" ;;
    *)
      note "Add this to your shell rc to use 'spiel' globally:"
      note "  export PATH=\"\$HOME/.local/bin:\$PATH\""
      ;;
  esac

  note "DONE. Run 'spiel /post empty' from any IDE to ship a post."
else
  err "Wizard did not complete (no .install-state.json found)."
  note "Re-run any time:"
  note "  python3 $INSTALL_DIR/install/wizard/serve.py --port $WIZARD_PORT --target $INSTALL_DIR"
fi
