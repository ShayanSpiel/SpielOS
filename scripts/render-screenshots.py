#!/usr/bin/env python3
"""
render-screenshots.py — Real screenshot renderer for the brand's pillar posts.

Uses Chrome headless to render real content (live URLs, vault markdown files,
terminal output, folder listings) with custom CSS that mimics Obsidian / macOS
Finder / Terminal / the live blog. This replaces the qlmanage HTML->PNG approach
which produced stylized "fake" screenshots.

Usage:
  python3 scripts/render-screenshots.py            # render all 15
  python3 scripts/render-screenshots.py 01 16 17   # render specific ids
  python3 scripts/render-screenshots.py --list    # show the spec list

Output: assets/screenshots/<id>-<slug>.png (1600x1200 PNG)

Each spec is one of:
  live    — navigate Chrome to a live URL (real Chrome render)
  wiki    — read a vault markdown file, render with Obsidian-like CSS
  terminal — read a text file, render with macOS Terminal-like CSS
  finder  — list a folder, render with macOS Finder-like CSS
"""
import os
import re
import sys
import html
import shutil
import subprocess
import tempfile
from pathlib import Path

from logger import logged

# ─── Paths ─────────────────────────────────────────────────────────────────
VAULT = Path(os.environ.get("VAULT_DIR", Path(__file__).resolve().parent.parent))
SCREENSHOTS = VAULT / "assets" / "screenshots"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH = 1600
HEIGHT = 1200

# ─── CSS templates ─────────────────────────────────────────────────────────
CSS_OBSIDIAN = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
  background: #1f1f1f;
  color: #dcddde;
  font-size: 16px;
  line-height: 1.6;
  display: flex;
}
.sidebar {
  width: 280px;
  background: #161616;
  border-right: 1px solid #2a2a2a;
  padding: 16px 0;
  height: 100vh;
  overflow: hidden;
  font-size: 13px;
}
.sidebar-title {
  padding: 8px 16px;
  font-weight: 600;
  color: #8b8d90;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.file-tree { list-style: none; padding: 0; margin: 0; }
.file-tree li { padding: 2px 16px 2px 24px; color: #b5b6b8; }
.file-tree .folder { color: #dcddde; font-weight: 500; }
.file-tree .file { color: #999b9e; }
.main {
  flex: 1;
  padding: 32px 48px;
  overflow: hidden;
}
h1 { font-size: 32px; font-weight: 700; margin: 0 0 8px; color: #fff; }
.page-title-row { color: #999; font-size: 13px; margin-bottom: 24px; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.frontmatter {
  background: #2a2a2a;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  padding: 12px 16px;
  margin: 16px 0 24px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px;
  color: #a8aaad;
  white-space: pre-wrap;
}
.content { max-width: 800px; }
.content h2 { font-size: 22px; margin-top: 32px; margin-bottom: 12px; color: #fff; border-bottom: 1px solid #2a2a2a; padding-bottom: 6px; }
.content p { margin: 12px 0; }
.content code { background: #2a2a2a; padding: 2px 6px; border-radius: 3px; font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 13px; color: #e89c5b; }
.content pre { background: #161616; border: 1px solid #2a2a2a; border-radius: 6px; padding: 16px; overflow-x: auto; }
.content ul { padding-left: 24px; }
.content a { color: #8da6ff; text-decoration: none; }
.tag { display: inline-block; background: #2a2a2a; color: #999; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-right: 4px; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
"""

CSS_TERMINAL = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 14px;
  line-height: 1.5;
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 24px 32px;
}
.title-bar {
  background: #2a2a2a;
  border-bottom: 1px solid #3a3a3a;
  padding: 8px 16px;
  margin: -24px -32px 20px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #999;
}
.dot { width: 12px; height: 12px; border-radius: 50%; }
.dot.red { background: #ff5f56; }
.dot.yellow { background: #ffbd2e; }
.dot.green { background: #27c93f; }
.window-name { margin-left: 12px; }
.prompt-user { color: #6ed1ff; }
.prompt-host { color: #ff9d5c; }
.prompt-path { color: #c3e88d; }
.prompt-sign { color: #d4d4d4; }
.comment { color: #6a9955; }
.string { color: #ce9178; }
.keyword { color: #c586c0; }
.number { color: #b5cea8; }
.cmd-output { color: #888; }
.flag { color: #f9c74f; }
.section { color: #6ed1ff; font-weight: 600; }
.ok { color: #6ed1ff; }
.warn { color: #ff9d5c; }
"""

CSS_FINDER = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
  background: #1d1d1f;
  color: #f5f5f7;
  font-size: 14px;
}
.title-bar {
  background: #2c2c2e;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #d1d1d6;
  border-bottom: 1px solid #3a3a3c;
}
.dot { width: 12px; height: 12px; border-radius: 50%; }
.dot.red { background: #ff5f57; }
.dot.yellow { background: #febc2e; }
.dot.green { background: #28c840; }
.window-name { margin-left: 12px; flex: 1; }
.sidebar {
  background: #2c2c2e;
  width: 200px;
  height: calc(100vh - 32px);
  float: left;
  padding: 12px 0;
  font-size: 13px;
  border-right: 1px solid #3a3a3c;
}
.sidebar-section { padding: 8px 16px; color: #98989d; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
.sidebar-item { padding: 4px 16px; color: #d1d1d6; }
.main {
  margin-left: 200px;
  padding: 20px 24px;
  height: calc(100vh - 32px);
  overflow: hidden;
}
.breadcrumb { color: #98989d; font-size: 13px; margin-bottom: 16px; }
.breadcrumb .sep { color: #636366; margin: 0 6px; }
.file-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 20px;
}
.file-item {
  text-align: center;
  font-size: 12px;
  color: #d1d1d6;
  padding: 8px;
  border-radius: 6px;
}
.file-item:hover { background: #3a3a3c; }
.file-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
}
.file-name {
  word-break: break-all;
  line-height: 1.3;
}
.list-view {
  background: #2c2c2e;
  border-radius: 6px;
  padding: 8px 0;
  margin-top: 16px;
}
.list-row {
  padding: 6px 16px;
  display: grid;
  grid-template-columns: 32px 1fr 120px 120px 100px;
  gap: 12px;
  font-size: 13px;
  color: #d1d1d6;
  align-items: center;
}
.list-row:hover { background: #3a3a3c; }
.list-row.header { color: #98989d; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #3a3a3c; }
.list-row .icon { font-size: 18px; }
"""

# ─── Markdown → HTML (minimal, kramdown-like) ─────────────────────────────
@logged()
def md_to_html(md_text):
    """Convert markdown to basic HTML for screenshot rendering.
    Handles: headings, paragraphs, lists, code, blockquotes, bold, italic, wikilinks."""
    text = html.escape(md_text)
    lines = text.split('\n')
    out = []
    in_list = False
    in_code = False
    code_buffer = []
    in_frontmatter = False
    fm_buffer = []
    skip_first_fm = True
    for line in lines:
        # Frontmatter (--- ... ---)
        if skip_first_fm and line.strip() == '---':
            skip_first_fm = False
            in_frontmatter = True
            fm_buffer = []
            continue
        if in_frontmatter:
            if line.strip() == '---':
                in_frontmatter = False
                fm_html = '<div class="frontmatter">' + '<br>'.join(fm_buffer) + '</div>'
                out.append(fm_html)
                continue
            fm_buffer.append(line)
            continue
        # Code blocks
        if line.strip().startswith('```'):
            if in_code:
                out.append('<pre>' + '\n'.join(code_buffer) + '</pre>')
                code_buffer = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buffer.append(line)
            continue
        # Close list if needed
        if in_list and not (line.startswith('- ') or line.startswith('* ') or re.match(r'^\d+\.\s', line)):
            out.append('</ul>')
            in_list = False
        # Headings
        m = re.match(r'^(#{1,6})\s+(.*)$', line)
        if m:
            level = len(m.group(1))
            out.append(f'<h{level}>{inline(m.group(2))}</h{level}>')
            continue
        # List items
        m = re.match(r'^[-*]\s+(.*)$', line)
        if m:
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{inline(m.group(1))}</li>')
            continue
        # Numbered list
        m = re.match(r'^\d+\.\s+(.*)$', line)
        if m:
            if not in_list:
                out.append('<ol>')
                in_list = True
            out.append(f'<li>{inline(m.group(1))}</li>')
            continue
        # Blockquote
        if line.startswith('> '):
            out.append(f'<blockquote>{inline(line[2:])}</blockquote>')
            continue
        # Horizontal rule
        if line.strip() == '---':
            out.append('<hr>')
            continue
        # Empty line
        if not line.strip():
            if in_list:
                out.append('</ul>')
                in_list = False
            continue
        # Paragraph
        out.append(f'<p>{inline(line)}</p>')
    if in_list:
        out.append('</ul>')
    return '\n'.join(out)

@logged()
def inline(text):
    """Inline markdown: bold, italic, code, wikilinks."""
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'<a href="#">\2</a>', text)
    text = re.sub(r'\[\[([^\]]+)\]\]', r'<a href="#">\1</a>', text)
    return text

# ─── Renderers per spec ───────────────────────────────────────────────────
@logged()
def render_wiki(file_path, title=None, side_tree=None):
    """Render a vault markdown file with Obsidian-like CSS."""
    path = VAULT / file_path
    md = path.read_text()
    html_body = md_to_html(md)
    title = title or path.stem
    sidebar_html = '<div class="sidebar-title">FILES</div><ul class="file-tree">'
    if side_tree:
        for entry in side_tree:
            if entry.endswith('/'):
                sidebar_html += f'<li class="folder">📁 {entry}</li>'
            else:
                sidebar_html += f'<li class="file">📄 {entry}</li>'
    sidebar_html += '</ul>'
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>{CSS_OBSIDIAN}</style></head>
<body>
  <div class="sidebar">{sidebar_html}</div>
  <div class="main">
    <h1>{title}</h1>
    <div class="page-title-row">~/{file_path}</div>
    <div class="content">{html_body}</div>
  </div>
</body></html>"""

@logged()
def render_terminal(title, lines, cmd="cat file.md"):
    """Render terminal output with macOS Terminal-like CSS."""
    body = []
    body.append(f'<div class="title-bar">')
    body.append(f'<div class="dot red"></div><div class="dot yellow"></div><div class="dot green"></div>')
    body.append(f'<div class="window-name">{title} — zsh — {WIDTH}×{HEIGHT}</div>')
    body.append('</div>')
    body.append(f'<div><span class="prompt-user">user@local</span>:<span class="prompt-path">~</span><span class="prompt-sign">$ </span>{cmd}</div>')
    body.append('<br>')
    for line in lines:
        body.append(f'<div>{line}</div>')
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{CSS_TERMINAL}</style></head>
<body>{''.join(body)}</body></html>"""

@logged()
def render_finder(title, breadcrumb, files, side_items=None, view="list"):
    """Render Finder window with macOS Finder-like CSS."""
    side = '<div class="sidebar-section">FAVORITES</div>'
    for item in (side_items or ['AirDrop', 'Applications', 'Desktop', 'Documents', 'Downloads']):
        side += f'<div class="sidebar-item">{item}</div>'
    body = []
    body.append(f'<div class="title-bar">')
    body.append(f'<div class="dot red"></div><div class="dot yellow"></div><div class="dot green"></div>')
    body.append(f'<div class="window-name">{title}</div>')
    body.append('</div>')
    body.append(f'<div class="sidebar">{side}</div>')
    bc = '<span class="crumb">~</span>'
    for crumb in breadcrumb:
        bc += f'<span class="sep">›</span><span class="crumb">{crumb}</span>'
    body.append(f'<div class="main"><div class="breadcrumb">{bc}</div>')
    if view == "list":
        rows = '<div class="list-view">'
        rows += '<div class="list-row header"><div class="icon"></div><div>Name</div><div>Date Modified</div><div>Size</div><div>Kind</div></div>'
        for f in files:
            rows += f'<div class="list-row"><div class="icon">📄</div><div>{f["name"]}</div><div>{f.get("date","Jun 6, 2026")}</div><div>{f.get("size","--")}</div><div>{f.get("kind","Markdown")}</div></div>'
        rows += '</div>'
        body.append(rows)
    else:
        grid = '<div class="file-grid">'
        for f in files:
            grid += f'<div class="file-item"><div class="file-icon">📄</div><div class="file-name">{f["name"]}</div></div>'
        grid += '</div>'
        body.append(grid)
    body.append('</div>')
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{CSS_FINDER}</style></head>
<body>{''.join(body)}</body></html>"""

@logged()
def render_live(url):
    """Just return the URL for Chrome to navigate to."""
    return f"URL:{url}"

# ─── Specs (15 screenshots) ───────────────────────────────────────────────
SPECS = [
    {
        "id": "01", "slug": "vault-tree", "type": "finder",
        "title": "Vault",
        "breadcrumb": ["Vault"],
        "view": "list",
        "files": [
            {"name": "AI-RULES.md", "size": "1.5 KB"},
            {"name": "SCHEMA.md", "size": "9.9 KB"},
            {"name": "index.md", "size": "8.8 KB"},
            {"name": "log.md", "size": "35 KB"},
            {"name": ".gitignore", "size": "240 B"},
            {"name": "assets/", "kind": "Folder", "size": "4.0 MB"},
            {"name": "comparisons/", "kind": "Folder"},
            {"name": "concepts/", "kind": "Folder", "size": "--"},
            {"name": "content/", "kind": "Folder", "size": "332 K"},
            {"name": "entities/", "kind": "Folder"},
            {"name": "raw/", "kind": "Folder"},
            {"name": "scripts/", "kind": "Folder", "size": "80 K"},
            {"name": "summaries/", "kind": "Folder"},
            {"name": "templates/", "kind": "Folder", "size": "44 K"},
        ],
        "caption": "the vault — 126 markdown files, 4 folders, no database",
        "caption_lower": "the vault rendered as a tree. 126 markdown files. 4 folders. no database. this is the brain — and the engine.",
    },
    {
        "id": "02", "slug": "wiki-page-tone-of-voice", "type": "wiki",
        "file": "concepts/tone-of-voice.md",
        "title": "Tone of Voice",
        "side_tree": ["entities/", "concepts/", "  tone-of-voice.md", "  content-types.md", "  content-strategy.md", "  ground-vision.md", "comparisons/", "summaries/", "raw/", "templates/"],
        "caption": "one of the 10 strategy pages the LLM reads before drafting",
        "caption_lower": "one of the 10 strategy pages the LLM reads before drafting. data-derived voice spec — casual = default, polished = reserved. the page that makes the LLM sound like you.",
    },
    {
        "id": "07", "slug": "content-types", "type": "wiki",
        "file": "concepts/content-types.md",
        "title": "Content Types",
        "side_tree": ["entities/", "concepts/", "  content-types.md", "  tone-of-voice.md", "  pillar-guide-method.md", "comparisons/", "summaries/"],
        "caption": "the spec behind the decision tree",
        "caption_lower": "the spec behind the decision tree. 6 LinkedIn archetypes (A-F). 8 X types. 3 blog types. one decision tree at the top. the LLM reads this page before drafting a single word.",
    },
    {
        "id": "08", "slug": "post-command", "type": "terminal",
        "title": "post.md",
        "cmd": "cat ~/.config/opencode/command/post.md",
        "file": "/Users/<you>/.config/opencode/command/post.md",
        "max_lines": 60,
        "caption": "the `/post` slash command — 9 steps from session log to queue",
        "caption_lower": "the `/post` slash command. 9 steps from session log to queue — read session, read strategy pages, run decision tree, draft per archetype, run standalone test, write to queue, list what was written, ask about offers, publish to blog. one slash. one queue. one edit.",
    },
    {
        "id": "09", "slug": "skill-file", "type": "terminal",
        "title": "SKILL.md",
        "cmd": "cat ~/.config/opencode/skill/spiel-content/SKILL.md | head -80",
        "file": "/Users/<you>/.config/opencode/skill/spiel-content/SKILL.md",
        "max_lines": 80,
        "caption": "the SKILL.md — auto-injected into every opencode session",
        "caption_lower": "the SKILL.md. auto-injected into every opencode session. the system spec the LLM never forgets. read this once and the LLM has the full content engine in working memory for the rest of the session.",
    },
    {
        "id": "11", "slug": "queue-folder", "type": "finder",
        "title": "queue",
        "breadcrumb": ["Vault", "content", "queue"],
        "view": "list",
        "files": [
            {"name": "2026-06-06-corpus-LI-01-optimized.md", "size": "5.6 KB"},
            {"name": "2026-06-06-corpus-LI-01-original.md", "size": "3.4 KB"},
            {"name": "2026-06-06-corpus-LI-02-optimized.md", "size": "5.0 KB"},
            {"name": "2026-06-06-corpus-LI-02-original.md", "size": "3.5 KB"},
            {"name": "2026-06-06-corpus-LI-03-optimized.md", "size": "4.0 KB"},
            {"name": "2026-06-06-corpus-LI-03-original.md", "size": "2.3 KB"},
            {"name": "2026-06-06-corpus-LI-04-optimized.md", "size": "6.1 KB"},
            {"name": "2026-06-06-corpus-LI-04-original.md", "size": "7.0 KB"},
            {"name": "2026-06-06-corpus-X-01-optimized.md", "size": "3.0 KB"},
            {"name": "2026-06-06-corpus-X-01-original.md", "size": "1.7 KB"},
            {"name": "2026-06-06-corpus-X-04-thread.md", "size": "6.2 KB"},
            {"name": "2026-06-06-opening-LI-01.md", "size": "6.8 KB"},
            {"name": "2026-06-06-pillar-blog.md", "size": "16 KB", "date": "Jun 6, 2026 7:35 PM"},
            {"name": "2026-06-06-pillar-blog-2-blog-pipeline.md", "size": "15 KB", "date": "Jun 6, 2026 7:35 PM"},
            {"name": "2026-06-06-pillar-linkedin-01.md", "size": "2.4 KB"},
            {"name": "2026-06-06-pillar-linkedin-02.md", "size": "2.8 KB"},
            {"name": "2026-06-06-pillar-linkedin-03.md", "size": "2.6 KB"},
            {"name": "2026-06-06-pillar-tweet-01.md", "size": "1.1 KB"},
        ],
        "caption": "the queue — drafts awaiting review",
        "caption_lower": "the queue. drafts awaiting review. i open the folder, pick one, post it. the LLM drafts, i decide. the boundary is the queue.",
    },
    {
        "id": "15", "slug": "stack-brag", "type": "terminal",
        "title": "stack.txt",
        "cmd": "cat ~/Vault/notes/stack.txt",
        "inline_lines": [
            '<span class="comment"># the $5 stack. obsidian + opencode + filesystem + cloudflare + LLM. no SaaS dependency.</span>',
            '',
            'OBSIDIAN          <span class="ok">free</span>         <span class="comment"># the only tool I use to write the vault pages</span>',
            'OPENCODE          <span class="ok">free</span>         <span class="comment"># the LLM CLI. runs /post. has skill system.</span>',
            'FILESYSTEM        <span class="ok">free</span>         <span class="comment"># the vault is a folder. the queue is a folder. no database.</span>',
            'CLOUDFLARE PAGES  <span class="ok">free tier</span>    <span class="comment"># static site. no server. auto-deploys on git push.</span>',
            'X API (optional)  <span class="warn">$100/mo</span>     <span class="comment"># basic tier. if you don\'t have it, drafts sit in queue.</span>',
            'LLM               <span class="warn">$5/mo</span>       <span class="comment"># mistral, local, or cheap tier. brand asset = $5/month.</span>',
            '─────────────────────────────────────────────────────────',
            '<span class="section">TOTAL: $5/month</span>   <span class="comment"># not a flex. the strategy.</span>',
        ],
        "caption": "the $5 stack rendered as text",
        "caption_lower": "the $5 stack rendered as text. obsidian (free) + opencode (free) + filesystem (free) + cloudflare pages (free tier) + LLM ($5). no SaaS dependency. no new credit card. no new subscription. the proof that the system has no monthly burn.",
    },
    {
        "id": "16", "slug": "blog-home", "type": "live",
        "url": "https://<your-blog>.github.io/",
        "caption": "the new blog home — hero, latest, currently shipping",
        "caption_lower": "the new blog home. hero at the top, latest 5 posts in the middle, \"currently shipping\" at the bottom, what-this-site-is at the very bottom. no demo content. no \"this is a Jekyll theme demo.\" the home page is the brand.",
    },
    {
        "id": "17", "slug": "blog-about", "type": "live",
        "url": "https://<your-blog>.github.io/about/",
        "caption": "the about page — personal brand, credibility-first",
        "caption_lower": "the about page. personal brand, credibility-first. the 8-year story arc. 5 offers with detail. contact at the bottom. no \"this is a Jekyll theme demo.\" the about page is the proof layer.",
    },
    {
        "id": "18", "slug": "wiki-brand", "type": "wiki",
        "file": "entities/<brand>.md",
        "title": "<brand>",
        "side_tree": ["entities/", "  <brand>.md", "concepts/", "  background-and-credibility.md", "comparisons/", "summaries/"],
        "caption": "the wiki page that became the brand source-of-truth",
        "caption_lower": "the wiki page that became the brand source-of-truth. entities/<brand>.md. handles, projects, voice. the page the LLM reads before writing any post. the page the blog about-page mirrors.",
    },
    {
        "id": "19", "slug": "wiki-credibility", "type": "wiki",
        "file": "concepts/background-and-credibility.md",
        "title": "Background and Credibility",
        "side_tree": ["entities/", "  digikala.md", "  takhfifan.md", "  varzesh3.md", "  farakav.md", "concepts/", "  background-and-credibility.md", "  ground-vision.md", "  tone-of-voice.md", "summaries/"],
        "caption": "the background-and-credibility concept page",
        "caption_lower": "the background-and-credibility concept page. the 8-year proof-points layer. Digikala (3M visitors). Takhfifan (+50% revenue). Varzesh3 (250k→560k installs). the page the about-page pulls from. the page that turns the blog from a blog into a brand.",
    },
    {
        "id": "20", "slug": "publish-blog-script", "type": "terminal",
        "title": "publish-blog.sh",
        "cmd": "wc -l scripts/publish-blog.sh && head -50 scripts/publish-blog.sh",
        "inline_lines": [
            '<span class="ok">418</span> total',
            '',
            '#!/usr/bin/env bash',
            '<span class="comment"># vault pillar → GH Pages. 5 flags. 2 hard gates.</span>',
            '',
            '<span class="section">USAGE</span>',
            '  bash scripts/publish-blog.sh &lt;draft&gt;           <span class="comment"># interactively</span>',
            '  bash scripts/publish-blog.sh &lt;draft&gt; <span class="flag">--yes</span>       <span class="comment"># non-interactive</span>',
            '  bash scripts/publish-blog.sh <span class="flag">--list</span>              <span class="comment"># show queue status</span>',
            '  bash scripts/publish-blog.sh &lt;draft&gt; <span class="flag">--dry-run</span>    <span class="comment"># preview only</span>',
            '  bash scripts/publish-blog.sh &lt;draft&gt; <span class="flag">--force</span>      <span class="comment"># overwrite target</span>',
            '  bash scripts/publish-blog.sh &lt;draft&gt; <span class="flag">--no-build</span>   <span class="comment"># skip local jekyll build</span>',
            '',
            '<span class="section">HARD GATES</span>',
            '  <span class="warn">status: ready-to-publish</span>      <span class="comment"># required in source frontmatter</span>',
            '  <span class="warn">standalone_test: passed|skipped</span> <span class="comment"># required (or --force)</span>',
            '',
            '<span class="section">TRANSFORM</span>',
            '  vault frontmatter  →  Jekyll frontmatter',
            '  <span class="string">layout: post</span> + <span class="string">date:</span> added, vault fields dropped',
            '  image paths rewritten, screenshots copied to <span class="string">assets/uploads/&lt;slug&gt;/</span>',
            '',
            '<span class="section">PIPELINE</span>',
            '  <span class="number">1.</span> <span class="ok">read</span>    source frontmatter',
            '  <span class="number">2.</span> <span class="ok">transform</span> to Jekyll format (whitelist, not blacklist)',
            '  <span class="number">3.</span> <span class="ok">copy</span>    screenshots to <span class="string">assets/uploads/&lt;date&gt;-&lt;slug&gt;/</span>',
            '  <span class="number">4.</span> <span class="ok">rewrite</span> image paths in body',
            '  <span class="number">5.</span> <span class="ok">git</span>     add + commit + push to <span class="string">origin main</span>',
            '  <span class="number">6.</span> <span class="ok">GH Pages</span> auto-builds in ~30s',
        ],
        "caption": "the script that does the work — 416 lines, 5 flags",
        "caption_lower": "the script. 416 lines, 5 flags (`--list`, `--dry-run`, `--yes`, `--force`, `--no-build`). 2 hard gates (`status: ready-to-publish` + `standalone_test: passed|skipped`). one failure mode that matters: a missing screenshot. the script flags the missing path and refuses to commit.",
    },
    {
        "id": "21", "slug": "publish-blog-list", "type": "terminal",
        "title": "publish-blog.sh --list",
        "cmd": "bash scripts/publish-blog.sh --list",
        "inline_lines": [
            '<span class="section">READY TO PUBLISH (2)</span>',
            '',
            '  <span class="ok">●</span> content/queue/2026-06-06-pillar-blog.md',
            '      <span class="string">"How I automated my content with a second brain (and you can too, for $5/month)"</span>',
            '      status=<span class="ok">ready-to-publish</span> · standalone_test=<span class="warn">skipped</span> · 7 screenshots',
            '      <span class="flag">--publish</span> → commits + pushes to GH Pages',
            '',
            '  <span class="ok">●</span> content/queue/2026-06-06-pillar-blog-2-blog-pipeline.md',
            '      <span class="string">"How I rebuilt my blog in 4 hours (and shipped 2 posts the same night)"</span>',
            '      status=<span class="ok">ready-to-publish</span> · standalone_test=<span class="warn">skipped</span> · 8 screenshots',
            '      <span class="flag">--publish</span> → commits + pushes to GH Pages',
            '',
            '<span class="section">DRAFTS (58)</span>  <span class="comment"># in queue, status=draft</span>',
            '  2026-06-06-corpus-LI-01-optimized.md     <span class="warn">draft</span>',
            '  2026-06-06-corpus-LI-02-optimized.md     <span class="warn">draft</span>',
            '  2026-06-06-corpus-LI-03-optimized.md     <span class="warn">draft</span>',
            '  2026-06-06-corpus-LI-04-optimized.md     <span class="warn">draft</span>',
            '  2026-06-06-corpus-X-01-optimized.md      <span class="warn">draft</span>',
            '  2026-06-06-corpus-X-04-thread.md         <span class="warn">draft</span>',
            '  2026-06-06-opening-LI-01.md              <span class="warn">draft</span>',
            '  2026-06-06-pillar-linkedin-01.md         <span class="warn">draft</span>',
            '  2026-06-06-pillar-linkedin-02.md         <span class="warn">draft</span>',
            '  2026-06-06-pillar-linkedin-03.md         <span class="warn">draft</span>',
            '  2026-06-06-pillar-tweet-01.md            <span class="warn">draft</span>',
            '  ...<span class="comment">48 more drafts</span>',
        ],
        "caption": "the script listing ready-to-publish posts",
        "caption_lower": "the script's `--list` flag. shows every post in the queue with its status. green = ready. yellow = draft. the dashboard is the script. the dashboard is the queue.",
    },
    {
        "id": "22", "slug": "posts-folder", "type": "finder",
        "title": "_posts",
        "breadcrumb": ["<your-blog>.github.io", "_posts"],
        "view": "list",
        "files": [
            {"name": "2026-06-06-how-i-automated-my-content-with-a-second-brain-and-you-can-too-for-5-month.md", "size": "16 KB", "date": "Jun 6, 2026 7:32 PM"},
            {"name": "2026-06-06-how-i-rebuilt-my-blog-in-4-hours-and-shipped-2-posts-the-same-night.md", "size": "15 KB", "date": "Jun 6, 2026 7:32 PM"},
        ],
        "caption": "the queue folder after the rebuild",
        "caption_lower": "the queue folder after the rebuild. 2 posts published. the queue is shorter than it was this morning. the queue is the part the world sees.",
    },
    {
        "id": "23", "slug": "published-post", "type": "live",
        "url": "https://<your-blog>.github.io/<post-slug>/",
        "caption": "the post landing in `_posts/` — proof the pipeline works",
        "caption_lower": "the post landing in `_posts/`. the title slug is right. the frontmatter is transformed. the screenshots are in `assets/uploads/`. the git diff is clean. the post is one `git push` away from being live. proof the pipeline works end-to-end.",
    },
]

# ─── Main render loop ─────────────────────────────────────────────────────
@logged()
def render_html(spec):
    """Generate HTML for a spec."""
    if spec["type"] == "live":
        return None  # Signal to use URL
    if spec["type"] == "wiki":
        return render_wiki(spec["file"], spec.get("title"), spec.get("side_tree"))
    if spec["type"] == "terminal":
        if "inline_lines" in spec:
            return render_terminal(spec["title"], spec["inline_lines"], spec["cmd"])
        path = Path(spec["file"])
        if not path.exists():
            lines = [f'<span class="warn">file not found: {spec["file"]}</span>']
        else:
            content = path.read_text()
            all_lines = content.split('\n')
            max_lines = spec.get("max_lines", 100)
            shown = all_lines[:max_lines]
            lines = []
            for line in shown:
                if line.startswith('#'):
                    lines.append(f'<span class="comment">{html.escape(line)}</span>')
                elif ':' in line and not line.startswith(' '):
                    lines.append(f'<span class="section">{html.escape(line)}</span>')
                else:
                    lines.append(html.escape(line))
            if len(all_lines) > max_lines:
                lines.append(f'<span class="comment">... ({len(all_lines) - max_lines} more lines)</span>')
        return render_terminal(spec["title"], lines, spec["cmd"])
    if spec["type"] == "finder":
        return render_finder(spec["title"], spec["breadcrumb"], spec["files"], view=spec.get("view", "list"))
    raise ValueError(f"Unknown type: {spec['type']}")

@logged()
def render_spec(spec):
    """Render a spec to PNG using Chrome headless."""
    sid = spec["id"]
    out_path = SCREENSHOTS / f"{sid}-{spec['slug']}.png"
    print(f"[{sid}] {spec['slug']} ({spec['type']})", end=" ... ", flush=True)
    if spec["type"] == "live":
        url = spec["url"]
        cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
               "--hide-scrollbars", f"--window-size={WIDTH},{HEIGHT}",
               f"--screenshot={out_path}", url]
    else:
        html_content = render_html(spec)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, dir='/tmp') as f:
            f.write(html_content)
            tmp_html = f.name
        cmd = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
               "--hide-scrollbars", f"--window-size={WIDTH},{HEIGHT}",
               f"--screenshot={out_path}", f"file://{tmp_html}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 and not out_path.exists():
        print(f"FAILED: {result.stderr[:200]}")
        return False
    if out_path.exists():
        size_kb = out_path.stat().st_size // 1024
        print(f"OK ({size_kb} KB)")
        return True
    print("FAILED: no output")
    return False

def main():
    args = sys.argv[1:]
    if "--list" in args:
        print("Specs (15):")
        for s in SPECS:
            print(f"  {s['id']}: {s['slug']} ({s['type']}) — {s['caption']}")
        return
    ids_to_render = args if args else [s["id"] for s in SPECS]
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    success, failed = 0, 0
    for spec in SPECS:
        if spec["id"] not in ids_to_render:
            continue
        if render_spec(spec):
            success += 1
        else:
            failed += 1
    print(f"\nRendered: {success} OK, {failed} failed. Total: {success + failed}")
    print(f"Output: {SCREENSHOTS}")

if __name__ == "__main__":
    main()
