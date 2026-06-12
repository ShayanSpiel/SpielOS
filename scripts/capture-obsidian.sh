#!/usr/bin/env bash
# scripts/capture-obsidian.sh — Capture the Obsidian graph (or local graph).
#
# Thin wrapper around scripts/capture-window.sh — the generic auto-screenshot
# primitive. This wrapper just hardcodes --app "Obsidian" and provides
# the --view shorthand for the two most common graphs.
#
# Usage:
#   scripts/capture-obsidian.sh                  # full vault graph
#   scripts/capture-obsidian.sh --view local     # local graph for current page
#   scripts/capture-obsidian.sh --output path.png
#   scripts/capture-obsidian.sh --help
#
# For ANY other app, use scripts/capture-window.sh directly:
#   scripts/capture-window.sh --app "Safari" --url "https://..."
#   scripts/capture-window.sh --app "VS Code" --cmd "View: Toggle Terminal"
#   scripts/capture-window.sh --app "Terminal" --keys "Cmd+N"
#
# Why this script exists (2026-06-07):
#   The first "screenshot of the vault" post shipped a screenshot of X
#   because the agent grabbed the whole screen without verifying what
#   was frontmost. capture-window.sh (and this wrapper) hard-fail on
#   the wrong window.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Forward all args + add --app Obsidian
exec "$SCRIPT_DIR/capture-window.sh" --app "Obsidian" "$@"
