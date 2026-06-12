#!/usr/bin/env bash
# scripts/capture-window.sh — Generic auto-screenshot of any app's front window
#
# Activate any app, optionally navigate (command palette, URL, keystrokes),
# and capture the front window of that app as a PNG. Validates the capture.
#
# Usage:
#   scripts/capture-window.sh --app "Obsidian"                                  # activate + capture
#   scripts/capture-window.sh --app "Obsidian" --cmd "Graph: Open graph view"  # navigate via palette
#   scripts/capture-window.sh --app "Obsidian" --view graph                     # shorthand for the graph command
#   scripts/capture-window.sh --app "Safari" --url "https://example.com"       # open URL then capture
#   scripts/capture-window.sh --app "Terminal" --keys "Cmd+N"                   # new window then capture
#   scripts/capture-window.sh --app "Finder" --output /tmp/x.png                # custom output path
#   scripts/capture-window.sh --app "Obsidian" --wait 5                         # extra wait after navigate
#   scripts/capture-window.sh --help
#
# Flags:
#   --app <name>         REQUIRED. The app to capture (must be installed).
#   --cmd <text>         Open the app's command palette, type this text, press Enter.
#                        Works for apps with a palette (Obsidian, VS Code, Sublime, Atom, Linear, Raycast).
#   --view <name>        Shorthand for --cmd, with these presets:
#                          graph  -> "Graph: Open graph view" (Obsidian)
#                          local  -> "Graph: Open local graph"  (Obsidian)
#                          daily  -> "Daily notes: Open today's daily note" (Obsidian)
#   --url <url>          Open this URL in the app (works for browsers: Safari, Chrome, Firefox, Arc, Brave).
#                        The app must be one of the supported browsers (validated).
#   --keys <keystroke>   Send a keystroke to the app before capture.
#                        Examples: "Cmd+N" (new window), "Cmd+Shift+P" (VS Code palette), "Cmd+4" (system item).
#                        Use a comma-separated list for multiple: --keys "Cmd+N,Cmd+T"
#   --wait <seconds>     Override the post-navigate wait (default 3s).
#   --cold-start <sec>   Override the cold-start wait (default 4s).
#   --output <path>      Output PNG path. Default: assets/screenshots/<timestamp>-<app>.png
#   --no-launch          Don't launch the app if not running. Abort instead.
#   --help               Show this help.
#
# What this script does:
#   1. If the app isn't running, launch it (open -a "<name>")
#   2. Wait for cold start (~4s)
#   3. Activate the app
#   4. Verify the app is frontmost (hard-fail if not)
#   5. Optionally navigate (palette / URL / keystroke)
#   6. Wait for render
#   7. Capture the front window by ID (not whole screen)
#   8. Validate the PNG (size, dimensions, format)
#   9. Print the path on the last line
#
# Why this script exists (2026-06-07):
#   The earlier capture-obsidian.sh hardcoded the Obsidian graph command.
#   We needed the same safety (frontmost verification, capture by window ID)
#   for ANY app, not just Obsidian. Today is Obsidian. Tomorrow is a
#   browser, a terminal, an IDE. This is the generic primitive.
#
# Requirements:
#   - macOS (uses osascript + screencapture -l)
#   - The named app must be installed

set -euo pipefail

SCREENSHOT_DIR="${SCREENSHOT_DIR:-${VAULT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}/assets/screenshots}"

# ---- colors --------------------------------------------------------------
RED=$'\033[0;31m'
GRN=$'\033[0;32m'
YLW=$'\033[1;33m'
BLU=$'\033[0;34m'
RST=$'\033[0m'

# ---- usage ---------------------------------------------------------------
print_help() {
  sed -n '2,/^# Requirements:/p' "$0" | sed 's/^# \{0,1\}//' | head -n -2
  exit 0
}

# ---- args ----------------------------------------------------------------
APP=""
CMD=""
VIEW=""
URL=""
KEYS=""
WAIT_RENDER=3
COLD_START_WAIT=4
OUTPUT=""
NO_LAUNCH=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)      print_help;;
    --app)          APP="$2"; shift 2;;
    --cmd)          CMD="$2"; shift 2;;
    --view)         VIEW="$2"; shift 2;;
    --url)          URL="$2"; shift 2;;
    --keys)         KEYS="$2"; shift 2;;
    --wait)         WAIT_RENDER="$2"; shift 2;;
    --cold-start)   COLD_START_WAIT="$2"; shift 2;;
    --output)       OUTPUT="$2"; shift 2;;
    --no-launch)    NO_LAUNCH=true; shift;;
    -*)             echo "${RED}Unknown flag: $1${RST}"; print_help; exit 1;;
    *)              echo "${RED}Unexpected arg: $1${RST}"; exit 1;;
  esac
done

if [[ -z "$APP" ]]; then
  echo "${RED}Error: --app is required.${RST}"
  print_help
fi

# Resolve --view to --cmd (presets)
case "$VIEW" in
  "") ;;
  graph) CMD="Graph: Open graph view";;
  local) CMD="Graph: Open local graph";;
  daily) CMD="Daily notes: Open today's daily note";;
  *)     echo "${RED}Unknown view preset: $VIEW${RST}"; exit 1;;
esac

# Browser list for --url
BROWSERS=("Safari" "Google Chrome" "Firefox" "Arc" "Brave Browser" "Microsoft Edge" "Opera" "Vivaldi")
is_browser() {
  local a="$1"
  for b in "${BROWSERS[@]}"; do [[ "$a" == "$b" ]] && return 0; done
  return 1
}

mkdir -p "$SCREENSHOT_DIR"
if [[ -z "$OUTPUT" ]]; then
  # Use view or first word of cmd as the slug
  SLUG="$APP"
  if [[ -n "$VIEW" ]]; then
    SLUG="${APP}-${VIEW}"
  elif [[ -n "$CMD" ]]; then
    SLUG="${APP}-$(echo "$CMD" | tr '[:upper:] ' '[:lower:]-' | tr -cd '[:alnum:]-' | head -c 30 | sed 's/-$//')"
  fi
  OUTPUT="$SCREENSHOT_DIR/$(date +%Y-%m-%d-%H%M%S)-${SLUG}.png"
fi

# ---- 1. launch app if not running ---------------------------------------
echo "${BLU}[1/5] Checking $APP${RST}"
if pgrep -fq "${APP}\.app" || pgrep -fq "${APP}\.app/Contents/MacOS"; then
  echo "  ${GRN}OK${RST}  $APP is already running"
else
  if [[ "$NO_LAUNCH" == true ]]; then
    echo "${RED}ERROR: $APP is not running and --no-launch was set${RST}"
    exit 1
  fi
  echo "  Launching $APP..."
  open -a "$APP"
  sleep "$COLD_START_WAIT"
fi

# ---- 2. activate app + verify frontmost --------------------------------
echo "${BLU}[2/5] Activating $APP${RST}"
osascript -e "tell application \"$APP\" to activate" >/dev/null
sleep 1

FRONTMOST=$(osascript -e 'tell application "System Events" to get name of (first process whose frontmost is true)' 2>/dev/null || echo "")
# FRONTMOST can be a comma-separated list of windows if multiple processes
# are frontmost; do a substring check.
if [[ "$FRONTMOST" != *"$APP"* ]]; then
  echo "${RED}ERROR: $APP is not frontmost (frontmost is: '$FRONTMOST')${RST}"
  echo "${YLW}Make sure $APP is open and the window you want is on top.${RST}"
  echo "${RED}ABORTING.${RST}"
  exit 1
fi
echo "  ${GRN}OK${RST}  $APP is frontmost"

# ---- 3. optional navigation --------------------------------------------
echo "${BLU}[3/5] Navigating${RST}"
if [[ -n "$CMD" ]]; then
  echo "  Command palette: $CMD"
  # Open command palette: Cmd+P is the universal shortcut (Obsidian, VS Code, Sublime, Atom).
  osascript -e "tell application \"System Events\" to tell process \"$APP\" to keystroke \"p\" using command down" >/dev/null
  sleep 0.6
  # Clear palette (in case anything was there) and type the command
  osascript -e "tell application \"System Events\" to tell process \"$APP\" to keystroke \"a\" using command down" >/dev/null 2>&1 || true
  sleep 0.2
  # Escape special characters for AppleScript string
  CMD_ESCAPED=$(echo "$CMD" | sed 's/\\/\\\\/g; s/"/\\"/g')
  osascript -e "tell application \"System Events\" to tell process \"$APP\" to keystroke \"$CMD_ESCAPED\"" >/dev/null
  sleep 0.5
  # Press Enter (key code 36 = Return)
  osascript -e "tell application \"System Events\" to tell process \"$APP\" to key code 36" >/dev/null
  sleep "$WAIT_RENDER"
elif [[ -n "$URL" ]]; then
  if ! is_browser "$APP"; then
    echo "${RED}ERROR: --url requires a browser app. Got: $APP${RST}"
    echo "${YLW}Supported browsers: ${BROWSERS[*]}${RST}"
    exit 1
  fi
  echo "  Opening URL: $URL"
  open -a "$APP" "$URL"
  sleep "$WAIT_RENDER"
elif [[ -n "$KEYS" ]]; then
  echo "  Keystrokes: $KEYS"
  IFS=',' read -ra KEY_LIST <<< "$KEYS"
  for k in "${KEY_LIST[@]}"; do
    # Parse "Cmd+N", "Shift+Cmd+P", "Cmd+4" etc.
    MOD=""
    KEY_CHAR=""
    IFS='+' read -ra PARTS <<< "$k"
    for p in "${PARTS[@]}"; do
      case "$p" in
        Cmd|cmd|Command|command)
          MOD="$MOD using command down" ;;
        Shift|shift)
          MOD="$MOD using shift down" ;;
        Alt|alt|Option|option)
          MOD="$MOD using option down" ;;
        Ctrl|ctrl|Control|control)
          MOD="$MOD using control down" ;;
        *)
          KEY_CHAR="$p" ;;
      esac
    done
    if [[ -n "$KEY_CHAR" ]]; then
      # Single character key
      osascript -e "tell application \"System Events\" to tell process \"$APP\" to keystroke \"$KEY_CHAR\"$MOD" >/dev/null
    else
      # Key code (e.g., "36" for Return, "48" for Tab) — used directly
      osascript -e "tell application \"System Events\" to tell process \"$APP\" to key code $KEY_CHAR$MOD" >/dev/null
    fi
    sleep 0.3
  done
  sleep "$WAIT_RENDER"
else
  echo "  (no navigation; capturing current state)"
fi

# ---- 4. capture the front window ---------------------------------------
echo "${BLU}[4/5] Capturing the front window${RST}"
WINDOW_ID=$(osascript -e "tell application \"$APP\" to get id of front window" 2>/dev/null || echo "")
if [[ -z "$WINDOW_ID" ]]; then
  echo "${RED}ERROR: could not get window ID for $APP${RST}"
  echo "${RED}ABORTING.${RST}"
  exit 1
fi
echo "  Window ID: $WINDOW_ID"

# -l: capture by window ID, -o: no window shadow, -x: no sound
screencapture -l "$WINDOW_ID" -o -x "$OUTPUT"
sleep 0.5

# ---- 5. validate -------------------------------------------------------
echo "${BLU}[5/5] Validating capture${RST}"
if [[ ! -f "$OUTPUT" ]]; then
  echo "${RED}ERROR: capture file not created at $OUTPUT${RST}"
  exit 1
fi
SIZE=$(wc -c < "$OUTPUT" | tr -d ' ')
WIDTH=$(sips -g pixelWidth "$OUTPUT" 2>/dev/null | awk -F': ' '/pixelWidth/ {print $2}')
HEIGHT=$(sips -g pixelHeight "$OUTPUT" 2>/dev/null | awk -F': ' '/pixelHeight/ {print $2}')

if [[ -z "$WIDTH" || -z "$HEIGHT" ]]; then
  echo "${RED}ERROR: could not read dimensions of $OUTPUT${RST}"
  exit 1
fi
if [[ $WIDTH -lt 100 || $HEIGHT -lt 100 ]]; then
  echo "${RED}ERROR: capture too small ($WIDTH x $HEIGHT)${RST}"
  exit 1
fi
if [[ $SIZE -lt 5000 ]]; then
  echo "${RED}ERROR: capture suspiciously small ($SIZE bytes) — likely blank screen${RST}"
  exit 1
fi

echo "  ${GRN}OK${RST}  $WIDTH x $HEIGHT, $((SIZE / 1024))KB"
echo ""
echo "${GRN}================================================================${RST}"
echo "${GRN}CAPTURED${RST}"
echo "  App:    $APP"
echo "  Path:   $OUTPUT"
echo "  Size:   $WIDTH x $HEIGHT, $((SIZE / 1024))KB"
echo "${GRN}================================================================${RST}"

# Last line is the path (for easy capture: `$(capture-window.sh --app Foo | tail -1)`)
echo "$OUTPUT"
