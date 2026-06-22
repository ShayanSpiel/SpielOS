#!/usr/bin/env python3
"""banner.py — Self-contained banner generator.

ONE entry point for the engine, the post subagent, the CLI, and tests.
Reads tokens from system/brand.json → banner, fills CSS variables
in tools/banner-templates/{name}.html, renders the resulting HTML to
PNG via Playwright + system Chrome.

Public API:
    load_tokens(vault) -> dict
    load_template(vault, name) -> str
    build_html(template, tokens, title, subtitle, handle, vault) -> str
    render_png(html, out_path, width, height, scale, chrome_path) -> bool
    generate(vault, template, title, subtitle, handle, out_path) -> Path|None
    preview(vault, template, open_browser) -> Path
    generate_for_draft(vault, draft_path) -> Path|None
    generate_for_queue(vault) -> list[Path]

CLI:
    python3 -m banner_tool render --template default --title "..." --subtitle "..." --out x.png
    python3 -m banner_tool preview --template default --open
    python3 -m banner_tool generate-queue
    python3 -m banner_tool test --snapshot
"""

from __future__ import annotations
import argparse
import json
import os
import html
import re
import sys
import tempfile
import webbrowser
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_DEFAULT = SCRIPT_DIR.parent

TEMPLATES_DIR = "banner-templates"
BANNERS_DIR = "banners"
PREVIEW_DIR = ".preview"
BRAND_CONFIG = "brand.json"

DEFAULT_CHROME_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
)

# Required token keys. Tool fails fast if any missing.
REQUIRED_TOKENS = frozenset(
    {
        "bg",
        "font_heading",
        "font_subtitle",
        "text_title_color",
        "text_title_size",
        "text_title_size_min",
        "text_title_weight",
        "text_title_shadow",
        "text_title_lh",
        "text_title_letterspacing",
        "text_subtitle_color",
        "text_subtitle_size",
        "text_subtitle_weight",
        "text_subtitle_lh",
        "text_subtitle_letterspacing",
        "text_subtitle_highlight",
        "text_subtitle_max_chars",
        "text_handle",
        "text_handle_size",
        "text_handle_weight",
        "text_handle_letterspacing",
        "text_handle_align",
        "text_handle_bottom",
        "icon_color",
        "icon_opacity",
        "icon_size",
        "icon_rotate",
        "icon_position_x",
        "icon_position_y",
        "icon_offset_x",
        "icon_offset_y",
        "content_padding",
        "content_width",
        "text_align",
    }
)


def _vault() -> Path:
    return Path(os.environ.get("VAULT_DIR", VAULT_DEFAULT))


# ─── Loaders ──────────────────────────────────────────────────────────────


def _resolve_template(vault: Path | None, template: str | None) -> str:
    """Pick the active template name. Order: arg > brand.json > 'default'."""
    if template:
        return template
    vault = vault or _vault()
    cfg_path = vault / "system" / BRAND_CONFIG
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text())
        return cfg.get("banner", {}).get("template", "default")
    return "default"


def load_tokens(vault: Path | None = None, template: str | None = None) -> dict:
    """Read banner config from brand.json. Validates required keys.

    Tokens come from two layers (merged):
      1. ``banner.tokens`` — global defaults.
      2. ``banner.templates.{template}.tokens`` — per-template overrides.
    Per-template overrides win on key collision, so each template can
    restyle without forking brand.json.

    The ``template`` arg overrides ``banner.template`` for resolution but is
    optional — passing nothing keeps backward-compatible behavior.
    """
    vault = vault or _vault()
    cfg_path = vault / "system" / BRAND_CONFIG
    if not cfg_path.exists():
        raise FileNotFoundError(f"brand.json not found at {cfg_path}")
    cfg = json.loads(cfg_path.read_text())

    if "banner" not in cfg:
        raise ValueError(
            f"brand.json missing 'banner' section. "
            f"Run migration: see banner_tool README."
        )

    banner = cfg["banner"]
    resolved = _resolve_template(vault, template)

    global_tokens = dict(banner.get("tokens", {}))
    template_overrides = (
        banner.get("templates", {})
        .get(resolved, {})
        .get("tokens", {})
    )
    tokens = {**global_tokens, **template_overrides}

    missing = REQUIRED_TOKENS - set(tokens)
    if missing:
        raise ValueError(
            f"banner tokens (merged) missing required keys: {sorted(missing)}. "
            f"Add them to system/brand.json under banner.tokens "
            f"or banner.templates.{resolved}.tokens."
        )

    # Merge render + dimensions + template + icon_mapping for downstream use.
    tokens["_render"] = dict(banner.get("render", {}))
    tokens["_dimensions"] = dict(banner.get("dimensions", {"width": 1200, "height": 630}))
    tokens["_template"] = resolved
    tokens["_icon_mapping"] = dict(banner.get("icon_mapping", {}))
    return tokens


def load_template(vault: Path | None = None, name: str = "default") -> str:
    """Read a template HTML file. Validates the :root marker exists."""
    vault = vault or _vault()
    path = vault / "tools" / TEMPLATES_DIR / f"{name}.html"
    if not path.exists():
        raise FileNotFoundError(
            f"Banner template not found: {path}\n"
            f"Create tools/{TEMPLATES_DIR}/{name}.html "
            f"(see tools/banner-templates/default.html for the contract)."
        )
    html = path.read_text()
    if not re.search(r":root\s*\{", html):
        raise ValueError(
            f"Template {name}.html has no :root CSS block. "
            f"banner_tool requires CSS variables for all configurable values. "
            f"See tools/banner-templates/default.html for the contract."
        )
    return html


def resolve_svg(icon_name: str, vault: Path | None = None) -> str:
    """Read icon SVG, normalize fills, return inlined content."""
    vault = vault or _vault()
    cfg_path = vault / "system" / BRAND_CONFIG
    if not cfg_path.exists():
        return ""
    cfg = json.loads(cfg_path.read_text())
    registry = cfg.get("icons", {}).get("registry", {})
    entry = registry.get(icon_name, {})
    rel = entry.get("svg_path")
    if not rel:
        return ""
    abs_path = (cfg_path.parent / rel).resolve()
    if not abs_path.exists():
        print(f"  ⚠ icon {icon_name!r}: file not found at {abs_path}")
        return ""
    svg = abs_path.read_text()
    svg = re.sub(r"<\?xml.*?\?>", "", svg).strip()
    svg = re.sub(r'\s+(width|height)="[^"]*"', "", svg)
    svg = re.sub(r'\s+fill="([^"]*)"', lambda m: f' fill="{m.group(1)}"' if m.group(1) in ("none", "transparent", "currentColor") else ' fill="currentColor"', svg)
    return svg


def pick_icon(tokens: dict, title: str, subtitle: str) -> str:
    """Keyword match → icon name. Falls back to icon_mapping.default.
    Uses word-boundary matching. Title matches score higher than subtitle.
    Longest phrase match wins among ties.
    """
    mapping = tokens.get("_icon_mapping", {})
    default = mapping.get("default", "arrow-up-right")
    rules = mapping.get("rules", [])
    if not rules:
        return default
    title_lower = title.lower()
    sub_lower = subtitle.lower()
    best_score = -1
    best_icon = default
    for entry in rules:
        icon = entry.get("icon")
        for pat in entry.get("patterns", []):
            escaped = re.escape(pat)
            # Title match scores 2, subtitle match scores 1
            title_match = re.search(rf"(?<!\w){escaped}(?!\w)", title_lower)
            sub_match = re.search(rf"(?<!\w){escaped}(?!\w)", sub_lower)
            if title_match or sub_match:
                score = len(pat) * (2 if title_match else 1)
                if score > best_score:
                    best_score = score
                    best_icon = icon
    return best_icon


def title_case(text: str) -> str:
    words = text.split()
    out = []
    for w in words:
        if len(w) <= 2 and w.isupper():
            out.append(w)
        elif any(c.isupper() for c in w[1:]):
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def split_title(text: str) -> list[str]:
    words = text.strip().split()
    if len(words) <= 2:
        return [" ".join(words)]
    if len(words) <= 5:
        return _best_split(words, 2)
    return _best_split(words, 3)


def _best_split(words: list[str], parts: int) -> list[str]:
    best, best_score = None, float("inf")

    def recurse(start: int, remaining: int, splits: list[str]) -> None:
        nonlocal best, best_score
        if remaining == 1:
            lines = splits + [" ".join(words[start:])]
            counts = [len(l) for l in lines]
            score = max(counts) - min(counts)
            word_counts = [len(l.split()) for l in lines]
            if any(wc <= 1 for wc in word_counts):
                score += 5
            if score < best_score:
                best_score, best = score, lines
            return
        for end in range(start + 1, len(words) - remaining + 2):
            recurse(end, remaining - 1, splits + [" ".join(words[start:end])])

    recurse(0, parts, [])
    return best or [" ".join(words)]


# ─── Sizing ───────────────────────────────────────────────────────────────


def _strip_unit(value) -> float:
    """Parse a CSS value to a number, stripping units (px, %, em, etc)."""
    s = str(value).strip()
    for unit in ("px", "em", "rem", "%", "vh", "vw", "pt", "deg", "s", "ms"):
        if s.endswith(unit):
            return float(s[: -len(unit)])
    return float(s)


def _parse_padding(parts_str: str) -> tuple[int, int, int, int]:
    """Parse CSS shorthand padding. Returns (top, right, bottom, left)."""
    parts = parts_str.split()
    nums = [int(_strip_unit(p)) for p in parts]
    if len(nums) == 1:
        return (nums[0], nums[0], nums[0], nums[0])
    if len(nums) == 2:
        return (nums[0], nums[1], nums[0], nums[1])
    if len(nums) == 3:
        return (nums[0], nums[1], nums[2], nums[1])
    return (nums[0], nums[1], nums[2], nums[3])


def compute_title_size(
    title_lines: list[str], subtitle: str, tokens: dict, width: int, height: int
) -> int:
    """Auto-scale title to fit available area. Clamped to [min, base]."""
    base_size = int(_strip_unit(tokens["text_title_size"]))
    min_size = int(_strip_unit(tokens.get("text_title_size_min", 36)))
    t_pad, _, b_pad, h_pad = _parse_padding(tokens["content_padding"])
    avail_w = int(width * 0.85) - h_pad * 2
    longest = max((len(l) for l in title_lines), default=1)
    size_by_w = avail_w / (longest * 0.48) if longest else base_size
    sub_h = (
        _strip_unit(tokens["text_subtitle_size"])
        * float(tokens.get("text_subtitle_lh", 1.4))
        + (32 if subtitle else 0)
    )
    handle_h = (
        _strip_unit(tokens["text_handle_bottom"])
        + _strip_unit(tokens["text_handle_size"])
        + 10
    )
    text_area_h = height - t_pad - b_pad - handle_h
    lh = float(tokens["text_title_lh"])
    n = len(title_lines)
    size_by_h = (text_area_h - sub_h) / (n * lh) if n else base_size
    final = min(base_size, size_by_w, size_by_h)
    return max(int(final), min_size)


# ─── HTML builder ─────────────────────────────────────────────────────────


def _build_root_block(tokens: dict) -> str:
    """Render the :root { ... } block from tokens.

    Token names use underscores (Python/JSON convention). CSS custom
    properties use hyphens. We map underscores → hyphens at render time.
    Dimensions come from tokens._dimensions (width/height).
    """
    dims = tokens.get("_dimensions", {})
    lines = [
        f"    --width: {dims.get('width', 1200)}px;",
        f"    --height: {dims.get('height', 630)}px;",
    ]
    keys = [
        "bg",
        "font_heading",
        "font_subtitle",
        "text_title_color",
        "text_title_size",
        "text_title_size_min",
        "text_title_weight",
        "text_title_shadow",
        "text_title_lh",
        "text_title_letterspacing",
        "text_subtitle_color",
        "text_subtitle_size",
        "text_subtitle_weight",
        "text_subtitle_lh",
        "text_subtitle_letterspacing",
        "text_subtitle_highlight",
        "text_subtitle_max_chars",
        "text_handle",
        "text_handle_size",
        "text_handle_weight",
        "text_handle_letterspacing",
        "text_handle_align",
        "text_handle_bottom",
        "icon_color",
        "icon_opacity",
        "icon_size",
        "icon_rotate",
        "icon_position_x",
        "icon_position_y",
        "icon_offset_x",
        "icon_offset_y",
        "content_padding",
        "content_width",
        "text_align",
    ]
    for k in keys:
        lines.append(f"    --{k.replace('_', '-')}: {tokens[k]};")
    return ":root {\n" + "\n".join(lines) + "\n  }"


def build_html(
    template: str,
    tokens: dict,
    title: str,
    subtitle: str,
    handle: str,
    vault: Path | None = None,
    icon: str | None = None,
) -> str:
    """Inject tokens into the :root block + replace content placeholders."""
    vault = vault or _vault()
    dims = tokens.get("_dimensions", {"width": 1200, "height": 630})
    width, height = int(dims["width"]), int(dims["height"])

    # Inject CSS variables — replace the existing :root block.
    out = re.sub(
        r":root\s*\{[^}]*\}",
        _build_root_block(tokens),
        template,
        count=1,
    )

    # Truncate subtitle: word limit first, then char limit.
    words = subtitle.split()
    if len(words) > 10:
        subtitle = " ".join(words[:10]) + "\u2026"
    max_chars = int(_strip_unit(tokens.get("text_subtitle_max_chars", 80)))
    if len(subtitle) > max_chars:
        subtitle = subtitle[: max_chars - 1] + "\u2026"

    # Pick + load icon SVG.
    icon_name = icon or pick_icon(tokens, title, subtitle)
    icon_svg = resolve_svg(icon_name, vault)

    # Auto-scale title.
    title_lines = split_title(title)
    title_size = compute_title_size(title_lines, subtitle, tokens, width, height)
    # We push the final size back into tokens for the :root injection
    # (overrides text_title_size with the auto-scaled value, including unit).
    tokens_for_render = dict(tokens)
    tokens_for_render["text_title_size"] = f"{title_size}px"
    out = re.sub(
        r":root\s*\{[^}]*\}",
        _build_root_block(tokens_for_render),
        out,
        count=1,
    )

    # Replace icon position class.
    pos_x = str(tokens.get("icon_position_x", "right"))
    out = re.sub(
        r'class="bg-icon position-\w+"',
        f'class="bg-icon position-{pos_x}"',
        out,
    )

    # Replace handle align class.
    handle_align = str(tokens.get("text_handle_align", "center"))
    out = re.sub(
        r'class="handle align-\w+"',
        f'class="handle align-{handle_align}"',
        out,
    )

    # Content placeholders — escape all user/frontmatter-derived text to
    # prevent HTML/JS injection in the local Chrome render pipeline.
    title_lines_html = "\n    ".join(
        f'<div class="title-line">{html.escape(line)}</div>' for line in title_lines
    )
    subtitle_html = (
        f'<div class="subtitle-wrapper"><span class="subtitle-highlight">{html.escape(subtitle)}</span></div>'
        if subtitle
        else ""
    )

    out = out.replace("__ICON_SVG__", icon_svg)
    out = out.replace("__TITLE_LINES_HTML__", title_lines_html)
    out = out.replace("__SUBTITLE_HTML__", subtitle_html)
    out = out.replace("__HANDLE_TEXT__", html.escape(handle))

    return out


# ─── Render ───────────────────────────────────────────────────────────────


def find_chrome(render_cfg: dict | None = None) -> str | None:
    """Locate a Chrome binary. Order: env var → config → default paths."""
    env = os.environ.get("BANNER_CHROME_PATH")
    if env and Path(env).exists():
        return env
    if render_cfg and render_cfg.get("chrome_path"):
        p = Path(render_cfg["chrome_path"])
        if p.exists():
            return str(p)
    for path in DEFAULT_CHROME_PATHS:
        if Path(path).exists():
            return path
    return None


def render_png(
    html: str,
    out_path: Path,
    width: int,
    height: int,
    scale: int = 2,
    chrome_path: str | None = None,
    browser=None,
) -> bool:
    """Render HTML to PNG via Playwright + Chrome. Returns True on success.

    If `browser` is provided (a Playwright Browser instance), it is reused
    instead of launching a fresh Chrome. This is critical for batch rendering
    (generate_for_queue) where launching Chrome per-draft dominates wall-clock.
    """
    chrome = chrome_path or find_chrome()
    if not chrome:
        print(f"  ✗ no Chrome binary found. Set BANNER_CHROME_PATH or install Chrome.")
        return False
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ✗ playwright not installed. Run: pip install playwright")
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        html_path = f.name
    owns_browser = browser is None
    try:
        pw_ctx = None
        if owns_browser:
            pw_ctx = sync_playwright().start()
            launch_args = []
            if sys.platform.startswith("linux"):
                launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]
            browser = pw_ctx.chromium.launch(
                executable_path=chrome,
                args=launch_args,
            )
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=scale,
        )
        page.goto(f"file://{html_path}", wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("load", timeout=2000)
        except Exception:
            pass
        page.screenshot(
            path=str(out_path),
            clip={"x": 0, "y": 0, "width": width, "height": height},
        )
        page.close()
        if owns_browser:
            browser.close()
            if pw_ctx:
                pw_ctx.stop()
        return out_path.exists() and out_path.stat().st_size > 1000
    except Exception as e:
        print(f"  ✗ render failed: {e}")
        if owns_browser and browser:
            try:
                browser.close()
            except Exception:
                pass
            if pw_ctx:
                try:
                    pw_ctx.stop()
                except Exception:
                    pass
        return False
    finally:
        Path(html_path).unlink(missing_ok=True)


# ─── High-level operations ────────────────────────────────────────────────


def generate(
    vault: Path | None = None,
    template: str = "",
    title: str = "",
    subtitle: str = "",
    handle: str = "",
    out_path: Path | None = None,
    icon: str | None = None,
    browser=None,
) -> Path | None:
    """Full pipeline: load tokens, load template, build HTML, render PNG."""
    vault = vault or _vault()
    resolved = _resolve_template(vault, template or None)
    tokens = load_tokens(vault, template=resolved)
    tmpl = load_template(vault, resolved)
    if not handle:
        cfg = json.loads((vault / "system" / BRAND_CONFIG).read_text())
        handle = cfg.get("brand", {}).get("handle", "")
    html = build_html(tmpl, tokens, title, subtitle, handle, vault, icon=icon)
    dims = tokens.get("_dimensions", {"width": 1200, "height": 630})
    if out_path is None:
        banners_dir = vault / "assets" / BANNERS_DIR
        banners_dir.mkdir(parents=True, exist_ok=True)
        out_path = banners_dir / f"{title_case(title).replace(' ', '_').lower()}.png"
    ok = render_png(
        html,
        out_path,
        int(dims["width"]),
        int(dims["height"]),
        int(tokens.get("_render", {}).get("device_scale_factor", 2)),
        browser=browser,
    )
    return out_path if ok else None


def preview(
    vault: Path | None = None,
    template: str = "",
    title: str | None = None,
    subtitle: str | None = None,
    open_browser: bool = False,
) -> Path:
    """Write a preview HTML to assets/banners/.preview/{template}.html. Opens in browser if requested."""
    vault = vault or _vault()
    resolved = _resolve_template(vault, template or None)
    tokens = load_tokens(vault, template=resolved)
    tmpl = load_template(vault, resolved)
    cfg = json.loads((vault / "system" / BRAND_CONFIG).read_text())
    handle = cfg.get("brand", {}).get("handle", "")
    title = title or "Preview Title Goes Here"
    subtitle = subtitle or "And a preview subtitle that wraps in highlight"
    html = build_html(tmpl, tokens, title, subtitle, handle, vault)
    preview_dir = vault / "assets" / BANNERS_DIR / PREVIEW_DIR
    preview_dir.mkdir(parents=True, exist_ok=True)
    out = preview_dir / f"{template}.html"
    out.write_text(html)
    print(f"  preview written: {out}")
    if open_browser:
        try:
            webbrowser.open(f"file://{out}")
        except Exception as e:
            print(f"  ⚠ could not open browser: {e}")
    return out


def generate_for_draft(vault: Path | None, draft_path: Path, *, force: bool = False, browser=None) -> Path | None:
    """Generate a banner for a single queue draft; write back banner: field.

    Skips drafts that already have a `banner:` frontmatter field pointing to
    an existing file (unless `force=True`). The skip is a per-draft check, so
    re-running the queue generator on a mixed batch only renders the missing
    ones — saves Playwright time on re-runs.
    """
    vault = vault or _vault()
    if not draft_path.exists():
        print(f"  ✗ draft not found: {draft_path}")
        return None
    text = draft_path.read_text()
    fm, body = _parse_frontmatter(text)
    # Skip-if-exists: if the draft already has a banner file, do nothing.
    if not force:
        existing = (fm.get("banner") or "").strip()
        if existing:
            existing_path = vault / existing
            if existing_path.exists():
                print(f"    ↻ skip (banner exists): {existing}")
                return existing_path
    title = fm.get("title", draft_path.stem)
    subtitle = fm.get("subtitle", "") or ""
    if not subtitle:
        for line in body.strip().splitlines():
            line = line.strip().strip("^").strip()
            if line and not line.startswith("#") and not line.startswith("-") and not line.startswith(">"):
                subtitle = line[:80]
                break
    icon_override = fm.get("banner_icon") or None
    out = generate(
        vault=vault,
        template=load_tokens(vault).get("_template", "default"),
        title=title,
        subtitle=subtitle,
        icon=icon_override,
        out_path=vault / "assets" / BANNERS_DIR / f"{draft_path.stem}.png",
        browser=browser,
    )
    if out:
        rel = f"assets/banners/{out.name}"
        fm["banner"] = rel
        _write_frontmatter(draft_path, fm, body)
        print(f"    ✓ {rel}")
    else:
        print(f"    ⚠ Failed to generate banner for {draft_path.name}")
    return out


def generate_for_queue(vault: Path | None = None) -> list[Path]:
    """Walk content/queue/*.md and generate banners for each.

    Per-draft progress is emitted via PROGRESS: JSON lines (and a one-line
    "PROGRESS: {…}" line) so the parent or subagent user can see what's
    happening. Skips drafts that already have a banner file (use --force
    via the CLI to override).
    """
    import json as _json
    vault = vault or _vault()
    queue = vault / "content" / "queue"
    if not queue.exists():
        print("No queue directory. Nothing to banner.")
        return []
    drafts = sorted(queue.glob("*.md"))
    if not drafts:
        print("No drafts in queue. Nothing to banner.")
        return []
    print("── Auto-Generating Banners ──")
    out: list[Path] = []
    total = len(drafts)

    # Launch ONE Chrome instance and reuse it across all drafts.
    # This is the #1 performance fix: was O(N) Chrome launches (2-5s each),
    # now O(1) launch + O(N) page renders.
    chrome = find_chrome()
    shared_browser = None
    pw_ctx = None
    if chrome:
        try:
            from playwright.sync_api import sync_playwright
            pw_ctx = sync_playwright().start()
            launch_args = []
            if sys.platform.startswith("linux"):
                launch_args = ["--no-sandbox", "--disable-setuid-sandbox"]
            shared_browser = pw_ctx.chromium.launch(
                executable_path=chrome,
                args=launch_args,
            )
        except ImportError:
            print("  ⚠ playwright not installed — will try per-draft fallback")
        except Exception as e:
            print(f"  ⚠ Chrome launch failed ({e}) — will try per-draft fallback")
            shared_browser = None
            if pw_ctx:
                try:
                    pw_ctx.stop()
                except Exception:
                    pass
                pw_ctx = None

    for i, draft in enumerate(drafts, 1):
        print(f"  [{i}/{total}] {draft.stem}")
        print(f"PROGRESS: {_json.dumps({'event': 'banner', 'draft': draft.stem, 'i': i, 'n': total})}", flush=True)
        result = generate_for_draft(vault, draft, browser=shared_browser)
        if result:
            out.append(result)

    # Clean up the shared browser
    if shared_browser:
        try:
            shared_browser.close()
        except Exception:
            pass
    if pw_ctx:
        try:
            pw_ctx.stop()
        except Exception:
            pass

    print(f"\n  Generated: {len(out)}/{total} banners")
    print(f"PROGRESS: {_json.dumps({'event': 'banner_done', 'generated': len(out), 'total': total})}", flush=True)
    return out


# ─── Frontmatter helpers (minimal, local) ─────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter between --- markers. Returns (fm, body)."""
    import yaml
    if not text.startswith("---"):
        return ({}, text)
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ({}, text)
    fm = yaml.safe_load(parts[1]) or {}
    if not isinstance(fm, dict):
        fm = {}
    return (fm, parts[2])


def _write_frontmatter(path: Path, fm: dict, body: str) -> None:
    """Write YAML frontmatter + body back to file."""
    import yaml
    out = ["---", yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip(), "---", body]
    if not body.startswith("\n"):
        out.insert(3, "")
    path.write_text("\n".join(out))


# ─── Snapshot test ────────────────────────────────────────────────────────


def test_snapshot(vault: Path | None = None) -> int:
    """Render default template with mock data; compare to tests/snapshots/default.png."""
    vault = vault or _vault()
    snap_dir = vault / "tests" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / "default.png"
    out = vault / "tests" / ".tmp_default.png"
    if not snap_path.exists():
        # First run: create the snapshot, don't compare.
        result = generate(
            vault=vault,
            template="default",
            title="Snapshot Test",
            subtitle="A reference banner for visual regression",
            out_path=out,
        )
        if result is None:
            print("  ✗ render failed; cannot create snapshot")
            return 1
        snap_path.write_bytes(out.read_bytes())
        out.unlink(missing_ok=True)
        print(f"  ✓ snapshot created: {snap_path}")
        return 0
    # Subsequent runs: render + diff.
    result = generate(
        vault=vault,
        template="default",
        title="Snapshot Test",
        subtitle="A reference banner for visual regression",
        out_path=out,
    )
    if result is None:
        print("  ✗ render failed")
        return 1
    try:
        from PIL import Image, ImageChops
        a = Image.open(snap_path).convert("RGB")
        b = Image.open(out).convert("RGB")
        if a.size != b.size:
            print(f"  ✗ size mismatch: {a.size} vs {b.size}")
            return 1
        diff = ImageChops.difference(a, b)
        bbox = diff.getbbox()
        if bbox is None:
            print("  ✓ pixel-identical to snapshot")
            return 0
        # Approximate diff metric: count non-zero pixels / total.
        import numpy as np
        arr = np.array(diff)
        changed = (arr.sum(axis=2) > 5).sum()
        total = arr.shape[0] * arr.shape[1]
        pct = 100.0 * changed / total
        if pct < 2.0:
            print(f"  ✓ within tolerance ({pct:.2f}% changed)")
            return 0
        print(f"  ✗ drift detected: {pct:.2f}% of pixels differ")
        out.unlink(missing_ok=True)
        return 1
    except ImportError:
        # Fallback: byte compare.
        if snap_path.read_bytes() == out.read_bytes():
            print("  ✓ byte-identical to snapshot")
            return 0
        print("  ✗ bytes differ (PIL not installed for pixel diff)")
        return 1
    finally:
        out.unlink(missing_ok=True)


# ─── CLI ──────────────────────────────────────────────────────────────────


def _cli() -> int:
    ap = argparse.ArgumentParser(
        prog="banner_tool",
        description="Self-contained banner generator (Playwright + CSS-var templates).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_render = sub.add_parser("render", help="Render one banner to PNG")
    p_render.add_argument("--template", default="default")
    p_render.add_argument("--title", required=True)
    p_render.add_argument("--subtitle", default="")
    p_render.add_argument("--out", required=True)
    p_render.add_argument("--vault", default=None)

    p_prev = sub.add_parser("preview", help="Write a preview HTML (open in browser)")
    p_prev.add_argument("--template", default="default")
    p_prev.add_argument("--title", default=None)
    p_prev.add_argument("--subtitle", default=None)
    p_prev.add_argument("--open", action="store_true")
    p_prev.add_argument("--vault", default=None)

    sub.add_parser("generate-queue", help="Render banners for every content/queue/*.md (skip existing)")

    p_draft = sub.add_parser("generate-draft", help="Render banner for one draft")
    p_draft.add_argument("--file", required=True)
    p_draft.add_argument("--vault", default=None)
    p_draft.add_argument("--force", action="store_true", help="Re-render even if banner: exists")

    sub.add_parser("test", help="Render snapshot test")

    args = ap.parse_args()
    vault = Path(args.vault) if getattr(args, "vault", None) else _vault()

    if args.cmd == "render":
        out = generate(
            vault=vault,
            template=args.template,
            title=args.title,
            subtitle=args.subtitle,
            out_path=Path(args.out),
        )
        return 0 if out else 1
    if args.cmd == "preview":
        preview(
            vault=vault,
            template=args.template,
            title=args.title,
            subtitle=args.subtitle,
            open_browser=args.open,
        )
        return 0
    if args.cmd == "generate-queue":
        generate_for_queue(vault)
        return 0
    if args.cmd == "generate-draft":
        out = generate_for_draft(vault, Path(args.file), force=getattr(args, "force", False))
        return 0 if out else 1
    if args.cmd == "test":
        return test_snapshot(vault)
    return 2


if __name__ == "__main__":
    sys.exit(_cli())
