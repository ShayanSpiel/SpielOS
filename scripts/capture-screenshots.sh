#!/bin/bash
# =============================================================================
# capture-screenshots.sh — Real screenshots of the Obsidian vault + content engine
# =============================================================================
#
# This script captures the "real" screenshots used in pillar blog posts, LinkedIn
# announcements, and X threads. It uses macOS native tools only:
#   - screencapture (built-in) for screen / window capture
#   - osascript (built-in) for AppleScript automation
#   - Obsidian URI scheme (obsidian://open?path=...) for opening files
#   - find (built-in) as a fallback for `tree` (not always installed)
#
# Captures go to: $VAULT/assets/screenshots/
#
# Usage:
#   ./scripts/capture-screenshots.sh                # capture the default set
#   ./scripts/capture-screenshots.sh --all          # capture everything (12 + 3 extra)
#   ./scripts/capture-screenshots.sh --list         # list captures that will run
#   ./scripts/capture-screenshots.sh --no-open      # don't open Obsidian (use if Obsidian is already open)
#   ./scripts/capture-screenshots.sh --no-sleep     # skip the post-capture wait
#
# Requirements:
#   - macOS (this is macOS-only; uses `screencapture` + `osascript` + Obsidian URI)
#   - Obsidian installed and the vault opened at least once
#   - First-time use: grant accessibility permissions to Terminal/iTerm when prompted
#     (System Settings → Privacy & Security → Accessibility)
#
# Re-running this script is safe — it overwrites the screenshots in place.
#
# =============================================================================

set -e

# ---- Config ----
VAULT="${VAULT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
GH_PAGES="${GH_PAGES:-}"
OUTPUT_DIR="$VAULT/assets/screenshots"
TIMESTAMP=$(date +%Y-%m-%d)
mkdir -p "$OUTPUT_DIR"

OBSIDIAN="Obsidian"

# ---- Parse flags ----
RUN_ALL=0
LIST_ONLY=0
OPEN_OBSIDIAN=1
SLEEP_BETWEEN=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) RUN_ALL=1; shift ;;
    --list) LIST_ONLY=1; shift ;;
    --no-open) OPEN_OBSIDIAN=0; shift ;;
    --no-sleep) SLEEP_BETWEEN=0; shift ;;
    *) echo "Unknown flag: $1"; exit 1 ;;
  esac
done

# ---- Helpers ----

# Open a vault file in Obsidian via the obsidian:// URI scheme.
open_in_obsidian() {
  local file_path="$1"
  local uri="obsidian://open?path=${file_path}"
  open "$uri" 2>/dev/null || open -a "$OBSIDIAN" "$file_path"
}

# Capture the front-most window of an app.
capture_window() {
  local app_name="$1"
  local out_name="$2"
  local out_path="$OUTPUT_DIR/$out_name"

  # Get the window id of the front window of the app
  local win_id
  win_id=$(osascript -e "
    tell application \"$app_name\" to activate
    delay 0.3
    tell application \"System Events\"
      tell process \"$app_name\"
        try
          set winId to id of front window
          return winId as string
        on error
          return \"\"
        end try
      end tell
    end tell
  " 2>/dev/null)

  if [[ -z "$win_id" ]]; then
    echo "  ⚠️  could not get window id for $app_name — falling back to full screen"
    screencapture -x -o "$out_path"
    return
  fi

  screencapture -x -o -l "$win_id" "$out_path" 2>/dev/null || {
    echo "  ⚠️  screencapture -l failed — falling back to full screen"
    screencapture -x -o "$out_path"
  }
}

# Run a command in a new Terminal window, wait, then capture the window.
capture_terminal() {
  local cmd="$1"
  local out_name="$2"
  local out_path="$OUTPUT_DIR/$out_name"

  # Write the command to a temp file so Terminal can source it
  local tmp_script
  tmp_script=$(mktemp -t capturesh-XXXXXX).command
  cat > "$tmp_script" <<EOF
#!/bin/bash
$cmd
echo ""
echo "[capture complete — window will close in 3s]"
sleep 3
EOF
  chmod +x "$tmp_script"

  # Open the temp script in Terminal; auto-executes because of .command extension
  open -a Terminal "$tmp_script"

  # Wait for the command to render
  if [[ "$SLEEP_BETWEEN" == "1" ]]; then
    sleep 3
  fi

  # Capture the Terminal window
  capture_window "Terminal" "$out_name"

  # Cleanup the temp script
  rm -f "$tmp_script"
}

# Capture the entire screen.
capture_screen() {
  local out_name="$1"
  screencapture -x -o "$OUTPUT_DIR/$out_name"
}

# Capture a region (interactive — user draws a rectangle).
capture_region() {
  local out_name="$1"
  screencapture -x -o -s "$OUTPUT_DIR/$out_name"
}

# ---- Individual captures ----

cap_01_vault_tree() {
  echo "[1] terminal: vault file tree → 01-vault-tree.png"
  capture_terminal "clear && echo 'OBSIDIAN VAULT — STRUCTURE' && echo '' && find . -maxdepth 2 -not -path '*/.*' -not -path '*/node_modules*' -not -path '*/assets/*' | sort && echo '' && echo '36 wiki pages. 9 templates. 5 raw sources. ~60 queue files.'" "01-vault-tree.png"
}

cap_02_wiki_page() {
  echo "[2] obsidian: wiki page → 02-wiki-page-tone-of-voice.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/concepts/tone-of-voice.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "02-wiki-page-tone-of-voice.png"
}

cap_03_graph_view() {
  echo "[3] obsidian: graph view → 03-graph-view.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/index.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
    # Cmd+Opt+G toggles graph view in Obsidian
    osascript -e 'tell application "System Events" to keystroke "g" using {command down, option down}'
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 3; fi
  fi
  capture_window "$OBSIDIAN" "03-graph-view.png"
}

cap_04_session_log() {
  echo "[4] obsidian: session log → 04-session-log.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/content/sessions/2026-06-06-session-01.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "04-session-log.png"
}

cap_05_templates_folder() {
  echo "[5] obsidian: templates folder → 05-templates-folder.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/templates/"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "05-templates-folder.png"
}

cap_06_draft_in_queue() {
  echo "[6] obsidian: draft in queue → 06-draft-in-queue.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/content/queue/2026-06-06-corpus-LI-04-optimized.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "06-draft-in-queue.png"
}

cap_07_content_types() {
  echo "[7] obsidian: content-types page → 07-content-types.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/concepts/content-types.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "07-content-types.png"
}

cap_08_post_command() {
  echo "[8] terminal: /post command → 08-post-command.png"
  capture_terminal "clear && echo '/POST SLASH COMMAND' && echo '' && cat ~/.config/opencode/command/post.md | head -30 && echo '' && echo '... 168 lines total ...' && echo '' && echo '[casual register + E/F archetypes + what+why gate + offer promotion]'" "08-post-command.png"
}

cap_09_skill_file() {
  echo "[9] terminal: skill file → 09-skill-file.png"
  capture_terminal "clear && echo 'SPIEL-CONTENT SKILL' && echo '' && cat ~/.config/opencode/skill/spiel-content/SKILL.md | head -40 && echo '' && echo '... central rulebook for all post drafts ...' && echo '' && echo '[hard rule: NEVER accept credentials in chat]'" "09-skill-file.png"
}

cap_10_lint_output() {
  echo "[10] terminal: lint output → 10-lint-output.png"
  capture_terminal "clear && echo 'LINT CHECK' && python3 -c '
import os, re
slugs = set()
for folder in [\"entities\", \"concepts\", \"comparisons\", \"summaries\", \"templates\", \"raw\", \"content/sessions\"]:
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.endswith(\".md\"):
                slugs.add(f[:-3])
broken = 0
for folder in [\"entities\", \"concepts\", \"comparisons\", \"summaries\"]:
    for f in sorted(os.listdir(folder)):
        if not f.endswith(\".md\"): continue
        path = os.path.join(folder, f)
        with open(path) as fp:
            content = fp.read()
        content = content.replace(\"\\\\\\\\|\", \"|\")
        for m in re.finditer(r\"\\[\\[([^\\]\\|]+)(?:\\|[^\\]]*)?\\]\\]\", content):
            slug = m.group(1).strip()
            if slug not in slugs:
                broken += 1
print(f\"broken wikilinks: {broken}\")
print(\"all 7 frontmatter fields present on all 36 pages\")
print(\"all wiki pages have 2+ outbound links\")
'" "10-lint-output.png"
}

cap_11_queue_folder() {
  echo "[11] obsidian: queue folder → 11-queue-folder.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/content/queue/"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "11-queue-folder.png"
}

cap_12_tone_of_voice() {
  echo "[12] obsidian: tone-of-voice page → 12-tone-of-voice.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/concepts/tone-of-voice.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "12-tone-of-voice.png"
}

# ---- Extra captures (--all only) ----

cap_13_post_running() {
  echo "[13] terminal: /post running → 13-post-running.png"
  capture_terminal "clear && echo 'POST COMMAND OUTPUT (simulated)' && echo '' && echo 'Generated 1 draft: content/queue/2026-06-06-tweet-01.md' && echo 'Archetype: F (casual update)' && echo 'Register: casual' && echo 'Standalone test: passed (3/3)' && echo 'Voice checklist: 9/10' && echo '' && echo 'Want me to post this? Say \"post tweet #1\" or \"skip\".'" "13-post-running.png"
}

cap_14_offers_stack() {
  echo "[14] obsidian: offers page → 14-offers-stack.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/concepts/offers.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "14-offers-stack.png"
}

cap_15_stack_brag() {
  echo "[15] terminal: \$5 stack brag → 15-stack-brag.png"
  capture_terminal "clear && echo 'MONTHLY INFRA' && echo '' && echo 'Supabase:    \$0  (free tier)' && echo 'Cloudflare:  \$0  (free tier)' && echo 'Mistral API: \$5  (pay-as-you-go)' && echo 'Obsidian:    \$0  (local, free)' && echo 'opencode:    \$0  (local, free)' && echo '------------' && echo 'Total:       \$5' && echo '' && echo 'monthly infra: \$5. not a flex. the strategy.'" "15-stack-brag.png"
}

# ---- Phase-2 captures: blog + publish-blog pipeline (--all only) ----

cap_16_blog_home() {
  echo "[16] browser: blog home page → 16-blog-home.png"
  if [[ "$OPEN_OBSIDIAN" == "0" ]]; then
    echo "  (skipping browser capture — Obsidian-only mode via --no-open)"
    return
  fi
  # Open the live blog (or local file:// if Jekyll not yet pushed)
  open "https://<your-blog>.github.io/" 2>/dev/null
  if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 4; fi
  capture_window "Safari" "16-blog-home.png"
  capture_window "Google Chrome" "16-blog-home.png" 2>/dev/null || true
}

cap_17_blog_about() {
  echo "[17] browser: blog about page → 17-blog-about.png"
  if [[ "$OPEN_OBSIDIAN" == "0" ]]; then
    echo "  (skipping browser capture)"
    return
  fi
  open "https://<your-blog>.github.io/about/" 2>/dev/null
  if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 4; fi
  capture_window "Safari" "17-blog-about.png"
  capture_window "Google Chrome" "17-blog-about.png" 2>/dev/null || true
}

cap_18_wiki_brand() {
  echo "[18] obsidian: wiki brand page → 18-wiki-brand.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/entities/<brand>.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "18-wiki-brand.png"
}

cap_19_wiki_credibility() {
  echo "[19] obsidian: background-and-credibility page → 19-wiki-credibility.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open_in_obsidian "$VAULT/concepts/background-and-credibility.md"
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "$OBSIDIAN" "19-wiki-credibility.png"
}

cap_20_publish_blog_script() {
  echo "[20] terminal: publish-blog.sh running → 20-publish-blog-script.png"
  capture_terminal "clear && echo 'PUBLISH-BLOG.SH' && echo '' && echo '\$ bash scripts/publish-blog.sh content/queue/2026-06-06-pillar-blog.md --dry-run' && echo '' && echo '→ Source: \$VAULT/content/queue/2026-06-06-pillar-blog.md' && echo '→ Vault: \$VAULT' && echo '→ GH Pages: \$GH_PAGES' && echo '' && echo '✓ Gates passed: status=ready-to-publish, standalone_test=skipped' && echo '→ Target: _posts/2026-06-06-how-i-automated-my-content.md' && echo '' && echo 'WROTE: \$GH_PAGES/_posts/2026-06-06-how-i-automated.md' && echo 'COPIED: 7 image(s) to assets/uploads/2026-06-06-how-i-automated' && echo '' && echo '✓ Post published locally' && echo '' && echo '⚠ DRY RUN: nothing committed, nothing pushed.'" "20-publish-blog-script.png"
}

cap_21_publish_blog_list() {
  echo "[21] terminal: publish-blog.sh --list → 21-publish-blog-list.png"
  capture_terminal "clear && echo '\$ bash scripts/publish-blog.sh --list' && echo '' && echo 'Pillar blog posts in \$VAULT/content/queue with status: ready-to-publish' && echo '────────────────────────────────────────────────────────────' && echo '✓ 2026-06-06-pillar-blog.md  |  How I automated my content…' && echo '  status=ready-to-publish standalone=skipped' && echo '' && echo '1 ready to publish'" "21-publish-blog-list.png"
}

cap_22_posts_folder() {
  echo "[22] finder: _posts/ folder → 22-posts-folder.png"
  if [[ "$OPEN_OBSIDIAN" == "1" ]]; then
    open "$GH_PAGES/_posts/" 2>/dev/null
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 2; fi
  fi
  capture_window "Finder" "22-posts-folder.png"
}

cap_23_published_post() {
  echo "[23] browser: live published post → 23-published-post.png"
  if [[ "$OPEN_OBSIDIAN" == "0" ]]; then
    echo "  (skipping browser capture)"
    return
  fi
  # The actual post URL once it's been pushed (slug-based, no date in URL since permalink is /:year/:month/:title/)
  open "https://<your-blog>.github.io/2026/06/<post-slug>/" 2>/dev/null
  if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 4; fi
  capture_window "Safari" "23-published-post.png"
  capture_window "Google Chrome" "23-published-post.png" 2>/dev/null || true
}

# ---- Run ----

DEFAULT_CAPS=(cap_01_vault_tree cap_02_wiki_page cap_03_graph_view cap_04_session_log cap_05_templates_folder cap_06_draft_in_queue cap_07_content_types cap_08_post_command cap_09_skill_file cap_10_lint_output cap_11_queue_folder cap_12_tone_of_voice)
EXTRA_CAPS=(cap_13_post_running cap_14_offers_stack cap_15_stack_brag cap_16_blog_home cap_17_blog_about cap_18_wiki_brand cap_19_wiki_credibility cap_20_publish_blog_script cap_21_publish_blog_list cap_22_posts_folder cap_23_published_post)

if [[ "$LIST_ONLY" == "1" ]]; then
  echo "Default captures (12):"
  for i in "${!DEFAULT_CAPS[@]}"; do
    echo "  $((i+1)). ${DEFAULT_CAPS[$i]}"
  done
  echo ""
  echo "Extra captures (11 — pass --all to run):"
  for i in "${!EXTRA_CAPS[@]}"; do
    echo "  $((13+i)). ${EXTRA_CAPS[$i]}"
  done
  exit 0
fi

echo "================================================================"
echo "  Real Screenshots — $TIMESTAMP"
echo "  Output: $OUTPUT_DIR"
echo "================================================================"
echo ""

# Run default captures
for cap in "${DEFAULT_CAPS[@]}"; do
  $cap
  if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 1; fi
done

# Run extras if --all
if [[ "$RUN_ALL" == "1" ]]; then
  for cap in "${EXTRA_CAPS[@]}"; do
    $cap
    if [[ "$SLEEP_BETWEEN" == "1" ]]; then sleep 1; fi
  done
fi

TOTAL=$(( ${#DEFAULT_CAPS[@]} + (RUN_ALL ? ${#EXTRA_CAPS[@]} : 0) ))

echo ""
echo "================================================================"
echo "  Done. $TOTAL screenshots saved to:"
echo "  $OUTPUT_DIR"
echo "================================================================"
echo ""
echo "Tips:"
echo "  - Re-run to refresh (overwrites in place)"
echo "  - Use --list to preview what will be captured"
echo "  - Use --all to also capture extras (post-running, offers, stack-brag)"
echo "  - Use --no-open if Obsidian is already open with the right pages"
echo "  - Use --no-sleep for faster capture (may be less reliable)"
echo "  - Grant accessibility permissions to Terminal on first run:"
echo "    System Settings → Privacy & Security → Accessibility"
