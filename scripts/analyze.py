#!/usr/bin/env python3
"""analyze.py — Pull engagement from Buffer, update performance.json, re-rank.

For each posted draft with buffer_post_ids in frontmatter:
  1. Call Buffer API to get current engagement
  2. Update the draft's frontmatter `engagement:` field
  3. Update performance.json with the latest metrics
  4. Re-run template_ranker to update curated/ outputs

The performance.json is the source of truth for engagement data, used by
template_ranker.score_template to weight recommendations.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import buffer_client
import engine_state
from engine_frontmatter import parse_frontmatter, write_frontmatter
from engine_serial import log, log_err
import template_ranker


_PERF_PATH = Path(engine_state.VAULT) / "templates" / "registry" / "performance.json"


def _load_perf() -> dict:
    if not _PERF_PATH.exists():
        return {"templates": {}, "by_template": {}, "by_id": {}, "history": []}
    try:
        return json.loads(_PERF_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"templates": {}, "by_template": {}, "by_id": {}, "history": []}


def _save_perf(perf: dict) -> None:
    _PERF_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PERF_PATH.write_text(json.dumps(perf, indent=2, default=str))


def _template_id_of(draft_path: Path) -> str:
    try:
        text = draft_path.read_text()
        fm, _ = parse_frontmatter(text)
    except (OSError, ValueError):
        return ""
    if not fm:
        return ""
    return str(fm.get("template_id") or "")


def _looks_like_posted(draft_path: Path) -> bool:
    try:
        text = draft_path.read_text()
        fm, _ = parse_frontmatter(text)
    except (OSError, ValueError):
        return False
    if not fm:
        return False
    return bool(fm.get("posted_at")) and bool(fm.get("platform"))


def _platform_per_post_ids(fm: dict) -> dict[str, str]:
    """Extract {service: buffer_update_id} from frontmatter."""
    out: dict[str, str] = {}
    buf_ids = fm.get("buffer_post_ids") or {}
    if isinstance(buf_ids, dict):
        for service, pid in buf_ids.items():
            if pid:
                out[service] = str(pid)
    return out


def analyze_one(
    draft_path: Path,
    token: str,
    perf: dict,
    *,
    dry_run: bool = False,
) -> dict:
    """Pull engagement for a single draft, update its frontmatter and perf.

    Returns a result dict with {ok, engagement, updated, error}.
    """
    try:
        text = draft_path.read_text()
        fm, body = parse_frontmatter(text)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"read failed: {e}"}
    if not fm:
        return {"ok": False, "error": "no frontmatter"}
    if not fm.get("posted_at"):
        return {"ok": False, "error": "not posted yet (no posted_at)"}
    post_ids = _platform_per_post_ids(fm)
    if not post_ids:
        return {"ok": False, "error": "no buffer_post_ids in frontmatter"}
    if dry_run:
        return {"ok": True, "dry_run": True, "post_ids": post_ids}
    fetched = buffer_client.fetch_for_post(token, post_ids)
    engagement = fetched.get("aggregate") or {}
    if not engagement:
        return {"ok": False, "error": "Buffer returned no engagement", "fetched": fetched}
    now_iso = datetime.now().isoformat(timespec="seconds")
    fm["engagement"] = {
        **engagement,
        "fetched_at": now_iso,
        "per_platform": fetched.get("per_platform", {}),
    }
    if not dry_run:
        try:
            write_frontmatter(draft_path, fm, body)
        except Exception as e:
            return {"ok": False, "error": f"frontmatter write failed: {e}"}
    template_id = _template_id_of(draft_path)
    if template_id:
        perf.setdefault("by_template", {}).setdefault(template_id, {
            "posts": 0,
            "total_reactions": 0,
            "total_comments": 0,
            "total_reposts": 0,
            "total_impressions": 0,
            "total_engagements": 0,
            "rates": [],
            "last_30d_rates": [],
            "platforms": {},
        })
        entry = perf["by_template"][template_id]
        entry["posts"] = entry.get("posts", 0) + 1
        entry["total_reactions"] = entry.get("total_reactions", 0) + int(engagement.get("reactions", 0))
        entry["total_comments"] = entry.get("total_comments", 0) + int(engagement.get("comments", 0))
        entry["total_reposts"] = entry.get("total_reposts", 0) + int(engagement.get("reposts", 0))
        entry["total_impressions"] = entry.get("total_impressions", 0) + int(engagement.get("impressions", 0))
        entry["total_engagements"] = entry.get("total_engagements", 0) + int(engagement.get("engagements", 0))
        rate = float(engagement.get("rate", 0.0))
        entry.setdefault("rates", []).append(rate)
        entry.setdefault("last_30d_rates", []).append(rate)
        posts = max(1, entry.get("posts", 1))
        entry["avg_rate"] = entry.get("total_engagements", 0) / max(1, entry.get("total_impressions", 0))
        entry["last_30d_rate"] = sum(entry.get("last_30d_rates", [])[-30:]) / max(1, len(entry.get("last_30d_rates", [])[-30:]))
        entry["platforms"][fm.get("platform", "x")] = entry["platforms"].get(fm.get("platform", "x"), 0) + 1
        perf.setdefault("by_id", {}).setdefault(draft_path.stem, {
            "template_id": template_id,
            "engagement": engagement,
            "fetched_at": now_iso,
        })
    perf.setdefault("history", []).append({
        "timestamp": now_iso,
        "draft": str(draft_path),
        "template_id": template_id,
        "engagement": engagement,
    })
    return {
        "ok": True,
        "engagement": engagement,
        "updated": not dry_run,
        "template_id": template_id,
    }


def normalize_perf(perf: dict) -> dict:
    """Convert perf['by_template'] to the flat {template_id: {posts, avg_rate, ...}}
    format that template_ranker.score_template expects.
    """
    flat = {}
    for tmpl_id, entry in (perf.get("by_template") or {}).items():
        if not isinstance(entry, dict):
            continue
        total_impressions = int(entry.get("total_impressions", 0) or 0)
        total_engagements = int(entry.get("total_engagements", 0) or 0)
        avg_rate = entry.get("avg_rate")
        if avg_rate is None and total_impressions > 0:
            avg_rate = total_engagements / total_impressions
        last_30d = entry.get("last_30d_rate")
        if last_30d is None:
            rates = entry.get("rates") or []
            if rates:
                last_30d = sum(rates[-30:]) / len(rates[-30:])
        flat[tmpl_id] = {
            "posts": int(entry.get("posts", 0) or 0),
            "avg_rate": float(avg_rate or 0.0),
            "last_30d_rate": float(last_30d or 0.0),
            "total_impressions": total_impressions,
            "total_engagements": total_engagements,
        }
    return flat


def analyze_all(
    posted_dir: Path | None = None,
    *,
    dry_run: bool = False,
    token: str | None = None,
    re_rank: bool = True,
) -> dict:
    """Pull engagement for all posted drafts. Update perf.json. Optionally re-rank."""
    posted_dir = posted_dir or engine_state.POSTED_DIR
    if token is None:
        cfg = buffer_client.load_config()
        token = cfg.get("BUFFER_ACCESS_TOKEN")
    if not token:
        return {"ok": False, "reason": "no BUFFER_ACCESS_TOKEN", "skipped": True}
    perf = _load_perf()
    if not posted_dir.exists():
        return {"ok": False, "reason": f"posted dir not found: {posted_dir}"}
    summary = {
        "ok": True,
        "analyzed": 0,
        "skipped_no_postids": 0,
        "skipped_not_posted": 0,
        "errors": [],
        "re_ranked": False,
    }
    for d in sorted(posted_dir.glob("*.md")):
        if not _looks_like_posted(d):
            summary["skipped_not_posted"] += 1
            continue
        result = analyze_one(d, token, perf, dry_run=dry_run)
        if result.get("ok"):
            summary["analyzed"] += 1
        elif "no buffer_post_ids" in (result.get("error") or ""):
            summary["skipped_no_postids"] += 1
        else:
            summary["errors"].append((d.name, result.get("error")))
    if not dry_run:
        _save_perf(perf)
    if re_rank and not dry_run:
        rank_result = template_ranker.run(perf_path=_PERF_PATH)
        summary["re_ranked"] = rank_result.get("ok", False)
        summary["ranked_count"] = rank_result.get("n_ranked", 0)
    return summary


def main():
    import argparse
    p = argparse.ArgumentParser(prog="analyze.py")
    p.add_argument("--posted-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-rerank", action="store_true")
    args = p.parse_args()
    summary = analyze_all(
        posted_dir=args.posted_dir,
        dry_run=args.dry_run,
        re_rank=not args.no_rerank,
    )
    if not summary.get("ok"):
        print(f"ERROR: {summary.get('reason')}", file=sys.stderr)
        return 1
    print(f"  analyzed:           {summary['analyzed']}")
    print(f"  skipped_no_postids: {summary['skipped_no_postids']}")
    print(f"  skipped_not_posted: {summary['skipped_not_posted']}")
    print(f"  errors:             {len(summary['errors'])}")
    if summary.get("re_ranked"):
        print(f"  re-ranked:          {summary.get('ranked_count', 0)} templates")
    for name, err in summary["errors"][:5]:
        print(f"    {name}: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
