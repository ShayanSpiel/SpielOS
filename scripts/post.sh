#!/bin/bash
# scripts/post.sh — Portable /post entry point (2 modes)
#
# Usage:
#   post.sh                         # Mode 1: current session (auto-save stub if missing)
#   post.sh <topic>                 # Mode 2: topic (inline text)
#   post.sh <path/to/file.md>       # Mode 2: topic from file

set -euo pipefail

VAULT="${VAULT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENGINE="$VAULT/scripts/engine.py"

case $# in
  0)
    exec python3 "$ENGINE" content post
    ;;
  1)
    arg="$1"
    if [[ -f "$arg" ]]; then
      exec python3 "$ENGINE" content post "@file:$arg"
    else
      exec python3 "$ENGINE" content post "$arg"
    fi
    ;;
  *)
    echo "Usage: post.sh [topic|file.md]" >&2
    exit 1
    ;;
esac
