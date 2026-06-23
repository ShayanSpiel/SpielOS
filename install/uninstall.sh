#!/usr/bin/env bash
# SpielOS uninstaller.
# Removes the vault and the shim. Optionally removes config.

set -euo pipefail

DEFAULT_INSTALL_DIR="$HOME/.spielos"
SHIM_PATH="$HOME/.local/bin/spiel"

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  SpielOS uninstaller                        │"
echo "  │  Removes the vault + shim.                  │"
echo "  └─────────────────────────────────────────────┘"
echo ""

read -rp "  Install path [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

# Backup option
read -rp "  Back up content/ (sessions, queue, posted) before removal? (Y/n) " bk
bk="${bk:-Y}"
if [[ "$bk" =~ ^[Yy]$ ]]; then
  if [[ -d "$INSTALL_DIR/content" ]]; then
    BACKUP="$INSTALL_DIR.content.backup.$(date +%Y%m%d%H%M%S).tar.gz"
    tar -czf "$BACKUP" -C "$INSTALL_DIR" content
    echo "  ✓ Backed up to $BACKUP"
  fi
fi

# Remove vault
if [[ -d "$INSTALL_DIR" ]]; then
  rm -rf "$INSTALL_DIR"
  echo "  ✓ Removed $INSTALL_DIR"
else
  echo "  $INSTALL_DIR not found, skipping"
fi

# Remove shim
if [[ -f "$SHIM_PATH" ]]; then
  rm -f "$SHIM_PATH"
  echo "  ✓ Removed $SHIM_PATH"
fi

# Optionally remove ~/.config/opencode/{agents,skill}/md* etc. (live install)
if [[ -d "$HOME/.config/opencode" ]]; then
  read -rp "  Also remove SpielOS agents from ~/.config/opencode/ ? (y/N) " rm_oc
  if [[ "$rm_oc" =~ ^[Yy]$ ]]; then
    for f in "$HOME/.config/opencode/agents/"*.md; do
      [[ -f "$f" ]] || continue
      if grep -q "SpielOS\|Spiel" "$f" 2>/dev/null; then
        rm -f "$f"
        echo "  ✓ Removed $(basename "$f")"
      fi
    done
    for d in "$HOME/.config/opencode/skill/"*/; do
      [[ -d "$d" ]] || continue
      if grep -q "Spiel" "$d/SKILL.md" 2>/dev/null; then
        rm -rf "$d"
        echo "  ✓ Removed skill/$(basename "$d")"
      fi
    done
  fi
fi

echo ""
echo "  Done. Re-install any time:"
echo "    curl -fsSL https://raw.githubusercontent.com/ShayanSpiel/Spiel-OS/main/install/install.sh | bash"
echo ""
