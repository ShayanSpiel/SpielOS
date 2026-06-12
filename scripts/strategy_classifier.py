#!/usr/bin/env python3
"""strategy_classifier.py — Heuristic session/topic classifier.

ALL keyword rules come from rules.yaml under `strategy.*`.
To add archetypes, keywords, or verticals — edit rules.yaml, not this file.

Usage:
    python3 scripts/strategy_classifier.py session < content/sessions/...md
    python3 scripts/strategy_classifier.py topic "your topic text"
"""

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("strategy_classifier.py requires PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

VAULT = Path(__file__).resolve().parent.parent
RULES_FILE = VAULT / "rules.yaml"


def load_rules() -> dict:
    with RULES_FILE.open() as f:
        return yaml.safe_load(f) or {}


def best_match(text: str, candidates: dict) -> tuple[str, str]:
    """Return (key, label) with highest keyword match count."""
    lower = text.lower()
    best_key = list(candidates.keys())[0] if candidates else "unknown"
    best_label = best_key.split("_", 1)[1] if "_" in best_key else best_key
    best_score = 0
    for key, keywords in candidates.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            parts = key.split("_", 1)
            best_key = parts[0]
            best_label = parts[1] if len(parts) > 1 else key
    return best_key, best_label


def classify(text: str) -> dict:
    rules = load_rules()
    strategy = rules.get("strategy", {})

    arch_key, arch_label = best_match(text, strategy.get("archetypes", {}))
    vert_key, vert_label = best_match(text, strategy.get("verticals", {}))
    funnel_key, _ = best_match(text, strategy.get("funnel_stages", {}))
    layer_key, _ = best_match(text, strategy.get("icp_layers", {}))

    if not arch_key:
        raise ValueError("No archetype keywords matched — session text may be empty or out-of-domain")
    if not funnel_key:
        raise ValueError("No funnel stage keywords matched")
    return {
        "archetype": arch_key,
        "archetype_label": arch_label,
        "vertical": vert_key or "",
        "funnel_stage": funnel_key,
        "icp_layer": layer_key or "",
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: strategy_classifier.py session|topic [text]", file=sys.stderr)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "session":
        text = sys.stdin.read()
    elif mode == "topic":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    else:
        print(f"Unknown mode: {mode}", file=sys.stderr)
        sys.exit(1)

    result = classify(text)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
