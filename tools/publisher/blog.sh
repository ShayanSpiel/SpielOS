#!/usr/bin/env bash
# tools/publisher/blog.sh — vault blog post → GitHub Pages
#
# Publishes a blog post from the vault (content/ready/*.md) to a
# GitHub Pages Jekyll site (_posts/*.md), with referenced screenshots
# copied to assets/uploads/ and frontmatter transformed to Jekyll format.
# Then git add + commit + (optional) push.
#
# Usage:
#   bash tools/publisher/blog.sh <blog-file>
#   bash tools/publisher/blog.sh <blog-file> --dry-run
#   bash tools/publisher/blog.sh <blog-file> --yes
#   bash tools/publisher/blog.sh --list
#
# Flags:
#   --list      List all blog posts in content/ready/ that are
#               eligible to publish (status: ready)
#   --dry-run   Do everything except git push. Show the diff and ask.
#   --yes       Skip the "are you sure?" prompt; push automatically.
#   --force     Publish even if status != ready. USE WITH CARE.
#   --no-build  Skip the local `bundle exec jekyll build` step.
#
# Requirements:
#   - bash 4+, python3, git
#   - The vault is at $VAULT (from .env or env var)
#   - The GH Pages repo is at $GH_PAGES (from env var, default: ~/github/<BLOG_REPO>)
#   - The GH Pages repo is initialized as a git repo with a remote
#
# Behavior:
#   - Re-runnable (idempotent): if the target file already exists, asks
#     before overwriting
#   - Status must be `ready` (or --force)
#   - Image references in the post body that point into the vault's
#     assets/screenshots/ are copied to GH Pages
#     assets/uploads/YYYY-MM-DD-slug/ and rewritten as relative paths
#   - Other local image references are LEFT ALONE (likely broken on
#     the live site, but flagged for the user to review)
#   - Git commit is always created; git push only with --yes
#
set -euo pipefail

# ─── Config ────────────────────────────────────────────────────────────────
# Load .env if present (for VAULT_DIR, BLOG_REPO, BLOG_TOKEN)
ENV_FILE="$(dirname "$0")/../../.env"
[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
# VAULT from env var or default to cwd
VAULT="${VAULT:-${VAULT_DIR:-$PWD}}"
# GH_PAGES from env var or default to ~/github/<BLOG_REPO>
BLOG_REPO="${BLOG_REPO:-yourname/yourname.github.io}"
GH_PAGES="${GH_PAGES:-$HOME/github/$(basename "$BLOG_REPO" .git)}"
BLOG_OWNER="${BLOG_OWNER:-$(echo "$BLOG_REPO" | cut -d/ -f1)}"
READY_DIR="$VAULT/content/ready"
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
[[ -d "$READY_DIR" ]]  || die "Queue dir not found: $READY_DIR"
[[ -d "$POSTS_DIR" ]]  || die "Jekyll _posts dir not found: $POSTS_DIR"

command -v python3 >/dev/null || die "python3 not found in PATH"
command -v git >/dev/null      || die "git not found in PATH"

# ─── List mode ─────────────────────────────────────────────────────────────
if $LIST_MODE; then
  echo "Pillar blog posts in $READY_DIR with status: ready"
  hr
  count=0
  for f in "$READY_DIR"/*-pillar-blog.md; do
    [[ -f "$f" ]] || continue
    status=$(python3 -c '
import re, sys
with open(sys.argv[1]) as fh: c = fh.read()
m = re.search(r"^status:\s*(.+)$", c, re.M)
print(m.group(1).strip() if m else "unknown")
' "$f")
    title=$(python3 -c '
import re, sys
with open(sys.argv[1]) as fh: c = fh.read()
m = re.search(r"^title:\s*(.+)$", c, re.M)
print(m.group(1).strip() if m else "untitled")
' "$f")
    standalone=""
    if [[ "$status" == "ready" ]]; then
      printf "${GREEN}✓${NC} %-40s | %s\n  status=%s\n" "$(basename "$f")" "$title" "$status"
      count=$((count+1))
    else
      printf "${YELLOW}–${NC} %-40s | %s\n  status=%s\n" "$(basename "$f")" "$title" "$status"
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

_SOURCE_PATH="$SOURCE"
info "Source: $_SOURCE_PATH"
info "Vault: $VAULT"
info "GH Pages: $GH_PAGES"
hr

# ─── Extract frontmatter fields ────────────────────────────────────────────
# Inline Python helper reads YAML frontmatter and emits shell-safe
# `export KEY=value` lines on stdout. We source those into the current
# shell to set TITLE, STATUS, etc.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FM_FILE="$(mktemp -t publish-blog-fm.XXXXXX)"
trap 'rm -f "$FM_FILE"' EXIT

python3 - "$_SOURCE_PATH" > "$FM_FILE" <<'PYEOF' || die "Failed to parse frontmatter from $_SOURCE_PATH"
import re, sys
text = open(sys.argv[1]).read()
m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
if not m:
    sys.exit(1)
for line in m.group(1).splitlines():
    if ":" not in line:
        continue
    k, _, v = line.partition(":")
    k = k.strip()
    v = v.strip().strip('"').strip("'")
    # shell-safe: escape single quotes
    v_safe = v.replace("'", "'\\''")
    print(f"export {k}='{v_safe}'")
PYEOF

[[ ! -s "$FM_FILE" ]] && die "No frontmatter found in $_SOURCE_PATH"

# shellcheck source=/dev/null
source "$FM_FILE"
SOURCE="$_SOURCE_PATH"   # restore after frontmatter may have overwritten it

[[ -z "${TITLE:-}" ]]  && die "Missing 'title' in frontmatter"
[[ -z "${STATUS:-}" ]] && die "Missing 'status' in frontmatter"

# ─── Gates ─────────────────────────────────────────────────────────────────
if [[ "$STATUS" != "ready" ]] && ! $FORCE_FLAG; then
  die "Status is '$STATUS', not 'ready'. Set status: ready in the frontmatter, or use --force."
fi
if [[ "${gates_verdict:-}" != "pass" ]] && ! $FORCE_FLAG; then
  die "gates_verdict is '${gates_verdict:-missing}', not 'pass'. Run tools/editor.py stamp before publishing, or use --force."
fi

ok "Gates passed: status=$STATUS gates_verdict=${gates_verdict:-force}"

# ─── Compute target ────────────────────────────────────────────────────────
# Extract YYYY-MM-DD from source filename (the first 10 chars of basename)
BASE=$(basename "$SOURCE")
DATE_PREFIX="${BASE:0:10}"
[[ "$DATE_PREFIX" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "Source filename must start with YYYY-MM-DD-: $BASE"

# Slugify title: lowercase, replace non-alphanumeric with hyphens, collapse
# Title is passed via env var to avoid command injection via frontmatter.
SLUG=$(TITLE="$TITLE" python3 -c '
import os, re
t = os.environ["TITLE"].lower()
t = re.sub(r"[^a-z0-9]+", "-", t)
t = t.strip("-")
print(t[:80] or "untitled")
')

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
MANIFEST_FILE="$(mktemp -t publish-blog-manifest.XXXXXX)"
trap 'rm -f "$FM_FILE" "$MANIFEST_FILE"' EXIT
python3 - "$SOURCE" "$TARGET" "$UPLOAD_SUBDIR" "$SCREENSHOTS_DIR" "$DATE_PREFIX" "$SLUG" "$MANIFEST_FILE" "$VAULT" <<'PYEOF'
import re, sys, os, shutil, pathlib

source, target, upload_subdir, screenshots_dir, date_prefix, slug, manifest_file, vault_root = sys.argv[1:9]
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

# Track files we copy to GH Pages (uploaded screenshots, banners, icons).
# These are written to manifest_file at the end so the bash side can git-add them.
copied_files = []
flagged_paths = set()

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

# Banner/image: map vault "banner:" field to Jekyll "image: path:" frontmatter
# If the banner is a vault asset, copy it to GH Pages (preserving path).
banner = fm.get('banner', '')
if banner:
    banner_norm = banner.lstrip('/')
    if banner_norm.startswith(('assets/banners/', 'assets/icons/')):
        banner_src = os.path.realpath(os.path.join(vault_root, banner_norm))
        banners_root = os.path.realpath(os.path.join(vault_root, 'assets', 'banners'))
        icons_root = os.path.realpath(os.path.join(vault_root, 'assets', 'icons'))
        # Containment: reject any path that escapes assets/banners/ or assets/icons/
        # (prevents ../../.env traversal via a crafted banner: field).
        contained = (banner_src.startswith(banners_root + os.sep) or
                     banner_src == banners_root or
                     banner_src.startswith(icons_root + os.sep) or
                     banner_src == icons_root)
        if contained and os.path.isfile(banner_src):
            banner_dst = os.path.join(gh_pages_root, banner_norm)
            os.makedirs(os.path.dirname(banner_dst), exist_ok=True)
            shutil.copy2(banner_src, banner_dst)
            copied_files.append((banner_src, banner_dst, '/' + banner_norm))
    # Make banner path absolute for Jekyll
    if banner.startswith('assets/'):
        banner_path = '/' + banner
    else:
        banner_path = banner if banner.startswith('/') else '/' + banner
    jekyll_fm_lines.extend([
        'image:',
        f'  path: {banner_path}',
        '  width: 1200',
        '  height: 630',
    ])

# Find image references in body
# Patterns: ![alt](path), <img src="path">, src="path"
img_patterns = [
    re.compile(r'!\[([^\]]*)\]\(([^)]+)\)'),
    re.compile(r'<img\s+[^>]*src="([^"]+)"', re.IGNORECASE),
    re.compile(r'src="([^"]+)"'),
]

def process_path(path):
    # Skip external URLs and data URIs
    if path.startswith(('http://', 'https://', 'data:')):
        return path

    # Vault asset paths (banners, icons): if the file exists in the vault, copy
    # it to GH Pages at the same relative path. Otherwise fall through.
    norm = path.lstrip('/')
    if norm.startswith(('assets/banners/', 'assets/icons/')):
        src_abs = os.path.join(vault_root, norm)
        if os.path.isfile(src_abs):
            dst = os.path.join(gh_pages_root, norm)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src_abs, dst)
            copied_files.append((src_abs, dst, '/' + norm))
            return path  # Keep original form (absolute or relative)

    # Other absolute paths and Jekyll-relative paths — assume already on GH Pages
    # (e.g. /logo.png, /og-default.png, or assets/... committed in a prior publish)
    if path.startswith(('/', 'assets/')):
        return path

    # Try to resolve relative to source, vault root, or fall back to absolute
    if os.path.isabs(path):
        src_abs = path
    else:
        # Try relative to source file first
        src_abs = os.path.join(os.path.dirname(source), path)
        if not os.path.isfile(src_abs):
            # Try relative to vault root
            src_abs = os.path.normpath(os.path.join(vault_root, path))
            if not os.path.isfile(src_abs):
                # Try absolute interpretation from vault
                src_abs = os.path.join(os.path.dirname(source), '..', '..', path)
                src_abs = os.path.normpath(src_abs)

    if os.path.isfile(src_abs):
        # Copy to upload subdir (per-post screenshots)
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
    # Skip leading blank lines (empty lines or whitespace-only)
    idx = 0
    while idx < len(lines) and lines[idx].strip() == '':
        idx += 1
    if idx == len(lines):
        return body_text
    if not lines[idx].lstrip().startswith('# '):
        return body_text
    h1_text = lines[idx].lstrip()[2:].strip()
    def norm(s):
        return re.sub(r'[^a-z0-9]+', '', s.lower())
    if norm(h1_text) == norm(fm_title):
        del lines[idx]
        if idx < len(lines) and lines[idx].strip() == '':
            del lines[idx]
    return '\n'.join(lines)

new_body = strip_leading_h1(new_body, title)

# ─── Strip common fluff headings ──────────────────────────────────────────
# LLM-drafted blog posts often start with "## Intro" or "## Introduction"
# which reads redundantly after the post title. Strip the first H2 if it's
# one of the known fluff section anchors.
_fluff = ('intro', 'introduction', 'overview', 'background', 'context')
for _i in range(3):
    _lines = new_body.split('\n')
    _idx = 0
    while _idx < len(_lines) and _lines[_idx].strip() == '':
        _idx += 1
    if _idx < len(_lines) and _lines[_idx].lstrip().startswith('## '):
        _label = _lines[_idx].lstrip()[3:].strip().lower().rstrip(':')
        if _label in _fluff:
            del _lines[_idx]
            if _idx < len(_lines) and _lines[_idx].strip() == '':
                del _lines[_idx]
            new_body = '\n'.join(_lines)
            continue
    break

# ─── Insert banner image after frontmatter ────────────────────────────────
# If a banner was set in frontmatter (copied to GH Pages above), render it
# as a Markdown image right after the frontmatter separator, so it displays
# in the blog post body (not just as an OG meta tag).
banner_insert = ''
if banner:
    banner_alt = title or 'Banner'
    # Use the same Jekyll-relative path that was written to the OG meta
    banner_insert = f'\n![{banner_alt}]({banner_path})\n'

# Write target
jekyll_fm = '\n'.join(jekyll_fm_lines) + '\n'
with open(target, 'w') as f:
    f.write(jekyll_fm + '---' + banner_insert + '\n' + new_body)

# Print report
print(f"WROTE: {target}")
print(f"COPIED: {len(copied_files)} image(s) to {upload_subdir}")
for src, dst, rel in copied_files:
    print(f"  - {os.path.basename(src)} → {rel}")
if flagged_paths:
    print(f"FLAGGED: {len(flagged_paths)} image(s) not found in vault (left as-is, will be broken on live site unless fixed manually):")
    for p in flagged_paths:
        print(f"  - {p}")

# Write manifest of files copied to GH Pages (relative to repo root).
# The bash side reads this and `git add`s each one.
with open(manifest_file, 'w') as mf:
    for src, dst, rel in copied_files:
        repo_rel = os.path.relpath(dst, gh_pages_root)
        mf.write(repo_rel + '\n')
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
# Stage any files the Python script copied (uploads, banners, icons, etc.)
if [[ -s "$MANIFEST_FILE" ]]; then
  while IFS= read -r staged_file; do
    [[ -n "$staged_file" ]] && git add "$staged_file"
  done < "$MANIFEST_FILE"
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
COMMIT_MSG="post: $(basename "$TARGET_REL" .md) - pillar blog"
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
  ok "Pushed. GitHub Pages will rebuild in ~30s. Post will be live at https://${BLOG_OWNER}.github.io/${SLUG}/"
else
  warn "Not pushing (no --yes). Run: cd $GH_PAGES && git push"
fi
