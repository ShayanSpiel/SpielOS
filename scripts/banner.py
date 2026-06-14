#!/usr/bin/env python3
"""banner.py — Generate banner images for queue drafts (Puppeteer-based).

Replaces `scripts/generate-banner.js` (419 LOC of Node.js) with ~200 LOC of Python.
Honors brand-config.json. Auto-writes banner path into the queue draft's frontmatter.

Usage:
    python3 scripts/banner.py --queue-id 2026-06-12-tweet-01 --type social
    python3 scripts/banner.py --list
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from state import BANNERS_DIR, BRAND_CONFIG, QUEUE_DIR, VAULT, parse_frontmatter, write_frontmatter

DEFAULT_TEMPLATE = Path(__file__).parent / "banner-templates" / "default.html"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def load_brand() -> dict:
    if not BRAND_CONFIG.exists():
        raise SystemExit(f"brand-config.json not found: {BRAND_CONFIG}")
    return json.loads(BRAND_CONFIG.read_text())


def load_template() -> str:
    if not DEFAULT_TEMPLATE.exists():
        raise SystemExit(f"template not found: {DEFAULT_TEMPLATE}")
    return DEFAULT_TEMPLATE.read_text()


def list_queue() -> None:
    if not QUEUE_DIR.exists():
        print("no queue directory")
        return
    for f in sorted(QUEUE_DIR.glob("*.md")):
        fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        title = fm.get("title", "(no title)")
        has_banner = "yes" if fm.get("banner") else "no"
        print(f"  {f.stem}\n    title: {title}\n    banner: {has_banner}")


def read_draft(queue_id: str) -> Path:
    path = QUEUE_DIR / f"{queue_id}.md"
    if path.exists():
        return path
    matches = list(QUEUE_DIR.glob(f"{queue_id}*.md"))
    if not matches:
        raise SystemExit(f"no queue file found matching: {queue_id}")
    return matches[0]


def title_case(text: str) -> str:
    return " ".join(w if (len(w) <= 2 and w.isupper()) else w.capitalize() for w in text.split())


def pick_icon(config: dict, title: str, subtitle: str) -> str:
    icons = config.get("icons", {})
    mapping = icons.get("mapping", [])
    if not mapping:
        return icons.get("default", "arrow-up-right-square")
    text = f"{title} {subtitle}".lower()
    candidates = []
    for entry in mapping:
        for pat in entry.get("patterns", []):
            if pat in text:
                candidates.append((len(pat), entry.get("icon")))
    if not candidates:
        return icons.get("default", "arrow-up-right-square")
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_icon_svg(config: dict, name: str) -> str:
    icons = config.get("icons", {})
    if icons.get("source") == "web":
        return ""
    registry = icons.get("registry", {})
    entry = registry.get(name, {})
    rel = entry.get("svg_path")
    if not rel:
        return entry.get("fallback_svg", "")
    abs_path = (BRAND_CONFIG.parent / rel).resolve()
    if not abs_path.exists():
        return entry.get("fallback_svg", "")
    svg = abs_path.read_text()
    import re
    svg = re.sub(r"<\?xml.*?\?>", "", svg).strip()
    svg = re.sub(r'\s+(width|height)="[^"]*"', "", svg)
    def _fix_fill(m):
        v = m.group(1)
        if v in ("none", "transparent", "currentColor"):
            return f' fill="{v}"'
        return ' fill="currentColor"'
    svg = re.sub(r'\s+fill="([^"]*)"', _fix_fill, svg)
    return svg


def split_title(text: str) -> list[str]:
    words = text.strip().split()
    if len(words) <= 2:
        return [" ".join(words)]
    if len(words) <= 5:
        return _best_split(words, 2)
    return _best_split(words, 3)


def _best_split(words: list[str], parts: int) -> list[str]:
    best, best_score = None, float("inf")

    def recurse(start, remaining, splits):
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


def auto_scale_font(title_lines: list[str], subtitle: str, bt: dict, width: int, height: int) -> int:
    title_cfg = bt["title"]
    base_size = title_cfg["font_size_px"]
    min_size = title_cfg.get("font_size_min_px", 36)

    padding = bt.get("layout", {}).get("content_padding", "60px 70px 80px")
    parts = padding.split()
    h_pad = int(parts[1].replace("px", "")) if len(parts) >= 2 else int(parts[0].replace("px", ""))
    avail_w = int(width * 0.85) - h_pad * 2

    longest = max((len(l) for l in title_lines), default=1)
    size_by_w = avail_w / (longest * 0.48) if longest else base_size

    t_pad = int(parts[0].replace("px", ""))
    b_pad = int(parts[-1].replace("px", ""))
    handle = bt.get("handle", {})
    content_max_h = height - t_pad - b_pad - handle.get("position_bottom_px", 28) - handle.get("font_size_px", 18) - 10
    text_area_h = content_max_h - t_pad - b_pad

    lh = float(title_cfg.get("line_height", 0.9))
    sub_h = bt["subtitle"]["font_size_px"] * float(bt["subtitle"].get("line_height", 1.4)) + (32 if subtitle else 0)
    n = len(title_lines)
    size_by_h = (text_area_h - sub_h) / (n * lh) if n else base_size

    final = min(base_size, size_by_w, size_by_h)
    return max(int(final), min_size)


def truncate_to_fit(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"


def render_html(template: str, config: dict, banner_type: str, title: str, subtitle: str, headline: str = "") -> str:
    bt = config["banners"].get(banner_type, config["banners"].get("default"))
    brand = config["brand"]
    fonts = config["fonts"]
    icon_style = config.get("icons", {}).get("style", {})
    layout = bt.get("layout", {})

    icon_name = pick_icon(config, title, subtitle)
    icon_svg = load_icon_svg(config, icon_name)

    MAX_SUBTITLE_CHARS = 50
    subtitle = subtitle[:MAX_SUBTITLE_CHARS - 1] + "…" if len(subtitle) > MAX_SUBTITLE_CHARS else subtitle

    display_title = headline if headline else title
    title_lines = split_title(display_title)
    title_lines_html = "\n".join(f'<div class="title-line">{line}</div>' for line in title_lines)

    bg = brand.get("background", {})
    bg_value = bg.get("value", brand.get("primary_bg", "#e8e8e8"))
    bg_style = f"background: {bg_value};"

    pos_x = layout.get("icon_position_x", "right")
    pos_y = layout.get("icon_position_y", "center")
    if pos_x == "right":
        icon_position_style = f'right: {layout.get("icon_offset_x", "0%")}; top: 50%;'
    elif pos_x == "left":
        icon_position_style = f'left: {layout.get("icon_offset_x", "0%")}; top: 50%;'
    else:
        x_map = {"left": "0%", "center": "50%", "right": "100%"}
        y_map = {"top": "0%", "center": "50%", "bottom": "100%"}
        icon_position_style = f'left: {x_map.get(pos_x, "50%")}; top: {y_map.get(pos_y, "50%")};'

    handle_align = bt.get("handle", {}).get("alignment", "center")
    handle_padding = "70px" if handle_align in ("left", "right") else "0px"

    html = template
    html = html.replace("__GOOGLE_FONTS__", fonts.get("google_fonts", ""))
    html = html.replace("__WIDTH__", str(bt["dimensions"]["width"]))
    html = html.replace("__HEIGHT__", str(bt["dimensions"]["height"]))
    html = html.replace("__BG_STYLE__", bg_style)
    html = html.replace("__FONT_FAMILY__", fonts.get("heading", "Inter"))
    html = html.replace("__SUBTITLE_FONT__", fonts.get("subtitle", "Merriweather"))
    for field in ["size_px", "weight", "color", "letter_spacing", "line_height"]:
        pass
    html = html.replace("__TITLE_SIZE__", str(bt["title"]["font_size_px"]))
    html = html.replace("__TITLE_WEIGHT__", str(bt["title"]["weight"]))
    html = html.replace("__TITLE_COLOR__", bt["title"]["color"])
    html = html.replace("__TITLE_LETTER_SPACING__", str(bt["title"]["letter_spacing"]))
    html = html.replace("__TITLE_LINE_HEIGHT__", str(bt["title"]["line_height"]))
    html = html.replace("__SUBTITLE_SIZE__", str(bt["subtitle"]["font_size_px"]))
    html = html.replace("__SUBTITLE_WEIGHT__", str(bt["subtitle"]["weight"]))
    html = html.replace("__SUBTITLE_COLOR__", bt["subtitle"]["color"])
    html = html.replace("__SUBTITLE_LETTER_SPACING__", str(bt["subtitle"]["letter_spacing"]))
    html = html.replace("__SUBTITLE_LINE_HEIGHT__", str(bt["subtitle"]["line_height"]))
    html = html.replace("__SUBTITLE_HIGHLIGHT__", bt["subtitle"].get("highlight", "transparent"))
    html = html.replace("__HANDLE_TEXT__", brand.get("handle", ""))
    html = html.replace("__HANDLE_SIZE__", str(bt["handle"]["font_size_px"]))
    html = html.replace("__HANDLE_WEIGHT__", str(bt["handle"]["weight"]))
    html = html.replace("__HANDLE_COLOR__", bt["handle"]["color"])
    html = html.replace("__HANDLE_LETTER_SPACING__", str(bt["handle"]["letter_spacing"]))
    html = html.replace("__HANDLE_BOTTOM__", str(bt["handle"].get("position_bottom_px", 28)))
    html = html.replace("__HANDLE_ALIGN__", handle_align)
    html = html.replace("__HANDLE_PADDING__", handle_padding)
    html = html.replace("__ICON_SVG__", icon_svg)
    html = html.replace("__ICON_OPACITY__", str(icon_style.get("opacity", 0.30)))
    html = html.replace("__ICON_COLOR__", icon_style.get("color", "#444444"))
    html = html.replace("__ICON_SIZE__", str(icon_style.get("size_percent", 120)))
    html = html.replace("__ICON_ROTATE__", str(icon_style.get("rotate_deg", 30)))
    html = html.replace("__ICON_POSITION_STYLE__", icon_position_style)
    html = html.replace("__ICON_TRANSFORM__", "")
    html = html.replace("__TITLE_LINES_HTML__", title_lines_html)
    html = html.replace("__SUBTITLE_HTML__",
                        f'<div class="subtitle-wrapper"><span class="subtitle-highlight">{subtitle}</span></div>' if subtitle else "")
    html = html.replace("__CONTENT_PADDING__", layout.get("content_padding", "60px"))
    html = html.replace("__TEXT_ALIGN__", bt.get("text_align", "left"))
    return html


def render_png(html: str, out_path: Path, width: int, height: int) -> bool:
    """Render HTML to PNG via Puppeteer (Node)."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        html_path = f.name
    js_script = f"""
const puppeteer = require('puppeteer');
(async () => {{
  const browser = await puppeteer.launch({{
    executablePath: '{CHROME_PATH}',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  }});
  const page = await browser.newPage();
  await page.setViewport({{ width: {width}, height: {height}, deviceScaleFactor: 1 }});
  await page.goto('file://{html_path}', {{ waitUntil: 'networkidle0' }});
  await page.screenshot({{ path: '{out_path}', type: 'png', clip: {{x:0, y:0, width:{width}, height:{height}}}}});
  await browser.close();
  console.log('ok');
}})();
"""
    js_path = out_path.with_suffix(".tmp.js")
    js_path.write_text(js_script)
    try:
        result = subprocess.run(["node", str(js_path)], capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"  ✗ puppeteer: {result.stderr[:200]}")
            return False
        return out_path.exists()
    finally:
        js_path.unlink(missing_ok=True)
        Path(html_path).unlink(missing_ok=True)


def update_draft_banner(draft_path: Path, banner_rel: str) -> None:
    content = draft_path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    fm["banner"] = banner_rel
    write_frontmatter(draft_path, fm, body)


def main():
    parser = argparse.ArgumentParser(description="Generate banner for a queue draft.")
    parser.add_argument("--queue-id", help="Generate banner for the given queue file")
    parser.add_argument("--type", default="default", help="Banner type: default (1200x630) or social (1200x675)")
    parser.add_argument("--title", help="Override title")
    parser.add_argument("--subtitle", help="Override subtitle")
    parser.add_argument("--list", action="store_true", help="List queue items")
    args = parser.parse_args()

    if args.list:
        list_queue()
        return 0

    if not args.queue_id:
        parser.print_help()
        return 1

    config = load_brand()
    bt = config["banners"].get(args.type, config["banners"].get("default"))
    width = bt["dimensions"]["width"]
    height = bt["dimensions"]["height"]

    draft_path = read_draft(args.queue_id)
    fm, _ = parse_frontmatter(draft_path.read_text(encoding="utf-8"))
    title = args.title or fm.get("title", draft_path.stem)
    subtitle = args.subtitle or fm.get("subtitle", "")

    BANNERS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BANNERS_DIR / f"{draft_path.stem}.png"
    banner_rel = f"assets/banners/{draft_path.stem}.png"

    template = load_template()
    html = render_html(template, config, args.type, title_case(title), subtitle)
    if not render_png(html, out_path, width, height):
        return 1

    update_draft_banner(draft_path, banner_rel)
    print(f"  ✓ {out_path.relative_to(VAULT)}")
    print(f"  ✓ wrote banner: {banner_rel} → {draft_path.name}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
