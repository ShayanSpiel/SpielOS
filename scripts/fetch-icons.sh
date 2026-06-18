#!/usr/bin/env bash
set -euo pipefail

# fetch-icons.sh — Download icons from Lucide GitHub repo.
# Usage: bash scripts/fetch-icons.sh
# Downloads to assets/icons/ (overwrites existing files).
# Only fetches the icons listed below — not the entire set.

VAULT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$VAULT/assets/icons"
LUCIDE_RAW="https://raw.githubusercontent.com/lucide-icons/lucide/main/icons"

mkdir -p "$OUT_DIR"

ICONS=(
  arrow-up-right.svg
  ban.svg
  bot.svg
  code.svg
  compass.svg
  crosshair.svg
  feather.svg
  github.svg
  layers.svg
  lightbulb.svg
  rocket.svg
  send.svg
  settings-2.svg
  terminal.svg
  trending-up.svg
)

echo "── Fetching ${#ICONS[@]} Lucide icons ──"
for icon in "${ICONS[@]}"; do
  url="$LUCIDE_RAW/$icon"
  out="$OUT_DIR/$icon"
  code=$(curl -s -o "$out" -w "%{http_code}" "$url")
  if [ "$code" = "200" ]; then
    echo "  ✓ $icon"
  else
    echo "  ✗ $icon (HTTP $code)"
    rm -f "$out"
  fi
done
echo "Done."
