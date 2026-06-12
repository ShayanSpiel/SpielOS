#!/usr/bin/env bash
# scripts/install.sh — Auto-detect agents, copy skills, inject VAULT_DIR
# Portable: resolves vault root from script location.
set -euo pipefail

VAULT="$(cd "$(dirname "$0")/.." && pwd)"
echo "═══ Spiel Engine Installer ═══"
echo "Vault: $VAULT"
echo ""

# ─── Copy rules.yaml if missing ────────────────────────────────────────────
if [ ! -f "$VAULT/rules.yaml" ]; then
  if [ -f "$VAULT/rules.yaml.example" ]; then
    cp "$VAULT/rules.yaml.example" "$VAULT/rules.yaml"
    echo "✓ Created rules.yaml from template"
  fi
else
  echo "• rules.yaml exists, skipping"
fi

# ─── Create .env if missing ────────────────────────────────────────────────
if [ ! -f "$VAULT/.env" ]; then
  cat > "$VAULT/.env" <<EOF
# VAULT_DIR — set to the vault root if auto-detection fails
# VAULT_DIR=$VAULT
EOF
  echo "✓ Created .env"
else
  echo "• .env exists, skipping"
fi

# ─── Create required directories with .gitkeep ────────────────────────────
for dir in assets/banners assets/screenshots content/queue content/sessions content/posted logs; do
  mkdir -p "$VAULT/$dir"
  touch "$VAULT/$dir/.gitkeep"
done
echo "✓ Directories created"

# ─── Detect agents ────────────────────────────────────────────────────────
AGENTS=()
if command -v opencode &>/dev/null; then
  AGENTS+=("opencode")
fi
if command -v cursor &>/dev/null; then
  AGENTS+=("cursor")
fi
if command -v code &>/dev/null; then
  AGENTS+=("vscode")
fi
if [ -d "$HOME/.claude" ]; then
  AGENTS+=("claude")
fi
if [ -d "$HOME/.continue" ]; then
  AGENTS+=("continue")
fi

echo "Detected agents: ${AGENTS[*]:-(none)}"

# ─── Install for opencode ─────────────────────────────────────────────────
if [[ " ${AGENTS[*]} " =~ " opencode " ]]; then
  OCONFIG="$HOME/.config/opencode"
  mkdir -p "$OCONFIG"

  # Copy skills
  if [ -d "$VAULT/.opencode/skill" ]; then
    cp -r "$VAULT/.opencode/skill/"* "$OCONFIG/skill/" 2>/dev/null || true
    echo "✓ Copied skills to $OCONFIG/skill/"
  fi

  # Copy commands
  if [ -d "$VAULT/.opencode/commands" ]; then
    mkdir -p "$OCONFIG/commands"
    cp -r "$VAULT/.opencode/commands/"* "$OCONFIG/commands/" 2>/dev/null || true
    echo "✓ Copied commands to $OCONFIG/commands/"
  fi

  # Inject VAULT_DIR into opencode.jsonc
  if [ -f "$OCONFIG/opencode.jsonc" ]; then
    # Check if VAULT_DIR already set
    if grep -q "VAULT_DIR" "$OCONFIG/opencode.jsonc" 2>/dev/null; then
      echo "• VAULT_DIR already set in opencode.jsonc"
    else
      # Try to inject into env section
      if grep -q '"env"' "$OCONFIG/opencode.jsonc" 2>/dev/null; then
        sed -i '' 's/"env": {/"env": {\n    "VAULT_DIR": "'"$VAULT"'",/' "$OCONFIG/opencode.jsonc"
      else
        # Append before closing brace
        sed -i '' 's/}$/,\n  "env": {\n    "VAULT_DIR": "'"$VAULT"'"\n  }\n}/' "$OCONFIG/opencode.jsonc"
      fi
      echo "✓ VAULT_DIR injected into opencode.jsonc"
    fi
  else
    cat > "$OCONFIG/opencode.jsonc" <<JSONC
{
  "env": {
    "VAULT_DIR": "$VAULT"
  }
}
JSONC
    echo "✓ Created opencode.jsonc with VAULT_DIR"
  fi

  echo "✓ opencode configured"
fi

# ─── Install for other agents (TODO) ─────────────────────────────────────
if [[ " ${AGENTS[*]} " =~ " cursor" ]] || [[ " ${AGENTS[*]} " =~ " vscode" ]]; then
  echo "• Cursor/VSCode: install the .opencode folder as project settings"
  echo "  Copy .opencode to .vscode/ or .cursor/ in the vault root"
fi

echo ""
echo "═══ Done ═══"
echo "Next: run /setup in opencode to configure ICP, offer, and voice."
