#!/usr/bin/env python3
"""apply-scene-timing.py — Rewrites the video templates' tick() scene switches
to the MEASURED Gemini narration schedule in narration.json scene_timing.

Keeps the original internal stagger offsets per scene, so animation pacing
relative to each scene start is preserved. Safe to re-run: it reads only the
schedule and the current template state.

Usage: python3 scripts/apply-scene-timing.py
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
NARRATION = ROOT / "company/departments/design/templates/video/narration.json"
cfg = json.loads(NARRATION.read_text())
alt = []
print(f"Using scene_timing from {NARRATION}")

def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")

for scenario, file, old_starts, pattern in [
    ("b", "scenario-b.html",
     [0.00, 2.34, 6.49, 8.56, 10.88, 12.60],
     # (label, relative offsets for inner toggles, extra cta pattern)
     None),
    ("c", "scenario-c.html",
     [0.00, 3.10, 8.41, 10.52, 12.44, 12.44],
     None),
]:
    timing = cfg.get("scene_timing", {}).get(scenario, {}).get("scenes")
    if not timing:
        print(f"!! no scene_timing for {scenario}")
        sys.exit(1)
    starts = [s["start"] for s in timing]
    path = ROOT / "company/departments/design/templates/video" / file
    src = path.read_text()

    # 1) Comments block
    if scenario == "b":
        labels = ["Hook", "Pain cards", "Promise", "Pillars", "Director", "CTA"]
    else:
        labels = ["Hook", "Build steps", '"Live"', "Director", "CTA"]
    starts_p = starts + [15.0]
    new_comment = "\n".join(
        f"  {fmt(starts_p[i]) if i else '0'}-{fmt(starts_p[i+1])}s: {labels[i]}"
        for i in range(len(labels)))
    src = re.sub(r"  (0-\d+\.?\d*s[^\n]*\n)+", new_comment + "\n", src, count=1)

    # 2) Scene switch chain — rebuild from start map with fixed relative offsets
    if scenario == "b":
        # rel offsets from the original (verified above)
        rel = {
            0: [("hi1", 0.20), ("h1", 0.40), ("h2", 0.90), ("h3", 1.40), ("h4", 2.00)],
            1: [("pi", 0.30, "i*0.4")],   # pi{i} at rel + i*0.4
            2: [("pri1", 0.10), ("pr1", 0.30), ("pr2", 0.80), ("pr3", 1.40)],
            3: [("pl0", 0.00), ("pl", 0.30, "j*0.25")],
            4: [("di1", 0.00), ("d1", 0.20), ("d2", 0.50), ("d3", 0.80)],
            5: [("ct0", 0.00), ("ct1", 0.15), ("ct2", 0.35)],
        }
        chains = []
        for i, s in enumerate(starts):
            nxt = starts[i+1] if i + 1 < len(starts) else 15.0
            togs = []
            for item in rel[i]:
                if len(item) == 2:
                    togs.append(f"tog('{item[0]}',t>{fmt(s + item[1])})")
                else:
                    name, base, expr = item
                    togs.append(f"for(var {expr[0]}i=0;{expr[0]}i<5;{expr[0]}i++)tog('{name}'+{expr[0]}i,t>{fmt(s + base)}+{expr[0]}i*0.4)")
            if i == 0:
                cond = f"t<{fmt(nxt)}"
            elif i == len(starts) - 1:
                cond = f"t>={fmt(s)}"
            else:
                cond = f"t>={fmt(s)}&&t<{fmt(nxt)}"
            chains.append(f"  if({cond}){{act('s{i+1}');{' '.join(togs)}}}")
        # s1 hook-specific inner ids (hi1/h1... same as rel[0]) are generic enough.
        # fix s1 uses hi1..h4: handles fine. Rebuild fully.
        src = re.sub(r"  if\(t<[\d.]+\)\{act\('s1'\).*\n", chains[0] + "\n", src, count=1)
        src = re.sub(r"  if\(t>=[\d.]+&&t<[\d.]+\)\{act\('s2'\).*\n", chains[1] + "\n", src, count=1)
        src = re.sub(r"  if\(t>=[\d.]+&&t<[\d.]+\)\{act\('s3'\).*\n", chains[2] + "\n", src, count=1)
        src = re.sub(r"  if\(t>=[\d.]+&&t<[\d.]+\)\{act\('s4'\).*\n", chains[3] + "\n", src, count=1)
        src = re.sub(r"  if\(t>=[\d.]+&&t<[\d.]+\)\{act\('s5'\).*\n", chains[4] + "\n", src, count=1)
        src = re.sub(r"  if\(t>=[\d.]+\)\{act\('s6'\).*\n", chains[5] + "\n", src, count=1)
        # stationTimes + goal show
        src = re.sub(r"var stationTimes=\[[^\]]+\];",
                     "var stationTimes=[" + ",".join(fmt(x) for x in starts) + "];", src, count=1)
        src = re.sub(r"classList\.toggle\('show',t>=12\.9\)",
                     f"classList.toggle('show',t>={fmt(starts[-1] + 0.3)})", src, count=1)
    else:
        rel = {
            0: [("h1", 0.30), ("h2", 0.80)],
            1: [("bs", 0.30, "i*0.8")],
            2: [("l1", 0.10), ("l2", 0.50)],
            3: [("dc1", 0.10), ("dc-0", 0.50), ("dc-1", 1.00)],
            4: [("ct0", 0.00), ("ct1", 0.15), ("ct2", 0.35)],
        }
        chains = []
        for i, s in enumerate(starts):
            nxt = starts[i+1] if i + 1 < len(starts) else 15.0
            togs = []
            for item in rel[i]:
                if len(item) == 2:
                    togs.append(f"tog('{item[0]}',t>{fmt(s + item[1])})")
                else:
                    name, base, expr = item
                    togs.append(f"for(var {expr[0]}i=0;{expr[0]}i<4;{expr[0]}i++)tog('{name}'+{expr[0]}i,t>{fmt(s + base)}+{expr[0]}i*0.8)")
            if i == 0:
                cond = f"t<{fmt(nxt)}"
            elif i == len(starts) - 1:
                cond = f"t>={fmt(s)}"
            else:
                cond = f"t>={fmt(s)}&&t<{fmt(nxt)}"
            chains.append(f"  if({cond}){{act('s{i+1}');{' '.join(togs)}}}")
        for i in range(5):
            src = re.sub(rf"  if\([^)]*\)\{{act\('s{i+1}'\).*\n", chains[i] + "\n", src, count=1)
        src = re.sub(r"classList\.toggle\('show',t>12\.6\)",
                     f"classList.toggle('show',t>={fmt(starts[-1] + 0.25)})", src, count=1)
        src = re.sub(r"classList\.toggle\('show',t>={fmt(starts[-1] + 0.25)}\)",
                     f"classList.toggle('show',t>={fmt(starts[-1] + 0.25)})", src, count=1)

    path.write_text(src)
    print(f"  {file}: scenes re-timed to starts {[fmt(x) for x in starts]}")
