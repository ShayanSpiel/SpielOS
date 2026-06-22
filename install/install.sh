#!/usr/bin/env bash
# SpielOS installer.
#
# One command. Any Mac/Linux. Any IDE.
#
#   curl -fsSL https://spielos.xyz/install.sh | bash
#
# What this does:
#   1. Asks for install path (default ~/.spiel/)
#   2. Downloads the SpielOS vault (git clone or tarball)
#   3. Runs the local setup wizard at http://localhost:7331
#   4. The wizard writes strategy files, brand, .env
#   5. Installs the `spiel` shim to ~/.local/bin/spiel
#   6. Syncs IDE adapter files
#
# On completion: `spiel /post empty` from any IDE works.

set -euo pipefail

REPO="${SPIELOS_REPO:-https://github.com/ShayanSpiel/Spiel-OS.git}"
VERSION="${SPIELOS_VERSION:-main}"
DEFAULT_INSTALL_DIR="$HOME/.spiel"
SHIM_PATH="$HOME/.local/bin/spiel"

# ── Helpers ─────────────────────────────────────────────────────

err()  { echo "  $1" >&2; }
ok()   { echo "  ✓ $1"; }
note() { echo ""; echo "  $1"; echo ""; }

# ── Pre-flight ──────────────────────────────────────────────────

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  SpielOS installer                          │"
echo "  │  A markdown-driven marketing team.          │"
echo "  └─────────────────────────────────────────────┘"
echo ""

# python3
if ! command -v python3 >/dev/null 2>&1; then
  err "python3 is required but not installed."
  err "Install Python 3.10+ from https://python.org or via your package manager."
  exit 1
fi
ok "python3 found: $(python3 --version)"

# git (preferred) or curl+tar
HAS_GIT=0
if command -v git >/dev/null 2>&1; then
  HAS_GIT=1
  ok "git found: $(git --version | head -1)"
fi

# curl/wget
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

# ── Install path ───────────────────────────────────────────────

read -rp "  Install path [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

# If directory exists and is non-empty, check it's a SpielOS install
if [[ -d "$INSTALL_DIR" ]]; then
  if [[ -f "$INSTALL_DIR/team/md.md" ]]; then
    note "Existing SpielOS install detected at $INSTALL_DIR"
    read -rp "  Re-run the wizard on the existing install? (y/N) " yn
    if [[ ! "$yn" =~ ^[Yy]$ ]]; then
      note "Aborted. Re-run with: curl ... | bash"
      exit 0
    fi
  else
    err "Directory $INSTALL_DIR is not a SpielOS install."
    err "Pick a different path or remove it first."
    exit 1
  fi
else
  note "Installing SpielOS to $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
fi

# ── Download ────────────────────────────────────────────────────

cd "$INSTALL_DIR"
if [[ ! -d ".git" && ! -f "team/md.md" ]]; then
  if [[ $HAS_GIT -eq 1 ]]; then
    note "Cloning $REPO ..."
    if [[ -d ".git" ]]; then
      git pull origin "$VERSION" --ff-only 2>/dev/null || true
    else
      # fresh clone
      tmpdir=$(mktemp -d)
      git clone --depth 1 --branch "$VERSION" "$REPO" "$tmpdir/spielos" 2>/dev/null \
        || git clone --depth 1 "$REPO" "$tmpdir/spielos"
      shopt -s dotglob
      mv "$tmpdir/spielos/"* "$tmpdir/spielos/".* "$INSTALL_DIR/" 2>/dev/null || true
      rm -rf "$tmpdir/spielos"
    fi
  else
    note "Downloading SpielOS tarball ..."
    TAR_URL="https://github.com/ShayanSpiel/Spiel-OS/archive/refs/heads/${VERSION}.tar.gz"
    if [[ $HAS_CURL -eq 1 ]]; then
      curl -fsSL "$TAR_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
    else
      wget -qO- "$TAR_URL" | tar -xz --strip-components=1 -C "$INSTALL_DIR"
    fi
  fi
fi
ok "SpielOS downloaded to $INSTALL_DIR"

# ── Python deps ─────────────────────────────────────────────────

# Playwright is optional — only needed for banner generation.
# We don't install it here; the wizard warns and the user can install later.
ok "python3 ready"

# ── Run wizard ──────────────────────────────────────────────────

note "Opening the setup wizard at http://localhost:7331"
note "  → Fill the 10 steps (about 5 minutes)"
note "  → Click 'Finish & install' to write the files"
note "  → Then run: spiel /post empty  (from any IDE)"
echo ""

# Don't auto-open browser when piped (no controlling TTY)
if [[ -t 1 ]]; then
  OPEN_FLAG=""
else
  OPEN_FLAG="--no-open"
fi

python3 "$INSTALL_DIR/install/wizard/serve.py" --port 7331 --target "$INSTALL_DIR" $OPEN_FLAG
WIZARD_EXIT=$?

# ── Post-wizard steps (if user finished) ────────────────────────

if [[ $WIZARD_EXIT -eq 0 && -f "$INSTALL_DIR/.env" ]]; then
  ok "Wizard completed."

  # Install the shim
  mkdir -p "$(dirname "$SHIM_PATH")"
  cp "$INSTALL_DIR/bin/spiel" "$SHIM_PATH"
  chmod 0755 "$SHIM_PATH"
  ok "Shim installed: $SHIM_PATH"

  # Create ~/.spiel symlink for the shim's vault resolution (#3)
  if [[ "$INSTALL_DIR" != "$HOME/.spiel" ]]; then
    # Use a symlink if ~/.spiel doesn't exist, or update if it points elsewhere
    if [[ -L "$HOME/.spiel" ]]; then
      rm -f "$HOME/.spiel"
    fi
    if [[ ! -e "$HOME/.spiel" ]]; then
      ln -s "$INSTALL_DIR" "$HOME/.spiel"
      ok "Symlink: $HOME/.spiel → $INSTALL_DIR"
    fi
  fi

  # Sync IDE adapters
  if python3 "$INSTALL_DIR/tools/sync_adapters.py" >/dev/null 2>&1; then
    ok "IDE adapters generated in adapters/ and skills/"
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
  note "Wizard exited before completion."
  note "Re-run any time: $SHIM_PATH init  (or: python3 $INSTALL_DIR/install/wizard/serve.py --target $INSTALL_DIR)"
fi
