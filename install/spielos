#!/usr/bin/env bash
# SpielOS installer.
#
# One command. Any Mac/Linux. Any IDE.
#
#   curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash
#
# What this does:
#   1. Detects arch, python, git, curl/wget
  # 2. Resolves install path (default $PWD; override with $SPIELOS_INSTALL_DIR)
#   3. Downloads the SpielOS vault (git clone preferred, tarball fallback)
#   4. Starts the local setup wizard at http://localhost:7331
#   5. Waits for the wizard to write files (user clicks "Finish" in browser)
#   6. Installs the `spiel` shim to ~/.local/bin/spiel
#   7. Syncs IDE adapter files to all detected IDEs:
#        - opencode:    ~/.config/opencode/{agents,skill,commands}
#        - Cursor:      ~/.cursor/skills/
#        - Claude Code: ~/.claude/{agents,skills}
#
# The vault root is $PWD (override with $SPIELOS_INSTALL_DIR).
# The shim is ~/.local/bin/spiel.
#
# On completion: `spiel /post` (or just `/post` in any IDE) works.

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

SPIELOS_REPO="${SPIELOS_REPO:-ShayanSpiel/Spiel-OS}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/$SPIELOS_REPO.git}"
TARBALL_URL="${TARBALL_URL:-https://github.com/$SPIELOS_REPO/archive/refs/heads/main.tar.gz}"
RAW_INSTALL_URL="${RAW_INSTALL_URL:-https://raw.githubusercontent.com/$SPIELOS_REPO/main/install/install.sh}"
VERSION="${SPIELOS_VERSION:-main}"
DEFAULT_INSTALL_DIR="${SPIELOS_INSTALL_DIR:-$PWD}"
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

# Validate the target path. There are 4 cases:
#   1. Nothing exists                                 → fresh install
#   2. Symlink (broken OR points to non-SpielOS)      → auto-replace, then fresh install
#   3. Regular directory, has team/director.md        → re-install
#   4. Regular directory, no team/director.md         → error (real user data, ask first)
#   5. Regular file                                   → error

if [[ -L "$INSTALL_DIR" ]]; then
  # A symlink exists at the target path. This is almost always a leftover
  # from a previous install that got partially cleaned up. Auto-replace it
  # and proceed with a fresh install at the same path.
  TARGET=$(readlink "$INSTALL_DIR" 2>/dev/null || echo "(unreadable)")
  if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/team/director.md" ]]; then
    # Symlink resolves to a valid SpielOS install → re-install mode
    note "Existing SpielOS install detected at $INSTALL_DIR (via symlink)"
  else
    # Symlink is broken OR points to a non-SpielOS path → auto-replace
    err "Found a stale symlink at $INSTALL_DIR → $TARGET"
    err "Removing it and installing fresh at $INSTALL_DIR"
    rm -f "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
  fi
elif [[ -d "$INSTALL_DIR" ]]; then
  # Regular directory
  if [[ -f "$INSTALL_DIR/team/director.md" ]]; then
    note "Existing SpielOS install detected at $INSTALL_DIR"
  else
    note "Installing into existing directory: $INSTALL_DIR"
    note "  SpielOS files will be added alongside your existing files."
  fi
elif [[ -e "$INSTALL_DIR" ]]; then
  # Something exists but is not a symlink or directory (regular file, etc.)
  err "$INSTALL_DIR exists but is not a directory or symlink."
  err "Remove it:  rm $INSTALL_DIR"
  exit 1
else
  # Nothing exists — fresh install
  note "Installing SpielOS to $INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
fi

# ── Download ────────────────────────────────────────────────────

cd "$INSTALL_DIR"
IS_REINSTALL=0
if [[ ! -f "team/director.md" ]]; then
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
else
  # Re-install: vault already has team/director.md. Refresh the tool sources
  # (tools/, install/, system/, bin/spiel, package.json, etc.)
  # WITHOUT touching user data:
  #   - team/         (your prompt files)
  #   - skills/       (your skill overrides)
  #   - strategy/     (your audience/offer/voice/examples)
  #   - content/      (your drafts/briefs/ready/posted/rejected)
  #   - .env          (your secrets)
  #   - system/brand.* (your brand tokens)
  # To overwrite these, run `spiel init` (re-runs the wizard).
  IS_REINSTALL=1
  note "Existing install detected at $INSTALL_DIR"
  note "Re-install mode: refreshing tool sources only."
  note "  → PRESERVED (your data, not touched): team/, skills/, strategy/, content/, .env, system/brand.*"
  note "  → REFRESHED (from upstream): tools/, install/, system/, templates/, bin/spiel, package.json"
  note "  → IDE adapters: re-synced (your local team/ pushed to all 4 IDEs)"

  # Always use tarball overlay (NEVER `git pull`, which would clobber user data).
  if [[ $HAS_CURL -eq 1 ]]; then
    TMPDIR_OVERLAY=$(mktemp -d)
    if curl -fsSL "$TARBALL_URL" | tar -xz -C "$TMPDIR_OVERLAY" --strip-components=1 2>/dev/null; then
      (cd "$INSTALL_DIR" && python3 - <<PYEOF
import os, shutil
src = "$TMPDIR_OVERLAY"
dst = "$INSTALL_DIR"
# Directories: never overlay (user's custom data)
skip_dirs = {"team", "skills", "strategy", "content"}
# Individual files: never overlay
skip_files = {".env", "system/brand.md", "system/brand.json"}
copied = 0
skipped = 0
for root, dirs, files in os.walk(src):
    rel = os.path.relpath(root, src)
    parts = rel.split(os.sep) if rel != "." else []
    if any(p in skip_dirs for p in parts):
        skipped += len(files)
        continue
    for f in files:
        rel_file = os.path.relpath(os.path.join(root, f), src)
        if rel_file in skip_files:
            skipped += 1
            continue
        sp = os.path.join(root, f)
        dp = os.path.join(dst, rel_file)
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        shutil.copy2(sp, dp)
        copied += 1
print(f"  overlaid {copied} tool source files (skipped {skipped} user-data files)")
PYEOF
)
    else
      err "tarball download failed; tool sources NOT refreshed"
    fi
    rm -rf "$TMPDIR_OVERLAY"
  fi
fi
ok "SpielOS source at $INSTALL_DIR (re-install=$IS_REINSTALL)"

# ── Run wizard (fresh install) or skip (re-install) ───────────

if [[ $IS_REINSTALL -eq 1 ]]; then
  note "Re-install: skipping the wizard."
  note "  Your strategy files, content, and .env are preserved."
  note "  Tool source files in team/, tools/, system/ have been refreshed."
  note "  To re-run the wizard (and re-write your config), use:"
  note "    spiel init"
  WIZARD_EXIT=0
else
  note "Opening the setup wizard"
  echo "  → URL:  http://localhost:$WIZARD_PORT/"
  echo "  → Fill the setup steps (about 5 minutes)"
  echo "  → Click 'Finish & install' to write the files"
  echo "  → Then:  /post  (from any IDE)"
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

  # Wizard server auto-opens the browser via serve.py (single source of truth).
  # No duplicate `open` call here.

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
  WIZARD_EXIT=0
fi

# ── Post-wizard steps (if user finished) ────────────────────────

if [[ $WIZARD_EXIT -eq 0 && -f "$INSTALL_DIR/.env" ]]; then
  ok "Setup confirmed (.env present)."

  # Install the shim
  mkdir -p "$(dirname "$SHIM_PATH")"
  if [[ -L "$SHIM_PATH" || -f "$SHIM_PATH" ]]; then
    rm -f "$SHIM_PATH"
  fi
  cp "$INSTALL_DIR/bin/spiel" "$SHIM_PATH"
  chmod 0755 "$SHIM_PATH"
  ok "Shim installed: $SHIM_PATH"

  # Write vault pointer file (always — keeps .spiel-vault in sync with current path)
  printf 'VAULT_DIR=%s\n' "$INSTALL_DIR" > "$INSTALL_DIR/.spiel-vault"
  ok "Vault pointer: $INSTALL_DIR/.spiel-vault"

  # Write global config (~/.config/spielos/config) — makes vault resolvable from ANY cwd
  mkdir -p "$HOME/.config/spielos"
  printf 'VAULT_DIR=%s\n' "$INSTALL_DIR" > "$HOME/.config/spielos/config"
  ok "Global config: $HOME/.config/spielos/config -> $INSTALL_DIR"

  # Rewrite VAULT_DIR= line in .env (add if missing, preserves all other lines)
  if [[ -f "$INSTALL_DIR/.env" ]]; then
    if grep -q '^VAULT_DIR=' "$INSTALL_DIR/.env" 2>/dev/null; then
      sed -i '' "s|^VAULT_DIR=.*|VAULT_DIR=$INSTALL_DIR|" "$INSTALL_DIR/.env"
      ok "Updated VAULT_DIR in .env → $INSTALL_DIR"
    else
      printf '\nVAULT_DIR=%s\n' "$INSTALL_DIR" >> "$INSTALL_DIR/.env"
      ok "Appended VAULT_DIR to .env → $INSTALL_DIR"
    fi
  fi

  # Sync IDE adapters (opencode + Cursor + Claude Code, whichever is installed)
  if python3 "$INSTALL_DIR/tools/sync_adapters.py" --install </dev/null >/dev/null 2>&1; then
    IDE_TARGETS=""
    [[ -d "$HOME/.config/opencode" ]]  && IDE_TARGETS+="opencode  "
    [[ -d "$HOME/.cursor" ]]            && IDE_TARGETS+="Cursor  "
    [[ -d "$HOME/.claude" ]]            && IDE_TARGETS+="Claude Code  "
    [[ -d "$HOME/.codex" ]]             && IDE_TARGETS+="Codex  "
    if [[ -n "$IDE_TARGETS" ]]; then
      ok "Slash commands installed: $IDE_TARGETS"
    else
      ok "Adapters generated (no IDEs detected on this machine)"
    fi
  fi

  # Check PATH
  case ":$PATH:" in
    *":$(dirname "$SHIM_PATH"):"*) ok "Shim is on PATH" ;;
    *)
      note "Add this to your shell rc to use 'spiel' globally:"
      note "  export PATH=\"\$HOME/.local/bin:\$PATH\""
      ;;
  esac

  # Sanity-check the new tools. Catches missing-file bugs on first install
  # (e.g., broken tarball, partial clone, etc.) so the user finds out at
  # install time, not the first time they type /post.
  if [[ -x "$INSTALL_DIR/tools/editor.py" ]] && \
     python3 "$INSTALL_DIR/tools/editor.py" check --help >/dev/null 2>&1; then
    ok "tools/editor.py is callable"
  else
    err "tools/editor.py is missing or not executable — /post will fail"
    err "  re-run: curl ... | bash  (full install)"
  fi
  if [[ -x "$INSTALL_DIR/tools/sync_adapters.py" ]] && \
     python3 "$INSTALL_DIR/tools/sync_adapters.py" --help >/dev/null 2>&1; then
    ok "tools/sync_adapters.py is callable"
  else
    err "tools/sync_adapters.py is missing or broken — adapter sync will fail"
  fi
  if [[ -x "$INSTALL_DIR/bin/spiel" ]]; then
    ok "bin/spiel shim is executable"
  else
    err "bin/spiel is missing or not executable — /post will fail"
  fi

  note "DONE. From any IDE, type /post to ship a post."
  note "To re-run the wizard and update your config:"
  note "  spiel init"
else
  err "Setup incomplete (.env not found)."
  note "Re-run any time: $SHIM_PATH init"
fi
