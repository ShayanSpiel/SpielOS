#!/usr/bin/env python3
"""classifier.py — Heuristic session/topic classifier.

ALL keyword rules come from rules.yaml via Config.
Usage: from classifier import classify
"""


def best_match(text: str, candidates: dict) -> tuple[str, str]:
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


def classify(text: str, rules: dict) -> dict:
    strategy = rules.get("strategy", {})
    arch_key, arch_label = best_match(text, strategy.get("archetypes", {}))
    vert_key, vert_label = best_match(text, strategy.get("verticals", {}))
    funnel_key, _ = best_match(text, strategy.get("funnel_stages", {}))
    layer_key, _ = best_match(text, strategy.get("icp_layers", {}))
    return {
        "archetype": arch_key or "",
        "archetype_label": arch_label or "",
        "vertical": vert_key or "",
        "funnel_stage": funnel_key or "",
        "icp_layer": layer_key or "",
    }
