#!/usr/bin/env python3
"""generate-arch-canvas.py — Generate Obsidian Canvas architecture diagram.

Reads AGENTS.md, .wiki-state, and rules.yaml to produce a visual map
of the Spiel Engine at assets/architecture.canvas.

Usage:
    python3 scripts/generate-arch-canvas.py
"""

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

VAULT = Path(os.environ.get("VAULT_DIR", Path(__file__).resolve().parent.parent))
CANVAS_PATH = VAULT / "assets" / "architecture.canvas"

WIKI_STATES = [
    "INGESTING", "ANALYZING", "RECONCILING", "LINKING",
    "INDEXING", "VALIDATING", "COMPLETE",
]
CONTENT_STATES = [
    "SESSION_CAPTURE", "STRATEGY_LOAD", "ICP_WORLD_BUILD",
    "DRAFTING", "GATE_CHECK", "REVISING", "QUEUE",
    "PUBLISHING", "ARCHIVING", "ANALYZING_POST", "COMPLETE_POST",
]
WIKI_DATA = ["raw/", "concepts/", "entities/", "comparisons/", "summaries/"]
CONTENT_DATA = [
    "content/sessions/", "content/queue/",
    "content/posted/", "content/rejected/",
]
SCRIPTS = [
    "engine.py", "pipeline.sh", "post.sh", "gates.py",
    "state_machine.py", "wiki-health.py",
]
CONFIG = ["rules.yaml", ".wiki-state", ".content-brief.json"]

WIKI_COLOR = "#1e7d9c"
CONTENT_COLOR = "#2d7d46"
DATA_COLOR = "#b8860b"
SCRIPT_COLOR = "#666666"
CONFIG_COLOR = "#8b5cf6"
GROUP_WIKI = "#1e7d9c20"
GROUP_CONTENT = "#2d7d4620"
CURRENT_COLOR = "#ff6b35"
EDGE_COLOR = "#888888"
FEED_COLOR = "#b8860b"
IDLE_COLOR = "#555555"

CANVAS_WIDTH = 3000
CANVAS_HEIGHT = 1600

STATE_W = 155
STATE_H = 50
DATA_W = 140
DATA_H = 40
SCRIPT_W = 130
SCRIPT_H = 40
CONFIG_W = 140
CONFIG_H = 40

WIKI_X = 80
CONTENT_X = 1050
WIKI_ROW_Y = 120
CONTENT_ROW_Y = 120
CONTENT_ROW2_Y = 200
DATA_Y = 750
SCRIPT_Y = 1000
CONFIG_Y = 1100

COLORS = {
    "INGESTING": WIKI_COLOR,
    "ANALYZING": WIKI_COLOR,
    "RECONCILING": WIKI_COLOR,
    "LINKING": WIKI_COLOR,
    "INDEXING": WIKI_COLOR,
    "VALIDATING": WIKI_COLOR,
    "COMPLETE": WIKI_COLOR,
    "SESSION_CAPTURE": CONTENT_COLOR,
    "STRATEGY_LOAD": CONTENT_COLOR,
    "ICP_WORLD_BUILD": CONTENT_COLOR,
    "DRAFTING": CONTENT_COLOR,
    "GATE_CHECK": CONTENT_COLOR,
    "REVISING": CONTENT_COLOR,
    "QUEUE": CONTENT_COLOR,
    "PUBLISHING": CONTENT_COLOR,
    "ARCHIVING": CONTENT_COLOR,
    "ANALYZING_POST": CONTENT_COLOR,
    "COMPLETE_POST": CONTENT_COLOR,
    "IDLE": IDLE_COLOR,
}


def uid():
    return str(uuid.uuid4())


def text_node(x, y, w, h, text, color=None, bg=None, bold=False):
    n = {
        "id": uid(),
        "x": x, "y": y,
        "width": w, "height": h,
        "type": "text",
        "text": text,
    }
    if color:
        n["color"] = color
    if bg:
        n["backgroundColor"] = bg
    return n


def edge(frm, to, side_from="right", side_to="left", label=None, color=EDGE_COLOR):
    e = {
        "id": uid(),
        "fromNode": frm,
        "fromSide": side_from,
        "toNode": to,
        "toSide": side_to,
        "color": color,
    }
    if label:
        e["label"] = label
    return e


def read_wiki_state() -> dict:
    path = VAULT / ".wiki-state"
    if not path.exists():
        return {"current_state": "IDLE", "loop": "WIKI"}
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
            return data or {}
    except Exception:
        return {"current_state": "IDLE", "loop": "WIKI"}


def read_rules() -> dict:
    path = VAULT / "rules.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def generate():
    state = read_wiki_state()
    rules = read_rules()
    current_state = state.get("current_state", "IDLE")
    current_loop = state.get("loop", "WIKI")
    posting_mode = rules.get("posting", {}).get("mode", "manual")

    nodes = []
    edges_list = []

    # ─── Wiki Loop Group ────────────────────────────────────────────────
    wiki_group_id = uid()
    wiki_group = {
        "id": wiki_group_id,
        "x": 30, "y": 50,
        "width": 870, "height": 720,
        "type": "group",
        "label": "Wiki Loop",
        "backgroundColor": GROUP_WIKI,
    }
    nodes.append(wiki_group)

    # Wiki state nodes in a row
    wiki_ids = {}
    gap = 5
    x = WIKI_X
    for s in WIKI_STATES:
        is_current = (current_state == s and current_loop == "WIKI")
        color = CURRENT_COLOR if is_current else COLORS.get(s, WIKI_COLOR)
        n = text_node(x, WIKI_ROW_Y, STATE_W, STATE_H, s.replace("_", "\n"), color=color)
        n["fontSize"] = 11 if "_" in s else 13
        nodes.append(n)
        wiki_ids[s] = n["id"]
        x += STATE_W + gap

    # IDLE node
    idle_id = None
    if current_state == "IDLE" and current_loop == "WIKI":
        n = text_node(WIKI_X, WIKI_ROW_Y + STATE_H + 15, STATE_W, STATE_H, "IDLE", color=CURRENT_COLOR)
        nodes.append(n)
        idle_id = n["id"]

    # Wiki edges: state transitions
    prev = None
    for s in WIKI_STATES:
        if prev:
            from_side = "bottom" if prev == "RECONCILING" and s == "LINKING" else "right"
            to_side = "top" if prev == "RECONCILING" and s == "LINKING" else "left"
            edges_list.append(edge(wiki_ids[prev], wiki_ids[s], from_side, to_side))
        prev = s

    # Wiki data stores
    dx = WIKI_X
    for ds in WIKI_DATA:
        n = text_node(dx, DATA_Y, DATA_W, DATA_H, ds.strip("/"), color=DATA_COLOR)
        n["fontSize"] = 11
        nodes.append(n)
        dx += DATA_W + 5

    # ─── Content Loop Group ──────────────────────────────────────────────
    content_group_id = uid()
    content_group = {
        "id": content_group_id,
        "x": 1000, "y": 50,
        "width": 1300, "height": 720,
        "type": "group",
        "label": "Content Loop",
        "backgroundColor": GROUP_CONTENT,
    }
    nodes.append(content_group)

    # Content state nodes in two rows
    content_ids = {}
    row1 = CONTENT_STATES[:6]
    row2 = CONTENT_STATES[6:]
    cgap = 5
    cx = CONTENT_X
    for s in row1:
        is_current = (current_state == s and current_loop == "CONTENT")
        color = CURRENT_COLOR if is_current else COLORS.get(s, CONTENT_COLOR)
        n = text_node(cx, CONTENT_ROW_Y, STATE_W, STATE_H, s.replace("_", "\n"), color=color)
        n["fontSize"] = 10 if "_" in s else 13
        nodes.append(n)
        content_ids[s] = n["id"]
        cx += STATE_W + cgap

    cx = CONTENT_X
    for s in row2:
        is_current = (current_state == s and current_loop == "CONTENT")
        color = CURRENT_COLOR if is_current else COLORS.get(s, CONTENT_COLOR)
        n = text_node(cx, CONTENT_ROW2_Y + STATE_H + 10, STATE_W, STATE_H, s.replace("_", "\n"), color=color)
        n["fontSize"] = 10 if "_" in s else 13
        nodes.append(n)
        content_ids[s] = n["id"]
        cx += STATE_W + cgap

    # Content edges
    prev = None
    for s in CONTENT_STATES:
        if prev:
            from_side = "bottom" if prev == "GATE_CHECK" and s == "REVISING" else "right"
            to_side = "top" if prev == "GATE_CHECK" and s == "REVISING" else "left"
            # Handle the row wrap: row1 last -> row2 first
            if prev in row1 and s in row2:
                from_side = "bottom"
                to_side = "top"
            edges_list.append(edge(content_ids[prev], content_ids[s], from_side, to_side))
        prev = s

    # REVISING back to GATE_CHECK
    if "REVISING" in content_ids and "GATE_CHECK" in content_ids:
        edges_list.append(edge(
            content_ids["REVISING"], content_ids["GATE_CHECK"],
            "top", "bottom", label="retry",
            color=FEED_COLOR,
        ))

    # Content data stores
    cdx = CONTENT_X + 40
    for ds in CONTENT_DATA:
        n = text_node(cdx, DATA_Y, DATA_W, DATA_H, ds.strip("/"), color=DATA_COLOR)
        n["fontSize"] = 11
        nodes.append(n)
        cdx += DATA_W + 5

    # ─── Cross-loop feed arrows ─────────────────────────────────────────
    if "CONCEPTS_ANCHOR" in wiki_ids or True:
        # Feed-forward: wiki concepts → content drafting
        wiki_anchor_x = WIKI_X + (len(WIKI_STATES) * (STATE_W + gap)) // 2
        wiki_anchor_y = DATA_Y + DATA_H + 30
        content_anchor_x = CONTENT_X + (len(row1) * (STATE_W + cgap)) // 2
        content_anchor_y = DATA_Y + DATA_H + 30

        ff_node = text_node(
            (WIKI_X + CONTENT_X) // 2 - 60, wiki_anchor_y,
            120, 30, "feed →", color=FEED_COLOR,
        )
        ff_id = ff_node["id"]
        nodes.append(ff_node)

        fb_node = text_node(
            (WIKI_X + CONTENT_X) // 2 - 60, wiki_anchor_y + 40,
            120, 30, "← feedback", color=FEED_COLOR,
        )
        fb_id = fb_node["id"]
        nodes.append(fb_node)

        edges_list.append(edge(wiki_ids["COMPLETE"], ff_id, "bottom", "top", label="knowledge"))
        edges_list.append(edge(ff_id, content_ids["DRAFTING"], "right", "top", label=""))
        edges_list.append(edge(content_ids["ANALYZING_POST"], fb_id, "bottom", "right", label=""))
        edges_list.append(edge(fb_id, wiki_ids["RECONCILING"], "left", "top", label="update"))

    # ─── Scripts ─────────────────────────────────────────────────────────
    sx = (WIKI_X + CONTENT_X) // 2 - 300
    label = text_node(sx - 10, SCRIPT_Y - 35, 80, 24, "Scripts", color=SCRIPT_COLOR)
    label["fontSize"] = 12
    nodes.append(label)

    for sc in SCRIPTS:
        n = text_node(sx, SCRIPT_Y, SCRIPT_W, SCRIPT_H, sc, color=SCRIPT_COLOR)
        n["fontSize"] = 10
        nodes.append(n)
        sx += SCRIPT_W + 5

    # ─── Config ──────────────────────────────────────────────────────────
    cx_conf = (WIKI_X + CONTENT_X) // 2 - 200
    label2 = text_node(cx_conf - 10, CONFIG_Y - 35, 80, 24, "Config", color=CONFIG_COLOR)
    label2["fontSize"] = 12
    nodes.append(label2)

    for cfg in CONFIG:
        n = text_node(cx_conf, CONFIG_Y, CONFIG_W, CONFIG_H, cfg, color=CONFIG_COLOR)
        n["fontSize"] = 10
        nodes.append(n)
        cx_conf += CONFIG_W + 5

    # ─── Status footer ───────────────────────────────────────────────────
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    mode_text = f"State: {current_state} ({current_loop})  |  Mode: {posting_mode}  |  Generated: {now}"
    footer = text_node(20, CANVAS_HEIGHT - 60, 800, 30, mode_text, color="#999999")
    footer["fontSize"] = 12
    nodes.append(footer)

    # ─── Build canvas JSON ───────────────────────────────────────────────
    canvas = {
        "nodes": nodes,
        "edges": edges_list,
    }

    CANVAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANVAS_PATH.write_text(json.dumps(canvas, indent=2))
    print(f"Architecture canvas generated: {CANVAS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(generate())
