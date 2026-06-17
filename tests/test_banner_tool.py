"""test_banner_tool.py — Unit + integration tests for banner_tool.

Covers:
  - token loading + required-key validation
  - template loading + :root contract enforcement
  - icon picking (keyword match + fallback)
  - title splitting + auto-scaling
  - HTML builder (CSS vars injected, content placeholders replaced)
  - generate() end-to-end (PNG produced, sane size)
  - snapshot regression (default.png, fails on >2% pixel drift)
  - generate_for_draft (writes PNG, writes banner: frontmatter)

Snapshot test: first run creates the snapshot. Subsequent runs diff.
The snapshot is checked into tests/snapshots/default.png.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import banner_tool  # noqa: E402
from banner_tool import (  # noqa: E402
    build_html,
    compute_title_size,
    load_template,
    load_tokens,
    pick_icon,
    split_title,
)


VAULT = Path(__file__).resolve().parent.parent


# ── Token + template loaders ─────────────────────────────────────────────


def test_load_tokens_returns_all_required_keys():
    tokens = load_tokens(VAULT)
    for key in banner_tool.REQUIRED_TOKENS:
        assert key in tokens, f"missing required token: {key}"
    assert "_render" in tokens
    assert "_dimensions" in tokens
    assert tokens["_dimensions"]["width"] == 1200
    assert tokens["_dimensions"]["height"] == 630


def test_load_tokens_missing_keys_raises(tmp_path: Path):
    cfg = {"banner": {"tokens": {"bg": "#fff"}}}
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "brand-config.json").write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match="missing required keys"):
        load_tokens(tmp_path)


def test_load_template_requires_root_block(tmp_path: Path):
    tpl_dir = tmp_path / "scripts" / "banner-templates"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "bad.html").write_text("<html><body>no :root here</body></html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "brand-config.json").write_text(
        json.dumps({"brand": {"handle": "@x"}, "banner": {"tokens": {}}})
    )
    with pytest.raises(ValueError, match=":root"):
        load_template(tmp_path, "bad")


def test_load_template_default_runs():
    tpl = load_template(VAULT, "default")
    assert ":root" in tpl
    assert "__TITLE_LINES_HTML__" in tpl
    assert "__HANDLE_TEXT__" in tpl


# ── Icon picking ─────────────────────────────────────────────────────────


def test_pick_icon_keyword_match():
    tokens = {"_icon_mapping": {"default": "fallback", "rules": [
        {"patterns": ["ai", "agent"], "icon": "sparkles"},
        {"patterns": ["github", "open source"], "icon": "github"},
    ]}}
    assert pick_icon(tokens, "AI agents are cool", "") == "sparkles"
    # Longer pattern wins on tie
    assert pick_icon(tokens, "Open source on github", "") == "github"
    # No match → default
    assert pick_icon(tokens, "Random title", "") == "fallback"
    # Subtitle match → lower priority
    assert pick_icon(tokens, "Title", "about AI agents") == "sparkles"


def test_pick_icon_word_boundary():
    """Substring 'content' must not match 'discontent'."""
    tokens = {"_icon_mapping": {"default": "fallback", "rules": [
        {"patterns": ["content"], "icon": "mail"},
        {"patterns": ["plan"], "icon": "crosshair"},
    ]}}
    assert pick_icon(tokens, "Content strategy", "") == "mail"
    assert pick_icon(tokens, "discontent", "") == "fallback"
    assert pick_icon(tokens, "Strategic plan", "") == "crosshair"
    assert pick_icon(tokens, "airplane", "") == "fallback"


def test_pick_icon_no_rules_returns_default():
    tokens = {"_icon_mapping": {"default": "x", "rules": []}}
    assert pick_icon(tokens, "Anything", "") == "x"


# ── Title split + auto-scale ─────────────────────────────────────────────


def test_split_title_short_unchanged():
    assert split_title("Hello World") == ["Hello World"]


def test_split_title_three_lines_max():
    lines = split_title("One Two Three Four Five Six Seven")
    assert len(lines) <= 3
    assert all(len(line) > 0 for line in lines)


def test_compute_title_size_clamps_to_min():
    tokens = {
        "text_title_size": 96,
        "text_title_size_min": 56,
        "text_title_lh": 1.1,
        "text_subtitle_size": 32,
        "text_subtitle_lh": 1.4,
        "text_handle_bottom": 32,
        "text_handle_size": 22,
        "content_padding": "60px 80px 80px",
    }
    # Very long single-line title — should still be ≥ min.
    size = compute_title_size(["x" * 200], "subtitle", tokens, 1200, 630)
    assert size >= 56
    assert size <= 96


# ── HTML builder ─────────────────────────────────────────────────────────


def test_build_html_injects_root_vars_and_replaces_placeholders():
    tokens = load_tokens(VAULT)
    tmpl = load_template(VAULT, "default")
    html = build_html(
        tmpl, tokens, "Test Title", "Test subtitle", "@test", VAULT
    )
    # :root block was rewritten — contains a CSS variable we just set
    assert "--text-title-color:" in html
    # Content placeholders replaced
    assert "__TITLE_LINES_HTML__" not in html
    assert "__SUBTITLE_HTML__" not in html
    assert "__HANDLE_TEXT__" not in html
    assert "__ICON_SVG__" not in html
    # Title + subtitle + handle present
    assert "Test Title" in html
    assert "Test subtitle" in html
    assert "@test" in html


def test_build_html_uses_icon_class_for_position():
    tokens = load_tokens(VAULT)
    tmpl = load_template(VAULT, "default")
    html = build_html(tmpl, tokens, "AI agents", "subtitle", "@x", VAULT)
    # icon_position_x default = right → position-right class
    assert "position-right" in html


def test_build_html_truncates_long_subtitle():
    tokens = load_tokens(VAULT)
    tokens["text_subtitle_max_chars"] = 20
    tmpl = load_template(VAULT, "default")
    long_sub = "x" * 100
    html = build_html(tmpl, tokens, "Title", long_sub, "@x", VAULT)
    assert "\u2026" in html
    # The truncated version (≤ 20 chars + ellipsis) should be in the HTML.
    assert "x" * 19 + "\u2026" in html


# ── End-to-end render (requires system Chrome) ───────────────────────────


def _has_chrome() -> bool:
    return banner_tool.find_chrome() is not None


@pytest.mark.skipif(not _has_chrome(), reason="no Chrome binary available")
def test_generate_produces_png(tmp_path: Path):
    out = tmp_path / "banner.png"
    result = banner_tool.generate(
        vault=VAULT,
        template="default",
        title="Test Banner",
        subtitle="A subtitle for testing",
        handle="@test",
        out_path=out,
    )
    assert result is not None
    assert result.exists()
    assert result.stat().st_size > 5_000  # Real PNG, not an error stub


@pytest.mark.skipif(not _has_chrome(), reason="no Chrome binary available")
def test_generate_for_draft_writes_png_and_frontmatter(tmp_path: Path):
    # Build a minimal vault
    (tmp_path / "content" / "queue").mkdir(parents=True)
    (tmp_path / "assets" / "banners").mkdir(parents=True)
    # Copy brand-config + template + icons
    shutil.copy(VAULT / "assets" / "brand-config.json", tmp_path / "assets" / "brand-config.json")
    shutil.copytree(
        VAULT / "scripts" / "banner-templates",
        tmp_path / "scripts" / "banner-templates",
    )
    shutil.copytree(VAULT / "assets" / "icons", tmp_path / "assets" / "icons")
    # Write a draft
    draft = tmp_path / "content" / "queue" / "2026-01-01-test.md"
    draft.write_text(
        "---\ntitle: Test Draft\nsubtitle: For Draft Test\n---\n\nbody\n"
    )
    result = banner_tool.generate_for_draft(tmp_path, draft)
    assert result is not None
    assert result.exists()
    # Frontmatter was updated with banner: field
    text = draft.read_text()
    assert "banner:" in text
    assert "assets/banners/2026-01-01-test.png" in text


# ── Snapshot regression test ─────────────────────────────────────────────


SNAPSHOT_PATH = VAULT / "tests" / "snapshots" / "default.png"


@pytest.mark.skipif(not _has_chrome(), reason="no Chrome binary available")
def test_snapshot_default():
    """First run: creates tests/snapshots/default.png.
    Subsequent runs: diffs against it; fails on >2% pixel drift.
    """
    if not SNAPSHOT_PATH.exists():
        result = banner_tool.generate(
            vault=VAULT,
            template="default",
            title="Snapshot Test",
            subtitle="A reference banner for visual regression",
            out_path=VAULT / "tests" / ".tmp_default.png",
        )
        assert result is not None
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_bytes(result.read_bytes())
        result.unlink(missing_ok=True)
        pytest.skip("snapshot created; run again to compare")
    # Subsequent runs: render + diff
    out = VAULT / "tests" / ".tmp_default.png"
    result = banner_tool.generate(
        vault=VAULT,
        template="default",
        title="Snapshot Test",
        subtitle="A reference banner for visual regression",
        out_path=out,
    )
    assert result is not None
    try:
        from PIL import Image, ImageChops
        import numpy as np

        a = Image.open(SNAPSHOT_PATH).convert("RGB")
        b = Image.open(out).convert("RGB")
        if a.size != b.size:
            pytest.fail(f"size mismatch: {a.size} vs {b.size}")
        diff = ImageChops.difference(a, b)
        arr = np.array(diff)
        changed = int((arr.sum(axis=2) > 5).sum())
        total = arr.shape[0] * arr.shape[1]
        pct = 100.0 * changed / total
        assert pct < 2.0, f"visual drift detected: {pct:.2f}% of pixels differ"
    except ImportError:
        # Without PIL: byte compare is the fallback
        assert SNAPSHOT_PATH.read_bytes() == out.read_bytes(), (
            "bytes differ (install pillow for pixel-diff)"
        )
    finally:
        out.unlink(missing_ok=True)
