#!/usr/bin/env bash
# scripts/pipeline.sh — Single-state pipeline wrappers for ShayanWiki.
#
# Every subcommand maps 1:1 to one engine.py call. Run them as SEPARATE
# bash tool calls so each state transition is visible in the CLI.
#
# Usage:
#   Wiki:    pipeline.sh wiki-{extract,analyze,reconcile,link,index,validate,complete,health,reset}
#   Content: pipeline.sh post-{start,strategy,draft,gate,revise,queue,publish,archive,analyze,complete}
#   Status:  pipeline.sh status | queue | recover
#
# Flags:
#   --yes     Skip confirmation prompts
#   --dry-run Show command without running

set -euo pipefail

VAULT_DIR="${VAULT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENGINE="$VAULT_DIR/scripts/engine.py"
ASSUME_YES=false
DRY_RUN=false

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; DIM='\033[2m'; RST='\033[0m'

die()  { echo "${RED}ERROR: $*${RST}" >&2; exit 1; }
ok()   { echo "${GRN}✓ $*${RST}"; }
warn() { echo "${YLW}⚠ $*${RST}"; }
info() { echo "${BLU}→ $*${RST}"; }

log_pipeline() {
  # Append a JSONL log entry for this pipeline.sh invocation
  local level="${1:-INFO}" source="pipeline.sh" msg="$2"
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%S.000")
  local log_dir="${VAULT_DIR}/logs"
  mkdir -p "$log_dir"
  local log_file="${log_dir}/$(date -u +'%Y-%m-%d').jsonl"
  printf '{"timestamp":"%s","level":"%s","source":"%s","message":"%s","command":"%s"}\n' \
    "$ts" "$level" "$source" "$msg" "${CMD:-unknown}" >> "$log_file"
}

usage() {
  cat <<'USAGE'
Usage: pipeline.sh {wiki|post|status|queue|recover} [args]

Wiki:
  wiki-extract [file]    INGEST — add frontmatter, validate domain
  wiki-analyze            ANALYZE — extract entities, apply thresholds
  wiki-reconcile          RECONCILE — create/update pages with provenance
  wiki-link               LINK — scan for wikilink targets (optional)
  wiki-index              INDEX — update index.md + log.md
  wiki-validate           VALIDATE — run health checks
  wiki-complete           COMPLETE — finish wiki pipeline
  wiki-health             Health check (read-only, no state change)
  wiki-reset              Force reset to IDLE (stuck-state recovery)

Content:
  post-start [about]     SESSION_CAPTURE — load strategy pages + session
  post-strategy           STRATEGY_LOAD — classify session
  post-compile            ICP_WORLD_BUILD — run Content Engine Compiler (6 steps)
  post-draft              DRAFTING — draft posts from core insight
  post-banner             BANNER — auto-generate banners for all queue drafts
  post-gate               GATE_CHECK — auto-runs gates.py (rules from rules.yaml)
  post-revise             REVISING — fix failing gates
  post-queue              QUEUE — show queued drafts
  post-queue-hold         HOLD — keep drafts in queue, reset state to IDLE
  post-publish [id]       PUBLISHING — post to X / LinkedIn
  post-archive             ARCHIVING — move posted drafts
  post-analyze             ANALYZE_POST — review engagement data
  post-complete            COMPLETE_POST — finish content pipeline

General:
  status                  Show current system state
  queue                   Show queue contents (read-only)
  recover                 Diagnose + fix stuck state
USAGE
  exit 0
}

confirm() {
  local prompt="$1"
  if $ASSUME_YES; then return 0; fi
  read -p "${prompt} (y/N) " REPLY
  [[ "$REPLY" == "y" || "$REPLY" == "Y" ]]
}

run_engine() {
  if $DRY_RUN; then echo "${DIM}DRY-RUN: $ENGINE $*${RST}"; return 0; fi
  if $ASSUME_YES; then echo "yes" | python3 "$ENGINE" "$@" 2>&1
  else python3 "$ENGINE" "$@" 2>&1; fi
}

# ─── Wiki wrappers ──────────────────────────────────────────────────────────

cmd_wiki_extract() {   info "WIKI: INGESTING";     run_engine wiki extract "$@"; }
cmd_wiki_analyze() {   info "WIKI: ANALYZING";     run_engine wiki analyze; }
cmd_wiki_reconcile() { info "WIKI: RECONCILING";   run_engine wiki reconcile; }
cmd_wiki_link() {      info "WIKI: LINKING";       run_engine wiki link; }
cmd_wiki_index() {     info "WIKI: INDEXING";      run_engine wiki index; }
cmd_wiki_validate() {  info "WIKI: VALIDATING";    run_engine wiki validate; }
cmd_wiki_complete() {  info "WIKI: COMPLETE";      run_engine wiki complete; }
cmd_wiki_health() {
    info "WIKI: HEALTH CHECK"
    run_engine wiki health
    echo ""
    info "Refreshing architecture canvas..."
    python3 "$VAULT_DIR/scripts/generate-arch-canvas.py"
}
cmd_wiki_reset() {     warn "WIKI: RESET";         run_engine wiki reset; }

# ─── Content wrappers ───────────────────────────────────────────────────────

cmd_post_start() {     info "CONTENT: SESSION_CAPTURE";  run_engine content post "$@"; }
cmd_post_strategy() {  info "CONTENT: STRATEGY_LOAD";    run_engine content strategy; }
cmd_post_compile() {   info "CONTENT: ICP_WORLD_BUILD";  run_engine content compile; }
cmd_post_draft() {     info "CONTENT: DRAFTING";         run_engine content draft; }
cmd_post_banner() {    info "CONTENT: BANNER";           run_engine content banner; }
cmd_post_gate() {      info "CONTENT: GATE_CHECK";       run_engine content gate; }
cmd_post_revise() {    info "CONTENT: REVISING";         run_engine content revise; }
cmd_post_queue() {     info "CONTENT: QUEUE";           run_engine content queue; }
cmd_post_hold() {      info "CONTENT: HOLD";             run_engine content hold; }
cmd_post_publish() {
  info "CONTENT: PUBLISHING"
  # engine.py validates + transitions; then dispatches to the platform publisher.
  run_engine content publish "$@"
  local target="${1:-}"
  if [[ -z "$target" || "$target" == "all" ]]; then
    for f in "$VAULT_DIR/content/queue"/*.md; do
      [[ -f "$f" ]] || continue
      local plat; plat=$(grep -m1 '^platform:' "$f" | awk '{print $2}')
      case "$plat" in
        x|twitter)       python3 "$VAULT_DIR/scripts/post_x.py" "$f" --yes ;;
        linkedin)        python3 "$VAULT_DIR/scripts/post_linkedin.py" "$f" --yes ;;
      esac
    done
  else
    local f="$VAULT_DIR/content/queue/$target"
    [[ -f "$f" ]] || f="$(find "$VAULT_DIR/content/queue" -name "${target}*" -print -quit)"
    [[ -f "$f" ]] || die "draft not found: $target"
    local plat; plat=$(grep -m1 '^platform:' "$f" | awk '{print $2}')
    case "$plat" in
      x|twitter)       python3 "$VAULT_DIR/scripts/post_x.py" "$f" --yes ;;
      linkedin)        python3 "$VAULT_DIR/scripts/post_linkedin.py" "$f" --yes ;;
      *)               die "no publisher for platform: $plat" ;;
    esac
  fi
}
cmd_post_archive() {   info "CONTENT: ARCHIVING";        run_engine content archive; }
cmd_post_analyze() {   info "CONTENT: ANALYZING_POST";   run_engine content analyze; }
cmd_post_complete() {  info "CONTENT: COMPLETE_POST";    run_engine content complete; }

# ─── General wrappers ───────────────────────────────────────────────────────

cmd_status()  { run_engine status; }
cmd_queue()   { run_engine queue; }
cmd_recover() { run_engine recover; }

# ─── Main ───────────────────────────────────────────────────────────────────

# Parse global flags
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --yes|-y)     ASSUME_YES=true ;;
    --dry-run)    DRY_RUN=true ;;
    -h|--help)    usage ;;
    *)            ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]}"

[[ $# -lt 1 ]] && usage

CMD="$1"; shift

log_pipeline "INFO" "Running command"

case "$CMD" in
  wiki-extract)      cmd_wiki_extract "$@" ;;
  wiki-analyze)      cmd_wiki_analyze ;;
  wiki-reconcile)    cmd_wiki_reconcile ;;
  wiki-link)         cmd_wiki_link ;;
  wiki-index)        cmd_wiki_index ;;
  wiki-validate)     cmd_wiki_validate ;;
  wiki-complete)     cmd_wiki_complete ;;
  wiki-health)       cmd_wiki_health ;;
  wiki-reset)        cmd_wiki_reset ;;

  post-start)        cmd_post_start "$@" ;;
  post-strategy)     cmd_post_strategy ;;
  post-compile)      cmd_post_compile ;;
  post-draft)        cmd_post_draft ;;
  post-banner)       cmd_post_banner ;;
  post-gate)         cmd_post_gate ;;
  post-revise)       cmd_post_revise ;;
  post-queue)        cmd_post_queue ;;
  post-queue-hold)   cmd_post_hold ;;
  post-publish)      cmd_post_publish "$@" ;;
  post-archive)      cmd_post_archive ;;
  post-analyze)      cmd_post_analyze ;;
  post-complete)     cmd_post_complete ;;

  status)            cmd_status ;;
  queue)             cmd_queue ;;
  recover)           cmd_recover ;;
  wiki)              die "Use wiki-extract, wiki-analyze, etc. (dash, not space)" ;;
  post)              die "Use post-start, post-gate, etc. (dash, not space)" ;;
  *)                 die "Unknown command: $CMD. See pipeline.sh --help" ;;
esac
