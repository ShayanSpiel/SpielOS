#!/usr/bin/env python3
"""template_selector.py — Heuristic template recommendation engine.

Reads .content-brief.json + runs strategy_classifier to score all templates
from templates/registry/viral-templates.yaml against the current context.

Usage:
    python3 scripts/template_selector.py
    python3 scripts/template_selector.py --platform x
    python3 scripts/template_selector.py --top-n 3

Output: JSON to stdout with ranked recommendations per platform.
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("template_selector.py requires PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

VAULT = Path(__file__).resolve().parent.parent
RULES_FILE = VAULT / "rules.yaml"
BRIEF_FILE = VAULT / ".content-brief.json"
REGISTRY_FILE = VAULT / "templates" / "registry" / "viral-templates.yaml"
CLASSIFIER = VAULT / "scripts" / "strategy_classifier.py"


def load_rules() -> dict:
    with RULES_FILE.open() as f:
        return yaml.safe_load(f) or {}


def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        print("ERROR: Template registry not found", file=sys.stderr)
        sys.exit(1)
    with REGISTRY_FILE.open() as f:
        return yaml.safe_load(f) or {}


def read_brief() -> dict:
    if not BRIEF_FILE.exists():
        return {}
    try:
        return json.loads(BRIEF_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def run_classifier(brief: dict) -> dict:
    """Run strategy_classifier on session log or topic text from brief."""
    result = {
        "archetype": "",
        "archetype_label": "",
        "vertical": "",
        "funnel_stage": "",
        "icp_layer": "",
    }

    session_path = brief.get("session")
    source = brief.get("source", {})
    source_kind = source.get("kind", "")
    source_text = source.get("text", "")

    if source_kind == "topic" and source_text:
        try:
            r = subprocess.run(
                [sys.executable, str(CLASSIFIER), "topic", source_text[:2000]],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                parsed = json.loads(r.stdout)
                result.update(parsed)
        except Exception:
            pass

    elif session_path:
        session_file = Path(session_path)
        if not session_file.is_absolute():
            session_file = VAULT / session_path
        if session_file.exists():
            try:
                r = subprocess.run(
                    [sys.executable, str(CLASSIFIER), "session"],
                    input=session_file.read_text(),
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0:
                    parsed = json.loads(r.stdout)
                    result.update(parsed)
            except Exception:
                pass

    return result


def flatten_templates(registry: dict) -> list[dict]:
    """Flatten the nested template structure into a flat list with inherited defaults.
    Template IDs are already fully qualified in the YAML (e.g. x-listicle-01).
    Supports nested platforms structure: registry['platforms'][plat_id]['categories'].
    """
    templates = []
    platforms = registry.get("platforms", {})
    if not platforms and "platform" in registry:
        # Fallback for flat structure (version < 2)
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
    """Compute a score [0.0, 1.0] for a template against the current context.

    Higher is better. Weights from rules.yaml §template_selector.weights.
    """
    bf = tmpl.get("best_for", {})
    score = 0.0

    # 1. Archetype match
    archetype = context.get("archetype", "")
    if archetype and archetype in bf.get("archetypes", []):
        score += weights.get("archetype", 0.30)

    # 2. Meaning axis match
    axis = context.get("meaning_axis", "")
    if axis and axis in bf.get("meaning_axes", []):
        score += weights.get("meaning_axis", 0.25)

    # 3. Funnel stage match
    funnel = context.get("funnel_stage", "")
    if funnel and funnel in bf.get("funnel_stages", []):
        score += weights.get("funnel_stage", 0.20)

    # 4. ICP layer match
    layer = context.get("icp_layer", "")
    if layer and layer in bf.get("icp_layers", []):
        score += weights.get("icp_layer", 0.15)

    return score


def select(
    templates: list[dict], context: dict, weights: dict, top_n: int = 5, platform_filter: str = ""
) -> list[dict]:
    """Score all templates and return top N sorted by score descending."""
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Template recommendation engine")
    parser.add_argument("--platform", default="", help="Filter to platform (x, linkedin, blog, pillar)")
    parser.add_argument("--top-n", type=int, default=5, help="Number of recommendations per category")
    args = parser.parse_args()

    rules = load_rules()
    selector_cfg = rules.get("template_selector", {})
    if not selector_cfg.get("enabled", True):
        print(json.dumps({"status": "disabled", "recommendations": {}}))
        return 0

    weights = selector_cfg.get("weights", {
        "archetype": 0.30,
        "meaning_axis": 0.25,
        "funnel_stage": 0.20,
        "icp_layer": 0.15,
    })

    top_n = selector_cfg.get("top_n", {})

    brief = read_brief()
    if not brief:
        print(json.dumps({"status": "no_brief", "error": "No .content-brief.json found", "recommendations": {}}))
        return 1

    registry = load_registry()
    all_templates = flatten_templates(registry)

    context = run_classifier(brief)
    context["meaning_axis"] = brief.get("selected_meaning", {}).get("axis", "")
    context["core_insight"] = brief.get("core_insight", "")

    if not context.get("archetype"):
        print(json.dumps({
            "status": "no_classification",
            "error": "Could not classify session/topic — archetype required for template selection",
            "context": context,
            "recommendations": {},
        }))
        return 1

    recommendations = {}
    if args.platform:
        platform_top_n = top_n.get(args.platform, args.top_n)
        recs = select(all_templates, context, weights, top_n=platform_top_n, platform_filter=args.platform)
        if recs:
            recommendations[args.platform] = recs
    else:
        for plat in sorted(set(t["platform"] for t in all_templates)):
            plat_top_n = top_n.get(plat, args.top_n)
            recs = select(all_templates, context, weights, top_n=plat_top_n, platform_filter=plat)
            if recs:
                recommendations[plat] = recs

    output = {
        "status": "ok",
        "context": {
            "archetype": context.get("archetype", ""),
            "archetype_label": context.get("archetype_label", ""),
            "meaning_axis": context.get("meaning_axis", ""),
            "funnel_stage": context.get("funnel_stage", ""),
            "icp_layer": context.get("icp_layer", ""),
            "core_insight": context.get("core_insight", "")[:120],
        },
        "recommendations": recommendations,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
