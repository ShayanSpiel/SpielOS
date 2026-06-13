#!/usr/bin/env bash
# scripts/publish-blog.sh — vault pillar blog → GitHub Pages
#
# Publishes a pillar blog post from the vault (content/queue/*.md) to the
# GitHub Pages Jekyll site (set $GH_PAGES to your repo, e.g. ~/yourname.github.io),
# with
# referenced screenshots copied to assets/uploads/ and frontmatter
# transformed to Jekyll format. Then git add + commit + (optional) push.
#
# Usage:
#   bash scripts/publish-blog.sh <pillar-blog-file>
#   bash scripts/publish-blog.sh <pillar-blog-file> --dry-run
#   bash scripts/publish-blog.sh <pillar-blog-file> --yes
#   bash scripts/publish-blog.sh --list
#
# Flags:
#   --list      List all pillar blog posts in content/queue/ that are
#               eligible to publish (status: ready-to-publish)
#   --dry-run   Do everything except git push. Show the diff and ask.
#   --yes       Skip the "are you sure?" prompt; push automatically.
#   --force     Publish even if status != ready-to-publish or
#               standalone_test != passed|skipped. USE WITH CARE.
#   --no-build  Skip the local `bundle exec jekyll build` step.
#
# Requirements:
#   - bash 4+, python3, git
#   - The vault is at $VAULT (default: $VAULT_DIR from .env, or the engine's own dir)
#   - The GH Pages repo is at $GH_PAGES (no default — set this to your GitHub Pages repo)
#   - The GH Pages repo is initialized as a git repo with a remote
#
# Behavior:
#   - Re-runnable (idempotent): if the target file already exists, asks
#     before overwriting
#   - Standalone test is a hard gate: standalone_test must be
#     `passed` or `skipped` (or --force)
#   - Status must be `ready-to-publish` (or --force)
#   - Image references in the post body that point into the vault's
#     assets/screenshots/ are copied to GH Pages
#     assets/uploads/YYYY-MM-DD-slug/ and rewritten as relative paths
#   - Other local image references are LEFT ALONE (likely broken on
#     the live site, but flagged for the user to review)
#   - Git commit is always created; git push only with --yes

set -euo pipefail

# ─── Config ────────────────────────────────────────────────────────────────
VAULT="${VAULT:-$(cd "$(dirname "$0")/.." && pwd)}"
GH_PAGES="${GH_PAGES:-}"  # Set to your GitHub Pages repo path, e.g. $HOME/yourusername.github.io
GH_URL="${GH_URL:-}"       # Your published URL, e.g. https://yourusername.github.io
QUEUE_DIR="$VAULT/content/queue"
POSTS_DIR="$GH_PAGES/_posts"
UPLOADS_DIR="$GH_PAGES/assets/uploads"
SCREENSHOTS_DIR="$VAULT/assets/screenshots"

# ─── Colors ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ─── Helpers ───────────────────────────────────────────────────────────────
die() { printf "${RED}✘ %s${NC}\n" "$*" >&2; exit 1; }
ok()  { printf "${GREEN}✓ %s${NC}\n" "$*"; }
warn(){ printf "${YELLOW}⚠ %s${NC}\n" "$*"; }
info(){ printf "${BLUE}→ %s${NC}\n" "$*"; }
hr()  { printf "%.0s─" {1..60}; printf "\n"; }

# ─── Arg parsing ───────────────────────────────────────────────────────────
LIST_MODE=false
DRY_RUN=false
YES_FLAG=false
FORCE_FLAG=false
SKIP_BUILD=false
SOURCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) LIST_MODE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --yes|-y) YES_FLAG=true; shift ;;
    --force) FORCE_FLAG=true; shift ;;
    --no-build) SKIP_BUILD=true; shift ;;
    -h|--help)
      sed -n '2,30p' "$0" | sed 's/^# //;s/^#//'
      exit 0
      ;;
    -*) die "Unknown flag: $1" ;;
    *)
      [[ -z "$SOURCE" ]] || die "Multiple source files given: $SOURCE and $1"
      SOURCE="$1"
      shift
      ;;
  esac
done

# ─── Sanity checks ─────────────────────────────────────────────────────────
[[ -d "$VAULT" ]]      || die "Vault not found: $VAULT (set \$VAULT to override)"
[[ -d "$GH_PAGES" ]]   || die "GH Pages repo not found: $GH_PAGES (set \$GH_PAGES to override)"
[[ -d "$GH_PAGES/.git" ]] || die "$GH_PAGES is not a git repo"
[[ -d "$QUEUE_DIR" ]]  || die "Queue dir not found: $QUEUE_DIR"
[[ -d "$POSTS_DIR" ]]  || die "Jekyll _posts dir not found: $POSTS_DIR"

command -v python3 >/dev/null || die "python3 not found in PATH"
command -v git >/dev/null      || die "git not found in PATH"

# ─── List mode ─────────────────────────────────────────────────────────────
if $LIST_MODE; then
  echo "Pillar blog posts in $QUEUE_DIR with status: ready-to-publish"
  hr
  count=0
  for f in "$QUEUE_DIR"/*-pillar-blog.md; do
    [[ -f "$f" ]] || continue
    status=$(python3 -c "
import re, sys
with open('$f') as fh: c = fh.read()
m = re.search(r'^status:\s*(.+)$', c, re.M)
print(m.group(1).strip() if m else 'unknown')
")
    title=$(python3 -c "
import re, sys
with open('$f') as fh: c = fh.read()
m = re.search(r'^title:\s*(.+)$', c, re.M)
print(m.group(1).strip() if m else 'untitled')
")
    standalone=$(python3 -c "
import re, sys
with open('$f') as fh: c = fh.read()
m = re.search(r'^standalone_test:\s*(.+)$', c, re.M)
print(m.group(1).strip() if m else 'unknown')
")
    if [[ "$status" == "ready-to-publish" ]]; then
      printf "${GREEN}✓${NC} %-40s | %s\n  status=%s standalone=%s\n" "$(basename "$f")" "$title" "$status" "$standalone"
      count=$((count+1))
    else
      printf "${YELLOW}–${NC} %-40s | %s\n  status=%s standalone=%s\n" "$(basename "$f")" "$title" "$status" "$standalone"
    fi
  done
  hr
  echo "$count ready to publish"
  exit 0
fi

# ─── Source file ───────────────────────────────────────────────────────────
[[ -n "$SOURCE" ]] || die "Usage: $0 <pillar-blog-file> [--dry-run] [--yes] [--force]"
[[ -f "$SOURCE" ]] || die "Source file not found: $SOURCE"

# Resolve to absolute path
SOURCE="$(cd "$(dirname "$SOURCE")" && pwd)/$(basename "$SOURCE")"

info "Source: $SOURCE"
info "Vault: $VAULT"
info "GH Pages: $GH_PAGES"
hr

# ─── Extract frontmatter fields (via Python helper script) ─────────────────
# The script dir contains a parse-frontmatter.py helper that reads YAML
# frontmatter and outputs shell-safe `export KEY=value` lines on stdout.
# We source those lines into the current shell to set TITLE, STATUS, etc.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FM_FILE="$(mktemp -t publish-blog-fm.XXXXXX)"
trap 'rm -f "$FM_FILE"' EXIT

python3 "$SCRIPT_DIR/parse-frontmatter.py" "$SOURCE" > "$FM_FILE" \
  || die "Failed to parse frontmatter from $SOURCE"

[[ ! -s "$FM_FILE" ]] && die "No frontmatter found in $SOURCE"

# shellcheck source=/dev/null
source "$FM_FILE"

[[ -z "${TITLE:-}" ]]  && die "Missing 'title' in frontmatter"
[[ -z "${STATUS:-}" ]] && die "Missing 'status' in frontmatter"

# ─── Gates ─────────────────────────────────────────────────────────────────
if [[ "$STATUS" != "ready-to-publish" ]] && ! $FORCE_FLAG; then
  die "Status is '$STATUS', not 'ready-to-publish'. Set status: ready-to-publish in the frontmatter, or use --force."
fi

if ! $FORCE_FLAG; then
  if [[ "$STANDALONE" != "passed" && "$STANDALONE" != "skipped" ]]; then
    die "standalone_test is '$STANDALONE', not 'passed' or 'skipped'. Run the standalone-quality-test and update the frontmatter, or use --force."
  fi
fi

ok "Gates passed: status=$STATUS, standalone_test=$STANDALONE"

# ─── Compute target ────────────────────────────────────────────────────────
# Extract YYYY-MM-DD from source filename (the first 10 chars of basename)
BASE=$(basename "$SOURCE")
DATE_PREFIX="${BASE:0:10}"
[[ "$DATE_PREFIX" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "Source filename must start with YYYY-MM-DD-: $BASE"

# Slugify title: lowercase, replace non-alphanumeric with hyphens, collapse
SLUG=$(python3 -c "
import re
t = '''$TITLE'''.lower()
t = re.sub(r'[^a-z0-9]+', '-', t)
t = t.strip('-')
print(t[:80] or 'untitled')
")

TARGET="$POSTS_DIR/${DATE_PREFIX}-${SLUG}.md"
TARGET_REL="${TARGET#$GH_PAGES/}"

info "Target: $TARGET_REL"

if [[ -f "$TARGET" ]]; then
  warn "Target file already exists: $TARGET_REL"
  if ! $YES_FLAG && ! $FORCE_FLAG; then
    read -p "Overwrite? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || die "Aborted."
  fi
fi

# ─── Transform frontmatter + copy screenshots ──────────────────────────────
UPLOAD_SUBDIR="assets/uploads/${DATE_PREFIX}-${SLUG}"
UPLOAD_TARGET="$GH_PAGES/$UPLOAD_SUBDIR"

# Create upload dir
mkdir -p "$UPLOAD_TARGET"

# Use Python to do the full transform — frontmatter + image rewrites — atomically
python3 - "$SOURCE" "$TARGET" "$UPLOAD_SUBDIR" "$SCREENSHOTS_DIR" "$DATE_PREFIX" "$SLUG" <<'PYEOF'
import re, sys, os, shutil, pathlib

source, target, upload_subdir, screenshots_dir, date_prefix, slug = sys.argv[1:7]
# upload_subdir is relative to GH Pages root (e.g. assets/uploads/2026-06-06-foo).
# Resolve it against GH_PAGES_ROOT (one level up from the _posts/ target).
gh_pages_root = os.path.dirname(os.path.dirname(target))
upload_subdir_abs = os.path.join(gh_pages_root, upload_subdir)

with open(source) as f:
    content = f.read()

# Split frontmatter and body
m = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
if not m:
    print("No frontmatter", file=sys.stderr); sys.exit(1)
fm_text, body = m.group(1), m.group(2)

# Parse frontmatter (simple — only the fields we know about)
def parse_fm(text):
    fields = {}
    current_key = None
    for line in text.split('\n'):
        m_kv = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if m_kv:
            key, val = m_kv.group(1), m_kv.group(2).strip()
            if val.startswith('[') and val.endswith(']'):
                # list
                inner = val[1:-1].strip()
                if inner:
                    fields[key] = [s.strip().strip('"').strip("'") for s in inner.split(',')]
                else:
                    fields[key] = []
            else:
                # scalar
                fields[key] = val.strip('"').strip("'")
            current_key = key
    return fields

fm = parse_fm(fm_text)

# Build Jekyll frontmatter (keep only Jekyll-relevant fields)
title = fm.get('title', 'Untitled')
# Tags: from frontmatter tags list, or empty
tags = fm.get('tags', [])
if isinstance(tags, str):
    tags = [t.strip() for t in tags.strip('[]').split(',') if t.strip()]
description = fm.get('description', '')

jekyll_fm_lines = [
    '---',
    'layout: post',
    f'title: "{title}"',
    f'date: {date_prefix} 09:00:00 +0000',
]
if tags:
    jekyll_fm_lines.append('tags:')
    for t in tags:
        jekyll_fm_lines.append(f'  - {t}')
if description:
    jekyll_fm_lines.append(f'description: "{description}"')

# Find image references in body
# Patterns: ![alt](path), <img src="path">, src="path"
img_patterns = [
    re.compile(r'!\[([^\]]*)\]\(([^)]+)\)'),
    re.compile(r'<img\s+[^>]*src="([^"]+)"', re.IGNORECASE),
    re.compile(r'src="([^"]+)"'),
]

copied_files = []
flagged_paths = set()

def process_path(path):
    # Skip http(s) and absolute paths and data: URIs
    if path.startswith(('http://', 'https://', 'data:', '/')):
        return path
    # Skip if it's already a Jekyll-relative path
    if path.startswith('assets/'):
        return path
    # Try to resolve from vault screenshots dir
    if os.path.isabs(path):
        src_abs = path
    else:
        # Try relative to source file first
        src_abs = os.path.join(os.path.dirname(source), path)
        if not os.path.isfile(src_abs):
            # Try relative to vault root
            vault_root = os.path.dirname(os.path.dirname(source))  # queue is 2 levels deep
            src_abs = os.path.normpath(os.path.join(vault_root, path))
            if not os.path.isfile(src_abs):
                # Try absolute interpretation from vault
                src_abs = os.path.join(os.path.dirname(source), '..', '..', path)
                src_abs = os.path.normpath(src_abs)

    if os.path.isfile(src_abs):
        # Copy to upload subdir
        fname = os.path.basename(src_abs)
        dst = os.path.join(upload_subdir_abs, fname)
        shutil.copy2(src_abs, dst)
        rel = os.path.relpath(dst, os.path.dirname(target))
        copied_files.append((src_abs, dst, rel))
        return rel
    else:
        flagged_paths.add(path)
        return path

# Process markdown image syntax
def repl_md(m):
    alt, path = m.group(1), m.group(2)
    new_path = process_path(path)
    return f'![{alt}]({new_path})'

def repl_html_src(m):
    return m.group(0).replace(m.group(1), process_path(m.group(1)))

new_body = img_patterns[0].sub(repl_md, body)
new_body = img_patterns[1].sub(repl_html_src, new_body)
new_body = img_patterns[2].sub(repl_html_src, new_body)

# ─── Convert Obsidian wikilinks to plain text ──────────────────────────────
# [[page]]          -> page
# [[page|display]]  -> display
# Patterns:
#   [[X|Y]]  -> Y
#   [[X]]    -> X
wikilink_with_display = re.compile(r'\[\[([^\]\|]+)\|([^\]]+)\]\]')
wikilink_simple = re.compile(r'\[\[([^\]]+)\]\]')

def repl_wikilink_display(m):
    return m.group(2).strip()
def repl_wikilink_simple(m):
    return m.group(1).strip()

new_body = wikilink_with_display.sub(repl_wikilink_display, new_body)
new_body = wikilink_simple.sub(repl_wikilink_simple, new_body)

# ─── Strip leading H1 from body (layout renders it from frontmatter) ────────
# The post.html layout renders <h1>{{ page.title }}</h1> automatically, so
# having a `# Title` H1 at the top of the body would duplicate the title.
# Strip the first H1 if it matches the frontmatter title (case-insensitive,
# ignoring punctuation).
def strip_leading_h1(body_text, fm_title):
    lines = body_text.split('\n')
    if not lines:
        return body_text
    if not lines[0].lstrip().startswith('# '):
        return body_text
    h1_text = lines[0].lstrip()[2:].strip()
    def norm(s):
        return re.sub(r'[^a-z0-9]+', '', s.lower())
    if norm(h1_text) == norm(fm_title):
        # Remove this line + one optional blank line after
        del lines[0]
        if lines and lines[0].strip() == '':
            del lines[0]
    return '\n'.join(lines)

new_body = strip_leading_h1(new_body, title)

# Write target
jekyll_fm = '\n'.join(jekyll_fm_lines) + '\n'
with open(target, 'w') as f:
    f.write(jekyll_fm + '---\n' + new_body)

# Print report
print(f"WROTE: {target}")
print(f"COPIED: {len(copied_files)} image(s) to {upload_subdir}")
for src, dst, rel in copied_files:
    print(f"  - {os.path.basename(src)} → {rel}")
if flagged_paths:
    print(f"FLAGGED: {len(flagged_paths)} image(s) not found in vault (left as-is, will be broken on live site unless fixed manually):")
    for p in flagged_paths:
        print(f"  - {p}")
PYEOF

hr
ok "Post published locally: $TARGET_REL"
# Python script already prints a FLAGGED list above if any images were missing.

# ─── Local Jekyll build (optional) ─────────────────────────────────────────
if ! $SKIP_BUILD; then
  if command -v bundle >/dev/null && [[ -f "$GH_PAGES/Gemfile" ]]; then
    info "Running local Jekyll build to verify (bundle exec jekyll build)..."
    (cd "$GH_PAGES" && bundle exec jekyll build --quiet) \
      && ok "Jekyll build succeeded" \
      || warn "Jekyll build failed — the post may have syntax issues. Review and try again."
  else
    info "Skipping Jekyll build (bundle or Gemfile not found at $GH_PAGES)"
  fi
fi

# ─── Git stage + commit + (optional) push ──────────────────────────────────
hr
info "Staging files in $GH_PAGES..."

cd "$GH_PAGES"
git add "$TARGET_REL"
# Stage uploads dir if anything was copied
if compgen -G "$UPLOAD_SUBDIR/*" > /dev/null; then
  git add "$UPLOAD_SUBDIR/"
fi

# Show diff
echo
info "Files staged for commit:"
git diff --cached --stat
echo
info "First 30 lines of the post diff:"
git diff --cached -- "$TARGET_REL" | head -30
echo

if $DRY_RUN; then
  warn "DRY RUN: nothing committed, nothing pushed. Re-run with --yes to commit + push."
  exit 0
fi

# Commit
COMMIT_MSG="post: $(basename "$TARGET_REL" .md) — pillar blog"
if ! $YES_FLAG; then
  read -p "Commit with message '$COMMIT_MSG'? [y/N] " -n 1 -r
  echo
  [[ $REPLY =~ ^[Yy]$ ]] || { warn "Committed nothing."; exit 0; }
fi

git commit -m "$COMMIT_MSG"
ok "Committed."

# Push
if $YES_FLAG; then
  info "Pushing to remote..."
  git push
  ok "Pushed. GitHub Pages will rebuild in ~30s. Post will be live at ${GH_URL}/${SLUG}/"
else
  warn "Not pushing (no --yes). Run: cd $GH_PAGES && git push"
fi
