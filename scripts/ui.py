#!/usr/bin/env python3
"""ui.py — Unicode + ANSI terminal rendering for the Spiel Engine.

Pure functions: no state, no I/O. Other modules import these and either
print the returned string or compose it with other strings. No `rich`
dependency. Falls back to plain ASCII when the terminal does not support
Unicode or color.

Public surface:
    header(title, subtitle, accent, width)
    panel(title, body, accent, width, style)
    rule(char, width, color)
    table(headers, rows, aligns, colors)
    status(icon, text, color)
    copyable(cmd, label)
    ego(text, signed)
    banner(art_lines, color, fill)
    clear()
    print_section(name, value, color)
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Iterable, Sequence


_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_ITALIC = "\033[3m"
_UNDERLINE = "\033[4m"

_FG = {
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bright_black": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
}

_BG = {
    "black": "\033[40m",
    "red": "\033[41m",
    "green": "\033[42m",
    "yellow": "\033[43m",
    "blue": "\033[44m",
    "magenta": "\033[45m",
    "cyan": "\033[46m",
    "white": "\033[47m",
    "bright_black": "\033[100m",
}


_BOX_LIGHT = {
    "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
    "h": "─", "v": "│",
    "lt": "├", "rt": "┤", "tt": "┬", "bt": "┴",
    "cross": "┼",
}
_BOX_HEAVY = {
    "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛",
    "h": "━", "v": "┃",
    "lt": "┡", "rt": "┩", "tt": "┯", "bt": "┷",
    "cross": "┿",
}
_BOX_DOUBLE = {
    "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝",
    "h": "═", "v": "║",
    "lt": "╠", "rt": "╣", "tt": "╦", "bt": "╩",
    "cross": "╬",
}
_BOX_ASCII = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|",
    "lt": "+", "rt": "+", "tt": "+", "bt": "+",
    "cross": "+",
}


def _detect_unicode() -> bool:
    enc = (sys.stdout.encoding or "").lower()
    if not enc or enc in ("ascii", "us-ascii"):
        return False
    return True


def _detect_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    enc = (sys.stdout.encoding or "").lower()
    if enc in ("ascii", "us-ascii"):
        return False
    term = (os.environ.get("TERM") or "").lower()
    if term in ("dumb", ""):
        return False
    return True


UNICODE_ENABLED = _detect_unicode()
COLOR_ENABLED = _detect_color()
_BOX = _BOX_DOUBLE if UNICODE_ENABLED else _BOX_ASCII


def _c(text: str, *codes: str) -> str:
    if not COLOR_ENABLED or not codes or not text:
        return text
    return "".join(codes) + text + _RESET


def _color(name: str) -> str:
    if not name:
        return ""
    return _FG.get(name.lower(), "")


def strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _vlen(text: str) -> int:
    return len(strip_ansi(text))


def _term_width(default: int = 80) -> int:
    try:
        return max(40, shutil.get_terminal_size().columns)
    except (OSError, ValueError):
        return default


def _fit_width(width: int, max_w: int | None = None) -> int:
    if max_w is None:
        max_w = _term_width(80)
    return min(width, max_w)


def _wrap(text: str, width: int) -> list[str]:
    if not text:
        return [""]
    out: list[str] = []
    for line in text.splitlines() or [""]:
        if _vlen(line) <= width:
            out.append(line)
            continue
        words = line.split()
        if not words:
            out.append("")
            continue
        cur = ""
        for w in words:
            candidate = (cur + " " + w).strip() if cur else w
            if _vlen(candidate) <= width:
                cur = candidate
            else:
                if cur:
                    out.append(cur)
                cur = w
        if cur:
            out.append(cur)
    return out


def _pad(text: str, width: int, align: str = "left") -> str:
    pad = max(0, width - _vlen(text))
    if align == "right":
        return " " * pad + text
    if align == "center":
        l = pad // 2
        r = pad - l
        return " " * l + text + " " * r
    return text + " " * pad


def _strip_box(s: str) -> str:
    return s.replace(_BOX["h"], "-").replace(_BOX["v"], "|")


def header(
    title: str,
    subtitle: str = "",
    accent: str = "cyan",
    width: int = 80,
) -> str:
    """Top banner with double border. Returns multi-line string."""
    w = _fit_width(width)
    b = _BOX
    inner = w - 2
    top = b["tl"] + b["h"] * inner + b["tr"]
    bot = b["bl"] + b["h"] * inner + b["br"]
    title_line = b["v"] + _c(_pad(f"  {title}", inner, "left"), _BOLD, _color(accent) or _FG["bright_white"]) + b["v"]
    lines = [_c(top, _color(accent) or _FG["bright_white"])]
    lines.append(title_line)
    if subtitle:
        sub_line = b["v"] + _c(_pad(f"  {subtitle}", inner, "left"), _DIM) + b["v"]
        lines.append(sub_line)
    lines.append(_c(bot, _color(accent) or _FG["bright_white"]))
    return "\n".join(lines)


def panel(
    title: str,
    body: str | Iterable[str],
    accent: str = "blue",
    width: int = 80,
    style: str = "double",
    title_inside: bool = True,
) -> str:
    """Boxed section with title bar and body. Returns multi-line string."""
    w = _fit_width(width)
    box = {
        "light": _BOX_LIGHT,
        "heavy": _BOX_HEAVY,
        "double": _BOX_DOUBLE,
        "ascii": _BOX_ASCII,
    }.get(style, _BOX) if UNICODE_ENABLED else _BOX_ASCII
    inner = w - 2
    b = box
    acc = _color(accent) or _FG["bright_white"]
    if isinstance(body, str):
        body_lines = body.splitlines() or [""]
    else:
        body_lines = list(body)
    title_text = f"  {title}" if title else ""
    title_padded = _pad(title_text, inner, "left")
    top = b["tl"] + b["h"] * inner + b["tr"]
    top = _c(top, acc)
    lines = [top]
    if title_inside and title:
        title_row = b["v"] + _c(_pad(title_text, inner, "left"), _BOLD, acc) + b["v"]
        sep = b["lt"] + b["h"] * inner + b["rt"]
        sep = _c(sep, acc)
        lines.append(title_row)
        lines.append(sep)
    for bl in body_lines:
        if _vlen(bl) > inner:
            bl = bl[: max(0, inner - 1)] + "…"
        row = b["v"] + _pad(bl, inner, "left") + b["v"]
        lines.append(row)
    bot = b["bl"] + b["h"] * inner + b["br"]
    bot = _c(bot, acc)
    lines.append(bot)
    return "\n".join(lines)


def rule(
    char: str = "─",
    width: int = 80,
    color: str = "bright_black",
) -> str:
    """Horizontal divider line."""
    if not UNICODE_ENABLED:
        if char not in ("-", "="):
            char = "-"
    w = _fit_width(width)
    line = char * w
    return _c(line, _color(color))


def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    aligns: Sequence[str] | None = None,
    colors: Sequence[str] | None = None,
    width: int = 80,
) -> str:
    """Unicode-bordered table. Auto-sizes columns to fit `width`."""
    w = _fit_width(width)
    b = _BOX if UNICODE_ENABLED else _BOX_ASCII
    n = len(headers)
    if n == 0:
        return ""
    aligns = list(aligns) if aligns else ["left"] * n
    while len(aligns) < n:
        aligns.append("left")
    rows = list(rows)
    cell_widths = [_vlen(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row[:n]):
            cell_widths[i] = max(cell_widths[i], _vlen(str(cell)))
    total_content = sum(cell_widths) + 3 * (n - 1) + 2
    if total_content > w:
        excess = total_content - w
        shrink_from = n - 1
        while excess > 0 and shrink_from >= 0:
            if cell_widths[shrink_from] > 6:
                give = min(excess, cell_widths[shrink_from] - 6)
                cell_widths[shrink_from] -= give
                excess -= give
            shrink_from -= 1
    elif total_content < w:
        if n > 0:
            cell_widths[0] += w - total_content
    data_w = sum(cell_widths) + 3 * (n - 1) + 2
    top_w_data = sum(cell_widths) + (n - 1) + 2
    extra = data_w - top_w_data
    sep = b["lt"] + b["h"] * (sum(cell_widths) + 3 * (n - 1)) + b["rt"]
    top = b["tl"] + b["h"] * extra + b["tt"].join(b["h"] * cw for cw in cell_widths) + b["tr"]
    bot = b["bl"] + b["h"] * extra + b["bt"].join(b["h"] * cw for cw in cell_widths) + b["br"]
    def render_row(cells: Sequence[str], is_header: bool = False) -> str:
        out = [b["v"]]
        for i, cell in enumerate(cells):
            text = _pad(str(cell), cell_widths[i], aligns[i] if i < len(aligns) else "left")
            if is_header:
                text = _c(text, _BOLD)
            elif colors and i < len(colors) and colors[i]:
                text = _c(text, _color(colors[i]))
            out.append(text)
            if i < n - 1:
                out.append(_c(" │ ", _DIM))
        out.append(b["v"])
        return "".join(out)
    lines = [_c(top, _FG["bright_white"])]
    lines.append(_c(sep, _FG["bright_black"]))
    lines.append(render_row(headers, is_header=True))
    lines.append(_c(sep, _FG["bright_black"]))
    for row in rows:
        cells = list(row) + [""] * (n - len(row))
        lines.append(render_row(cells[:n]))
    lines.append(_c(bot, _FG["bright_white"]))
    return "\n".join(lines)


_STATUS_MAP = {
    "pass": ("✓", "bright_green"),
    "ok": ("✓", "bright_green"),
    "yes": ("✓", "bright_green"),
    "true": ("✓", "bright_green"),
    "fail": ("✗", "bright_red"),
    "no": ("✗", "bright_red"),
    "false": ("✗", "bright_red"),
    "bad": ("✗", "bright_red"),
    "warn": ("⚠", "bright_yellow"),
    "skip": ("·", "bright_black"),
    "info": ("ℹ", "bright_blue"),
    "arrow": ("→", "bright_cyan"),
    "bullet": ("·", "bright_black"),
    "dot": ("●", "bright_cyan"),
}


def status(icon: str, text: str, color: str = "white") -> str:
    """Single-line status indicator. Returns a single line."""
    if isinstance(icon, bool):
        resolved = ("✓", "bright_green") if icon else ("✗", "bright_red")
    else:
        key = str(icon).lower()
        resolved = _STATUS_MAP.get(key, (str(icon), "white"))
    icon_glyph, icon_color_name = resolved
    icon_colored = _c(f"  {icon_glyph} ", _color(icon_color_name) or _FG["bright_white"])
    text_colored = _c(text, _color(color) or _FG["white"])
    return icon_colored + text_colored


def copyable(cmd: str, label: str = "", width: int = 80) -> str:
    """Show a paste-ready shell command. Multi-line."""
    w = _fit_width(width)
    out: list[str] = []
    if label:
        out.append(_c(f"  {label}", _DIM))
    cmd_lines = cmd.splitlines() or [cmd]
    prompt = _c("  $ ", _BOLD, _FG["bright_green"])
    for i, line in enumerate(cmd_lines):
        prefix = prompt if i == 0 else _c("  > ", _BOLD, _FG["bright_green"])
        out.append(prefix + _c(line, _FG["bright_cyan"]))
    return "\n".join(out)


def ego(text: str, signed: bool = True) -> str:
    """Centered, italic, dimmed 'ego' one-liner."""
    w = _term_width(80)
    full = f'"{text}"'
    if signed:
        full = full + "  " + _c("— also, the next line", _DIM, _ITALIC)
    pad = max(0, (w - _vlen(full)) // 2)
    return (" " * pad) + _c(full, _ITALIC, _DIM)


def banner(
    art_lines: Sequence[str],
    color: str = "cyan",
    fill: str = "·",
    width: int = 80,
) -> str:
    """Full-screen cool header. Multi-line."""
    w = _fit_width(width)
    inner = w - 2
    accent = _color(color) or _FG["bright_white"]
    b = _BOX if UNICODE_ENABLED else _BOX_ASCII
    top = b["tl"] + b["h"] * inner + b["tr"]
    bot = b["bl"] + b["h"] * inner + b["br"]
    lines = [_c(top, accent)]
    if not UNICODE_ENABLED:
        fill = "."
    fill_line = fill * w if UNICODE_ENABLED else "." * w
    lines.append(_c(fill_line, _DIM, accent))
    for art in art_lines:
        if _vlen(art) > inner:
            art = art[: max(0, inner - 1)] + "…"
        row = b["v"] + _c(_pad(f"  {art}", inner, "center"), _BOLD, accent) + b["v"]
        lines.append(row)
    lines.append(_c(fill_line, _DIM, accent))
    lines.append(_c(bot, accent))
    return "\n".join(lines)


def clear() -> None:
    """Clear the terminal. No-op when not a TTY."""
    if not sys.stdout.isatty():
        return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def print_section(name: str, value: str, color: str = "bright_cyan", width: int = 80) -> str:
    """Render a 'NAME: value' line with the NAME colored."""
    name_colored = _c(name, _BOLD, _color(color) or _FG["bright_white"])
    return f"  {name_colored}  {value}"


def kvpairs(pairs: Sequence[tuple[str, str]], color: str = "bright_cyan", width: int = 80) -> str:
    """Render a list of key: value pairs as aligned rows."""
    w = _fit_width(width)
    if not pairs:
        return ""
    key_w = max(_vlen(k) for k, _ in pairs)
    lines = []
    for k, v in pairs:
        key_colored = _c(_pad(k, key_w + 2, "left"), _BOLD, _color(color) or _FG["bright_white"])
        lines.append(f"  {key_colored}  {v}")
    return "\n".join(lines)


def progress(current: int, total: int, label: str = "", width: int = 40) -> str:
    """Render a progress bar. Returns single line."""
    if total <= 0:
        return ""
    pct = max(0, min(1, current / total))
    fill_w = max(0, int(width * pct))
    bar = "█" * fill_w + "░" * (width - fill_w) if UNICODE_ENABLED else "#" * fill_w + "-" * (width - fill_w)
    pct_str = f"{int(pct * 100):3d}%"
    bar_colored = _c(bar, _FG["bright_cyan"])
    label_part = f"  {label}  " if label else "  "
    return label_part + bar_colored + "  " + _c(pct_str, _DIM)


def dot_bullet(text: str, color: str = "bright_cyan") -> str:
    """Single bullet item: '  • text'"""
    glyph = "●" if UNICODE_ENABLED else "*"
    return "  " + _c(glyph, _color(color) or _FG["bright_white"]) + "  " + text


def print(*args, **kwargs):  # type: ignore[no-redef]
    """Default print. Real print, not our wrapper."""
    __builtins__.print(*args, **kwargs)


def say(msg: str) -> None:
    """Print a single line, no trailing newline handling."""
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def section_break(width: int = 80) -> str:
    """Two-rule section break: ─── / blank / ───"""
    w = _fit_width(width)
    return rule("─", w) + "\n\n" + rule("─", w)


def key_value_grid(pairs: Sequence[tuple[str, str]], color: str = "bright_cyan", width: int = 80) -> str:
    """Aligned key: value grid using the wider-of-pairs key width."""
    return kvpairs(pairs, color=color, width=width)
