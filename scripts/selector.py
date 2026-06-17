#!/usr/bin/env python3
"""selector.py — Template recommendation + format selection (merged).

Pure functions: score templates, select top N, format selection logic.
No CLI, no file I/O. Kernel calls these with data loaded from disk.
"""


def flatten_templates(registry: dict) -> list[dict]:
    templates = []
    platforms = registry.get("platforms", {})
    if not platforms and "platform" in registry:
        plat_id = registry["platform"]
        platforms = {plat_id: {"categories": registry.get("categories", [])}}
    for plat_id, plat_data in platforms.items():
        for cat in plat_data.get("categories", []):
            cat_defaults = cat.get("defaults", {})
            for tmpl in cat.get("templates", []):
                merged = {
                    "id": tmpl["id"],
                    "platform": plat_id,
                    "category": cat["id"],
                    "category_name": cat["name"],
                    "name": tmpl["name"],
                    "hook": tmpl.get("hook", ""),
                    "cta": tmpl.get("cta", ""),
                    "body": tmpl.get("body", cat_defaults.get("body", "")),
                    "psych_triggers": tmpl.get("psych_triggers", cat_defaults.get("psych_triggers", [])),
                    "anti_patterns": tmpl.get("anti_patterns", cat_defaults.get("anti_patterns", [])),
                    "best_for": tmpl.get("best_for", cat_defaults.get("best_for", {})),
                }
                templates.append(merged)
    return templates


def score_template(tmpl: dict, context: dict, weights: dict) -> float:
    bf = tmpl.get("best_for", {})
    score = 0.0
    archetype = context.get("archetype", "")
    if archetype and archetype in bf.get("archetypes", []):
        score += weights.get("archetype", 0.30)
    axis = context.get("meaning_axis", "")
    if axis and axis in bf.get("meaning_axes", []):
        score += weights.get("meaning_axis", 0.25)
    funnel = context.get("funnel_stage", "")
    if funnel and funnel in bf.get("funnel_stages", []):
        score += weights.get("funnel_stage", 0.20)
    layer = context.get("icp_layer", "")
    if layer and layer in bf.get("icp_layers", []):
        score += weights.get("icp_layer", 0.15)
    return score


def select(templates: list[dict], context: dict, weights: dict,
           top_n: int = 5, platform_filter: str = "") -> list[dict]:
    scored = []
    for tmpl in templates:
        if platform_filter and tmpl["platform"] != platform_filter:
            continue
        s = score_template(tmpl, context, weights)
        scored.append({
            "id": tmpl["id"],
            "name": tmpl["name"],
            "platform": tmpl["platform"],
            "category": tmpl["category"],
            "category_name": tmpl["category_name"],
            "score": round(s, 3),
            "hook": tmpl["hook"],
            "cta": tmpl["cta"],
            "body": tmpl["body"],
            "psych_triggers": tmpl["psych_triggers"],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]
