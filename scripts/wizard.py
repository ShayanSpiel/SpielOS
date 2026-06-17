#!/usr/bin/env python3
"""wizard.py — Interactive format + publish wizards.

Both wizards work in two modes:
  1. TTY mode: prompt the user directly via input()
  2. LLM-mediated mode: print a structured question to stderr and read the
     answer from stdin. The post subagent asks the user, then pipes the
     answer back into the wizard.

In both modes, the wizard writes its decision to .content-brief.json and the
orchestrator advances the state machine.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import ui
from engine_state import read_brief, write_brief


VALID_FORMATS = ["x", "linkedin", "blog"]
FORMAT_PRESETS = {
    "1": ["x"],
    "2": ["linkedin"],
    "3": ["blog"],
    "4": ["x", "linkedin"],
    "5": ["x", "blog"],
    "6": ["linkedin", "blog"],
    "7": ["x", "linkedin", "blog"],
    "8": "custom",
}


PLATFORM_CARDS = {
    "x": {
        "name": "X",
        "limits": "≤ 280 chars",
        "volume": "1-10 posts",
        "purpose": "Fast awareness",
        "trigger": "Tension first. Take a side.",
        "color": "bright_cyan",
    },
    "linkedin": {
        "name": "LinkedIn",
        "limits": "1300-3000 chars",
        "volume": "1-3 posts",
        "purpose": "Long-form engagement",
        "trigger": "Confessional opener. Story arc.",
        "color": "bright_blue",
    },
    "blog": {
        "name": "Blog",
        "limits": "1500-2500 words",
        "volume": "1 pillar",
        "purpose": "Source of truth",
        "trigger": "Atomize downstream to X + LI.",
        "color": "bright_magenta",
    },
}

PRESET_CARDS = {
    "4": ("X + LinkedIn",       "Awareness + Story",      ["x", "linkedin"]),
    "5": ("X + Blog",           "Awareness + Pillar",     ["x", "blog"]),
    "6": ("LinkedIn + Blog",    "Story + Pillar",         ["linkedin", "blog"]),
    "7": ("All three",          "Full coverage",          ["x", "linkedin", "blog"]),
}


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _read_input(prompt: str, fallback: str = "") -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return fallback


def _render_platform_cards(width: int = 80) -> str:
    out = []
    for i, (key, card) in enumerate(PLATFORM_CARDS.items(), 1):
        body = [
            f"{card['limits']:14s}  ·  {card['volume']}",
            f"Purpose:  {card['purpose']}",
            f"Trigger:  {card['trigger']}",
        ]
        out.append(ui.panel(f"[{i}] {card['name']}", body, accent=card["color"], width=width, style="double"))
    return "\n".join(out)


def _render_preset_row(width: int = 80) -> str:
    cells = []
    for key, (name, hint, _fmts) in PRESET_CARDS.items():
        cells.append(f"[{key}] {name}  ·  {hint}")
    line = "  ".join(cells)
    return ui._c(line, ui._FG["bright_yellow"])


def format_wizard(about: str = "") -> tuple[bool, str]:
    """Run the format-selection wizard. Returns (ok, message)."""
    brief = read_brief()
    if not brief:
        return False, "no .content-brief.json — run `engine.py content run` first"

    core = (brief.get("core_insight") or "").strip()
    if not core:
        return False, "core_insight is empty — finish the Compiler first"

    print()
    print(ui.header("FORMAT WIZARD", subtitle="Pick your weapons. The system handles the rest.", accent="cyan", width=80))
    print()
    core_display = core[:160] + "..." if len(core) > 160 else core
    print(ui.panel("CORE INSIGHT", [f'"{core_display}"'], accent="bright_blue", width=80))
    print()
    print(_render_platform_cards(width=80))
    print()
    print(ui._c("  PRESETS", ui._BOLD, ui._FG["bright_yellow"]))
    print(f"  {_render_preset_row(width=78)}")
    print()
    print(ui._c("  CUSTOM", ui._BOLD, ui._FG["bright_yellow"]))
    print(ui._c("  [8] Specify per platform  ·  e.g.  x,linkedin", ui._DIM))
    print()
    print(ui._c("  [h] Hold — reset to IDLE, drafts stay in queue", ui._DIM))
    print()
    prompt = "  Choose [1-8 or h]: " if _is_tty() else "FORMAT_WIZARD_ANSWER> "
    choice = _read_input(prompt).lower()

    if choice in ("h", "hold"):
        brief["wizard"] = {"formats": [], "hold": True, "answered_at": _now_iso()}
        write_brief(brief)
        print()
        print(ui.ego("We held the line. The drafts are safe."))
        return True, "HOLD — state will reset to IDLE"

    if choice == "8":
        return _format_wizard_custom(brief)

    if choice in FORMAT_PRESETS:
        formats = FORMAT_PRESETS[choice]
    else:
        if "," in choice or choice in VALID_FORMATS:
            formats = _parse_format_list(choice)
        else:
            return False, f"invalid choice: {choice!r}"

    if not formats:
        return False, "no valid formats selected"

    bad = [f for f in formats if f not in VALID_FORMATS]
    if bad:
        return False, f"invalid format(s): {bad} — must be one of {VALID_FORMATS}"

    brief["wizard"] = {
        "formats": formats,
        "hold": False,
        "answered_at": _now_iso(),
        "about": about,
    }
    write_brief(brief)
    print()
    print(ui.panel("SELECTED", [f"  Will draft: {', '.join(formats)}"], accent="bright_green", width=80))
    print()
    print(ui.ego("Three platforms. One insight. The system knows what to do."))
    return True, f"format-wizard complete: {formats}"


def _format_wizard_custom(brief: dict) -> tuple[bool, str]:
    print()
    print(ui._c(f"  Valid formats: {', '.join(VALID_FORMATS)}", ui._FG["bright_white"]))
    print(ui._c("  Example: x,linkedin  or  blog", ui._DIM))
    raw = _read_input("  Formats: ")
    formats = _parse_format_list(raw)
    if not formats:
        return False, "no valid formats parsed"
    bad = [f for f in formats if f not in VALID_FORMATS]
    if bad:
        return False, f"invalid format(s): {bad}"
    brief["wizard"] = {
        "formats": formats,
        "hold": False,
        "answered_at": _now_iso(),
    }
    write_brief(brief)
    print()
    print(ui.panel("SELECTED", [f"  Will draft: {', '.join(formats)}"], accent="bright_green", width=80))
    return True, f"format-wizard complete: {formats}"


def _parse_format_list(raw: str) -> list[str]:
    parts = [p.strip().lower() for p in raw.replace(" ", ",").split(",") if p.strip()]
    aliases = {"twitter": "x", "x.com": "x", "li": "linkedin", "in": "linkedin"}
    return [aliases.get(p, p) for p in parts]


def publish_wizard(queue_dir: Path) -> tuple[bool, str]:
    """Run the per-draft publish wizard."""
    brief = read_brief()
    if not brief:
        return False, "no .content-brief.json — run `engine.py content run` first"
    if not queue_dir.exists():
        return False, f"queue dir not found: {queue_dir}"

    drafts = sorted(queue_dir.glob("*.md"))
    if not drafts:
        return False, f"no drafts in {queue_dir}"

    print()
    print(ui.header("PUBLISH WIZARD", subtitle="Per-draft decision. The system handles dispatch.", accent="magenta", width=80))
    print()
    print(ui._c(f"  {len(drafts)} draft(s) ready", ui._BOLD))
    print()

    decisions: dict[str, str] = {}
    any_hold = False

    for i, d in enumerate(drafts, 1):
        platform = _read_platform(d)
        gate_state = _read_gate_state(d)
        title = _read_title(d) or d.stem
        size_info = _read_size(d)
        gate_color = "bright_green" if gate_state is True else ("bright_red" if gate_state is False else "bright_yellow")
        gate_label = "✓ gates" if gate_state is True else ("✗ gates" if gate_state is False else "— pending")
        plat_label = ui._c(f"[{platform.upper()}]", ui._BOLD, ui._FG.get(platform_color(platform), ""))
        body = [
            f"{plat_label}   {ui._c(gate_label, ui._color(gate_color))}   {ui._c(size_info, ui._DIM)}",
            "",
            f'  {ui._c(title[:80], ui._BOLD)}',
        ]
        print(ui.panel(f"▸ {i}. {d.name}", body, accent=platform_color(platform), width=80, style="double"))
        print()
        while True:
            prompt = f"  {ui._c(d.name, ui._DIM)}  [{ui._c('p', ui._FG['bright_green'])}/{ui._c('h', ui._FG['bright_yellow'])}/{ui._c('e', ui._FG['bright_cyan'])}/{ui._c('s', ui._FG['bright_black'])}]: "
            if not _is_tty():
                prompt = f"PUBLISH_WIZARD_ANSWER[{d.name}]> "
            ans = _read_input(prompt, fallback="__eof__").lower()
            if ans == "__eof__":
                return False, "wizard cancelled by user (EOF)"
            if not ans:
                continue
            if ans in ("p", "publish"):
                decisions[d.name] = "publish"
                print(ui.status("pass", f"  → {d.name}: publish"))
                break
            if ans in ("h", "hold"):
                decisions[d.name] = "hold"
                any_hold = True
                print(ui.status("warn", f"  → {d.name}: hold"))
                break
            if ans in ("e", "edit"):
                decisions[d.name] = "edit"
                print(ui.status("info", f"  → {d.name}: edit, then re-gate"))
                break
            if ans in ("s", "skip"):
                decisions[d.name] = "skip"
                print(ui.status("skip", f"  → {d.name}: skip"))
                break
            print(ui.status("fail", f"  invalid: {ans!r} (p/h/e/s)"))

    print()
    if any_hold:
        print()
        print(ui.status("warn", "One or more drafts set to HOLD. State will reset to IDLE."))
        confirm = _read_input("  Confirm HOLD (y/N): ").lower()
        if confirm != "y":
            return False, "publish-wizard cancelled at confirm"
    else:
        to_publish = [n for n, v in decisions.items() if v == "publish"]
        to_skip = [n for n, v in decisions.items() if v == "skip"]
        to_edit = [n for n, v in decisions.items() if v == "edit"]
        to_hold = [n for n, v in decisions.items() if v == "hold"]
        print(ui.panel("SUMMARY", [
            f"  Will publish: {len(to_publish)}",
            f"  Will hold:    {len(to_hold)}",
            f"  Will edit:    {len(to_edit)}",
            f"  Will skip:    {len(to_skip)}",
        ], accent="bright_cyan", width=80))
        confirm = _read_input("  Confirm? (y/N): ").lower()
        if confirm != "y":
            return False, "publish-wizard cancelled at confirm"

    brief["wizard"] = brief.get("wizard", {})
    brief["wizard"]["publish_decisions"] = decisions
    brief["wizard"]["publish_confirmed"] = not any_hold
    brief["wizard"]["publish_answered_at"] = _now_iso()
    write_brief(brief)
    print()
    print(ui.ego("Posted. Now the algorithm does its job."))
    return True, f"publish-wizard complete: {decisions}"


def platform_color(platform: str) -> str:
    return {
        "x": "bright_cyan",
        "linkedin": "bright_blue",
        "blog": "bright_magenta",
        "buffer": "bright_yellow",
        "pillar": "bright_magenta",
    }.get(platform.lower(), "white")


def _read_platform(d: Path) -> str:
    try:
        text = d.read_text()
    except OSError:
        return "—"
    if not text.startswith("---"):
        return "—"
    parts = text.split("---", 2)
    if len(parts) < 2:
        return "—"
    for line in parts[1].splitlines():
        if line.strip().startswith("platform:"):
            return line.split(":", 1)[1].strip()
    return "—"


def _read_gate_state(d: Path) -> bool | None:
    try:
        text = d.read_text()
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 2:
        return None
    for line in parts[1].splitlines():
        s = line.strip()
        if s.startswith("gates:"):
            v = s.split(":", 1)[1].strip().lower()
            if v in ("pass", "true", "yes"):
                return True
            if v in ("fail", "false", "no"):
                return False
    return None


def _read_title(d: Path) -> str:
    try:
        text = d.read_text()
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 2:
        return ""
    for line in parts[1].splitlines():
        if line.strip().startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


def _read_size(d: Path) -> str:
    try:
        text = d.read_text()
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 2:
        return ""
    body = parts[2] if len(parts) > 2 else ""
    if "platform: x" in parts[1] or "-x-" in d.name:
        return f"{len(body)} chars"
    if "platform: linkedin" in parts[1] or "linkedin" in d.name:
        return f"{len(body)} chars"
    if "platform: blog" in parts[1] or "pillar" in d.name or "blog" in d.name:
        word_count = len(body.split())
        return f"{word_count} words · {len(body)} chars"
    return f"{len(body)} chars"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
