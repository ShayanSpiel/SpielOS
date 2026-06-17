#!/usr/bin/env python3
"""template_ranker.py — Score and curate the template registry.

Reads templates/registry/viral-templates.yaml (or any structured YAML with
the same shape). For each template, computes a composite score from:
  - substance:     how much non-slot, non-trivial content in the hook/CTA
  - archetype:     breadth of archetype coverage in best_for.archetypes
  - psych_match:   how well psych_triggers align with funnel_stages
  - anti_density:  how many anti_patterns the template declares
  - engagement:    (when N>=5 posts available) avg engagement rate

Outputs:
  - templates/registry/_archive/viral-templates.yaml.<timestamp>  (full snapshot)
  - templates/registry/performance.json                            (engagement data)
  - templates/registry/curated/{platform}-{cat}-top10.yaml         (per-category slim)
  - templates/registry/rank-history.jsonl                          (per-run audit log)

Pure-ish: file I/O is the point. No CLI. No LLM.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from engine_state import VAULT


DEFAULT_WEIGHTS = {
    "substance":       0.30,
    "archetype":       0.20,
    "psych_match":     0.20,
    "anti_density":    0.15,
    "engagement":      0.15,
}

ENGAGEMENT_BOOST_THRESHOLD = 5
ENGAGEMENT_BOOST_WEIGHT = 0.35
ENGAGEMENT_BASE_WEIGHT = 0.10


_SLOT_PATTERN = re.compile(r"\{[a-z_][a-z0-9_]*\}")


def _substance_score(template: dict) -> float:
    """Score the substance of hook + cta. Higher = more actual content, fewer slots."""
    hook = (template.get("hook") or "").strip()
    cta = (template.get("cta") or "").strip()
    if not hook:
        return 0.0
    hook_slots = len(_SLOT_PATTERN.findall(hook))
    hook_tokens = len(hook.split())
    cta_slots = len(_SLOT_PATTERN.findall(cta))
    cta_tokens = len(cta.split())
    total_tokens = hook_tokens + cta_tokens
    total_slots = hook_slots + cta_slots
    if total_tokens == 0:
        return 0.0
    slot_ratio = total_slots / total_tokens
    substance = max(0.0, min(1.0, 1.0 - slot_ratio))
    length_bonus = min(0.3, total_tokens / 50.0)
    return min(1.0, substance * 0.7 + length_bonus)


def _archetype_breadth(template: dict) -> float:
    bf = template.get("best_for") or {}
    archetypes = bf.get("archetypes") or []
    axes = bf.get("meaning_axes") or []
    stages = bf.get("funnel_stages") or []
    layers = bf.get("icp_layers") or []
    score = 0.0
    score += min(0.4, len(archetypes) * 0.10)
    score += min(0.25, len(axes) * 0.08)
    score += min(0.20, len(stages) * 0.10)
    score += min(0.15, len(layers) * 0.08)
    return min(1.0, score)


def _psych_match_score(template: dict) -> float:
    triggers = template.get("psych_triggers") or []
    if not triggers:
        return 0.0
    score = min(1.0, len(triggers) * 0.25)
    if "fear" in triggers or "anger" in triggers:
        score += 0.1
    if "curiosity" in triggers or "greed" in triggers:
        score += 0.1
    return min(1.0, score)


def _anti_density_penalty(template: dict) -> float:
    anti = template.get("anti_patterns") or []
    return min(1.0, len(anti) * 0.3)


def _engagement_score(template_id: str, performance: dict) -> tuple[float, int]:
    """Returns (score, post_count). score is 0 if no data."""
    entry = performance.get(template_id)
    if not entry or not isinstance(entry, dict):
        return 0.0, 0
    n = int(entry.get("posts", 0) or 0)
    if n == 0:
        return 0.0, 0
    rate = float(entry.get("avg_rate", 0.0) or 0.0)
    last_30d = float(entry.get("last_30d_rate", rate) or 0.0)
    combined = (rate * 0.4) + (last_30d * 0.6)
    return min(1.0, combined * 50.0), n


def score_template(
    template: dict,
    performance: dict | None = None,
    weights: dict | None = None,
    category_priors: dict | None = None,
) -> dict:
    """Score a single template. Returns {id, score, components}."""
    weights = weights or DEFAULT_WEIGHTS
    performance = performance or {}
    category_priors = category_priors or {}
    sub = _substance_score(template)
    arc = _archetype_breadth(template)
    psy = _psych_match_score(template)
    anti = _anti_density_penalty(template)
    eng, n_posts = _engagement_score(template.get("id", ""), performance)
    if n_posts >= ENGAGEMENT_BOOST_THRESHOLD:
        w_eng = ENGAGEMENT_BOOST_WEIGHT
    else:
        w_eng = ENGAGEMENT_BASE_WEIGHT
    others = {
        "substance":    weights["substance"] * sub,
        "archetype":    weights["archetype"] * arc,
        "psych_match":  weights["psych_match"] * psy,
        "anti_density": weights["anti_density"] * (1.0 - anti),
    }
    base_total = sum(others.values())
    total_weights = (weights["substance"] + weights["archetype"] +
                     weights["psych_match"] + weights["anti_density"])
    if total_weights > 0 and w_eng < 1.0:
        scale = (1.0 - w_eng) / total_weights
    else:
        scale = 0.0
    base_total = base_total * scale
    final = base_total + w_eng * eng
    prior_multiplier = _category_prior_multiplier(template, category_priors)
    final = final * prior_multiplier
    return {
        "id":         template.get("id", ""),
        "name":       template.get("name", ""),
        "platform":   template.get("platform", ""),
        "category":   template.get("category", ""),
        "score":      round(final, 4),
        "components": {
            "substance":    round(sub, 3),
            "archetype":    round(arc, 3),
            "psych_match":  round(psy, 3),
            "anti_density": round(anti, 3),
            "engagement":   round(eng, 3),
            "n_posts":      n_posts,
        },
        "weights_used": {
            "substance":    round(weights["substance"] * scale, 3) if scale else 0,
            "archetype":    round(weights["archetype"] * scale, 3) if scale else 0,
            "psych_match":  round(weights["psych_match"] * scale, 3) if scale else 0,
            "anti_density": round(weights["anti_density"] * scale, 3) if scale else 0,
            "engagement":   w_eng,
        },
        "prior_multiplier": prior_multiplier,
    }


def rank_all(
    registry: dict,
    performance: dict | None = None,
    weights: dict | None = None,
    category_priors: dict | None = None,
) -> list[dict]:
    """Rank all templates across all platforms/categories."""
    performance = performance or {}
    weights = weights or DEFAULT_WEIGHTS
    category_priors = category_priors or {}
    results: list[dict] = []
    for plat_id, plat_data in (registry.get("platforms") or {}).items():
        for cat in plat_data.get("categories") or []:
            cat_defaults = cat.get("defaults", {})
            for tmpl in cat.get("templates") or []:
                merged = {**cat_defaults, **tmpl}
                merged["platform"] = plat_id
                merged["category"] = cat.get("id", "")
                merged["category_name"] = cat.get("name", "")
                results.append(score_template(merged, performance, weights, category_priors))
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def _category_prior_multiplier(template: dict, category_priors: dict) -> float:
    """Apply category_priors multiplier if template's category has a prior."""
    cat_id = template.get("category", "")
    prior = category_priors.get(cat_id)
    if not prior:
        return 1.0
    return float(prior.get("multiplier", 1.0))


def curate_top_n(
    registry: dict,
    ranked: list[dict],
    top_n: int = 10,
) -> dict:
    """Build a new registry containing only the top N templates per category.

    Returns a new dict with the same shape as the input.
    """
    keep_ids: set[str] = set()
    by_cat: dict[tuple, list[dict]] = defaultdict(list)
    for r in ranked:
        by_cat[(r["platform"], r["category"])].append(r)
    for key, items in by_cat.items():
        items.sort(key=lambda r: r["score"], reverse=True)
        for r in items[:top_n]:
            keep_ids.add(r["id"])
    out: dict = {"version": 1, "platforms": {}}
    for plat_id, plat_data in (registry.get("platforms") or {}).items():
        out["platforms"][plat_id] = {"categories": []}
        for cat in plat_data.get("categories") or []:
            new_cat = {
                "id": cat.get("id"),
                "name": cat.get("name"),
                "defaults": cat.get("defaults", {}),
                "templates": [
                    t for t in cat.get("templates", [])
                    if t.get("id") in keep_ids
                ],
            }
            out["platforms"][plat_id]["categories"].append(new_cat)
    return out


def load_registry(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def load_performance(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def append_history(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def archive_originals(registry_path: Path, archive_dir: Path) -> Path:
    """Copy registry to archive dir with timestamp. Returns the archived path."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = archive_dir / f"viral-templates.{ts}.yaml"
    shutil.copy2(registry_path, target)
    return target


def run(
    registry_path: Path | None = None,
    archive_dir: Path | None = None,
    curated_dir: Path | None = None,
    perf_path: Path | None = None,
    history_path: Path | None = None,
    top_n: int = 10,
    weights: dict | None = None,
    category_priors: dict | None = None,
) -> dict:
    """Run the full rank + curate + archive pipeline.

    Returns a summary dict with all the paths written.
    """
    registry_path = registry_path or (VAULT / "templates" / "registry" / "viral-templates.yaml")
    archive_dir = archive_dir or (VAULT / "templates" / "registry" / "_archive")
    curated_dir = curated_dir or (VAULT / "templates" / "registry" / "curated")
    perf_path = perf_path or (VAULT / "templates" / "registry" / "performance.json")
    history_path = history_path or (VAULT / "templates" / "registry" / "rank-history.jsonl")
    if not registry_path.exists():
        return {"ok": False, "reason": f"registry not found: {registry_path}"}
    registry = load_registry(registry_path)
    performance = load_performance(perf_path)
    if category_priors is None:
        try:
            from engine_config import config
            category_priors = config.category_priors
        except Exception:
            category_priors = {}
    ranked = rank_all(registry, performance, weights, category_priors)
    curated = curate_top_n(registry, ranked, top_n=top_n)
    archived = archive_originals(registry_path, archive_dir)
    write_yaml(curated_dir / "viral-templates.top.yaml", curated)
    append_history(history_path, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "registry": str(registry_path),
        "archive": str(archived),
        "n_ranked": len(ranked),
        "n_kept": sum(len(cat.get("templates") or []) for plat in curated.get("platforms", {}).values() for cat in plat.get("categories") or []),
        "top_n": top_n,
        "weights": weights or DEFAULT_WEIGHTS,
        "category_priors": category_priors,
        "top_10_ids": [r["id"] for r in ranked[:10]],
    })
    return {
        "ok": True,
        "registry": str(registry_path),
        "archive": str(archived),
        "curated": str(curated_dir / "viral-templates.top.yaml"),
        "n_ranked": len(ranked),
        "n_kept": sum(len(cat.get("templates") or []) for plat in curated.get("platforms", {}).values() for cat in plat.get("categories") or []),
        "ranked": ranked,
    }


def main():
    import argparse
    p = argparse.ArgumentParser(prog="template_ranker.py")
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--registry", type=Path, default=None)
    p.add_argument("--archive-dir", type=Path, default=None)
    p.add_argument("--curated-dir", type=Path, default=None)
    p.add_argument("--performance", type=Path, default=None)
    p.add_argument("--history", type=Path, default=None)
    args = p.parse_args()
    result = run(
        registry_path=args.registry,
        archive_dir=args.archive_dir,
        curated_dir=args.curated_dir,
        perf_path=args.performance,
        history_path=args.history,
        top_n=args.top_n,
    )
    if not result.get("ok"):
        print(f"ERROR: {result.get('reason')}", file=sys.stderr)
        return 1
    print(f"  ranked:   {result['n_ranked']}")
    print(f"  kept:     {result['n_kept']}")
    print(f"  archive:  {result['archive']}")
    print(f"  curated:  {result['curated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
