#!/usr/bin/env python3
"""format_wizard.py — Interactive format selection wizard.

Runs between TEMPLATE_SELECT and DRAFTING. Reads .content-brief.json,
presents the user with format/quantity choices, and writes selections.

Usage:
    python3 scripts/format_wizard.py
"""

import json
import sys
from pathlib import Path

VAULT = Path(__file__).resolve().parent.parent
BRIEF_FILE = VAULT / ".content-brief.json"

FORMATS = [
    {
        "id": "x",
        "label": "X (Twitter)",
        "desc": "Short hook-based posts (280 chars)",
        "default_qty": 3,
        "qty_range": (1, 10),
        "qty_label": "How many X posts?",
    },
    {
        "id": "linkedin",
        "label": "LinkedIn",
        "desc": "Professional narrative posts (1500-3000 chars)",
        "default_qty": 1,
        "qty_range": (1, 5),
        "qty_label": "How many LinkedIn posts?",
    },
    {
        "id": "blog",
        "label": "Blog",
        "desc": "SEO long-form post (2500+ words)",
        "default_qty": 1,
        "qty_range": (1, 3),
        "qty_label": "How many blog posts?",
    },
    {
        "id": "pillar",
        "label": "Pillar Blog",
        "desc": "Deep pillar post with atomized X + LinkedIn samples",
        "default_qty": 1,
        "qty_range": (0, 2),
        "qty_label": "How many pillar blogs?",
    },
]


def color(text: str, code: str) -> str:
    codes = {
        "red": "31", "green": "32", "yellow": "33", "blue": "34",
        "dim": "2", "bold": "1", "reset": "0",
    }
    c = codes.get(code, "0")
    return f"\033[{c}m{text}\033[0m"


def read_brief() -> dict:
    if not BRIEF_FILE.exists():
        return {}
    try:
        return json.loads(BRIEF_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def write_brief(brief: dict) -> None:
    BRIEF_FILE.write_text(json.dumps(brief, indent=2))
    print(f"  {color('✓', 'green')} Saved to .content-brief.json")


def print_header(brief: dict) -> None:
    print()
    print(color("═══ Format Selection Wizard ═══", "bold"))
    print()

    ctx = brief.get("template_selection", {}).get("context", {})
    if ctx.get("archetype"):
        print(f"  Archetype:    {ctx['archetype']} — {ctx.get('archetype_label', '')}")
        print(f"  Meaning axis: {ctx.get('meaning_axis', '—')}")
        print(f"  Funnel stage: {ctx.get('funnel_stage', '—')}")
        print(f"  ICP layer:    {ctx.get('icp_layer', '—')}")
    core = brief.get("core_insight", "")
    if core:
        print(f"  Core insight: {core[:80]}{'…' if len(core) > 80 else ''}")
    print()


def show_recommendations(brief: dict) -> None:
    recs = brief.get("template_selection", {}).get("recommendations", {})
    if not recs:
        return
    print(color("── Template Recommendations ──", "bold"))
    for plat, templates in recs.items():
        print(f"  {color(plat.upper(), 'blue')}:")
        for t in templates[:3]:
            score = t.get("score", 0)
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            print(f"    {bar} {t['name']} ({t.get('id', '')})")
    print()


def select_formats(brief: dict) -> list[str]:
    print(color("── Choose Formats ──", "bold"))
    print("  Which formats do you want to create?")
    print()

    for i, fmt in enumerate(FORMATS, 1):
        print(f"  {color(str(i) + ')', 'yellow')} {fmt['label']}")
        print(f"     {fmt['desc']}")

    print()
    while True:
        raw = input(f"  Enter numbers (comma-separated, e.g. 1,3,4) [{color('1,2,3,4', 'dim')}]: ").strip()
        if not raw:
            raw = "1,2,3,4"
        try:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
            selected = []
            for idx in indices:
                if 1 <= idx <= len(FORMATS):
                    selected.append(FORMATS[idx - 1]["id"])
            if selected:
                return selected
            print(f"  {color('Please enter valid numbers (1-4).', 'red')}")
        except ValueError:
            print(f"  {color('Invalid input. Use comma-separated numbers.', 'red')}")


def select_quantities(selected: list[str], brief: dict) -> dict:
    print()
    print(color("── Quantities ──", "bold"))

    existing = brief.get("format_selection", {})
    quantities = {}

    for fmt in FORMATS:
        if fmt["id"] not in selected:
            continue

        default = existing.get(fmt["id"], {}).get("qty", fmt["default_qty"])
        lo, hi = fmt["qty_range"]
        prompt = f"  {fmt['qty_label']} [{lo}-{hi}] (default: {default}): "

        while True:
            raw = input(prompt).strip()
            if not raw:
                qty = default
                break
            try:
                qty = int(raw)
                if lo <= qty <= hi:
                    break
                print(f"  {color(f'Enter a number between {lo} and {hi}.', 'red')}")
            except ValueError:
                print(f"  {color('Enter a number.', 'red')}")

        quantities[fmt["id"]] = {"qty": qty}
    return quantities


def atomization_prompt(quantities: dict) -> dict:
    if "pillar" not in quantities:
        return quantities

    print()
    print(color("── Pillar Atomization ──", "bold"))
    print("  A pillar blog can be atomized into X and LinkedIn samples.")
    print()

    pillar = quantities["pillar"]

    raw = input(f"  How many atomized X posts? [0-10] (default: 5): ").strip()
    pillar["atomize_x"] = max(0, min(10, int(raw) if raw.isdigit() else 5))

    raw = input(f"  How many atomized LinkedIn posts? [0-3] (default: 1): ").strip()
    pillar["atomize_linkedin"] = max(0, min(3, int(raw) if raw.isdigit() else 1))

    quantities["pillar"] = pillar
    return quantities


def save_selection(brief: dict, selected: list[str], quantities: dict) -> None:
    now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    brief["format_selection"] = {
        "selected_formats": selected,
        "quantities": quantities,
        "selected_at": now,
    }
    write_brief(brief)

    print()
    print(color("── Selection Summary ──", "bold"))
    for fmt_id, info in quantities.items():
        label = next(f["label"] for f in FORMATS if f["id"] == fmt_id)
        parts = [f"  {label}: {info['qty']} post(s)"]
        if "atomize_x" in info:
            parts.append(f"  └ atomize → {info['atomize_x']} X + {info['atomize_linkedin']} LinkedIn")
        for p in parts:
            print(p)
    print()
    print(f"  {color('✓', 'green')} Next: run 'bash scripts/pipeline.sh post-draft'")


def main():
    brief = read_brief()
    if not brief:
        print(f"{color('ERROR:', 'red')} No .content-brief.json found.")
        print("  Run 'bash scripts/pipeline.sh post-start [topic]' first.")
        return 1

    print_header(brief)
    show_recommendations(brief)

    selected = select_formats(brief)
    quantities = select_quantities(selected, brief)
    quantities = atomization_prompt(quantities)
    save_selection(brief, selected, quantities)

    return 0


if __name__ == "__main__":
    sys.exit(main())
