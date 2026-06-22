#!/usr/bin/env python3
"""analyst.py — Analyst role tool. Pulls engagement, updates perf ledger, re-ranks templates.

The Analyst subagent uses this to:

1. Pull engagement (views, likes, replies, reposts) for a posted draft.
2. Update `templates/registry/performance.json` with the new metrics.
3. Re-rank `templates/registry/viral-templates.yaml` (recommendations only, not content).
4. Append a row to `templates/registry/rank-history.jsonl`.

CLI:
    python3 tools/analyst.py pull --draft <path>
    python3 tools/analyst.py pull-all --since 24h
    python3 tools/analyst.py rerank
    python3 tools/analyst.py report --platform x --days 30

Output: JSON to stdout, human summary to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# ─── Vault detection ─────────────────────────────────────────────────────

def find_vault() -> Path:
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / "team" / "md.md").exists() and (p / "system" / "state-machine.md").exists():
            return p
    home_vault = Path.home() / ".spiel"
    if (home_vault / "team" / "md.md").exists():
        return home_vault
    import os
    env_vault = os.environ.get("VAULT_DIR")
    if env_vault:
        return Path(env_vault)
    return cwd


VAULT = find_vault()
PERF_FILE = VAULT / "templates" / "registry" / "performance.json"
RANK_HISTORY = VAULT / "templates" / "registry" / "rank-history.jsonl"
TEMPLATES_FILE = VAULT / "templates" / "registry" / "viral-templates.yaml"


# ─── Frontmatter parser (standalone) ─────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2]
    fm = {}
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        for line in fm_text.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm if isinstance(fm, dict) else {}, body


# ─── Buffer API engagement pull ──────────────────────────────────────────

BUFFER_API_URL = "https://api.buffer.com"


def load_buffer_token() -> str | None:
    env_file = VAULT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("BUFFER_ACCESS_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def buffer_request(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        BUFFER_API_URL, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")[:300] if hasattr(e, 'read') else ""
        raise RuntimeError(f"Buffer API HTTP {e.code}: {err}") from e


def pull_buffer_engagement(update_id: str, token: str) -> dict:
    """Fetch engagement metrics for a Buffer post."""
    query = """
    query PostStats($id: ID!) {
      post(id: $id) {
        statistics { reach engagement clicks }
      }
    }
    """
    try:
        data = buffer_request(query, {"id": update_id}, token)
        stats = ((data.get("data") or {}).get("post") or {}).get("statistics") or {}
        return {
            "views": int(stats.get("reach") or 0),
            "likes": 0,  # Buffer doesn't break out likes
            "replies": 0,
            "reposts": 0,
            "engagement_total": int(stats.get("engagement") or 0),
            "clicks": int(stats.get("clicks") or 0),
        }
    except Exception as e:
        return {"views": 0, "likes": 0, "replies": 0, "reposts": 0, "error": str(e)}


# ─── Perf ledger I/O ─────────────────────────────────────────────────────

def load_perf() -> dict:
    if not PERF_FILE.exists():
        return {"templates": {}, "last_updated": None}
    try:
        import yaml
        text = PERF_FILE.read_text(encoding="utf-8")
        if text.strip().startswith("{"):
            return json.loads(text)
        return yaml.safe_load(text) or {"templates": {}}
    except Exception:
        return {"templates": {}, "last_updated": None}


def save_perf(perf: dict) -> None:
    PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
    perf["last_updated"] = datetime.now().isoformat(timespec="seconds")
    PERF_FILE.write_text(json.dumps(perf, indent=2), encoding="utf-8")


def update_perf(perf: dict, template_id: str, engagement: dict) -> None:
    """Update the perf ledger for one template, one observation."""
    t = perf.setdefault("templates", {}).setdefault(template_id, {
        "uses": 0,
        "total_views": 0,
        "total_likes": 0,
        "total_replies": 0,
        "total_reposts": 0,
        "avg_views": 0,
        "avg_likes": 0,
        "avg_replies": 0,
        "avg_reposts": 0,
        "score": 0.0,
    })
    t["uses"] = t.get("uses", 0) + 1
    for k in ("views", "likes", "replies", "reposts"):
        tk = f"total_{k}"
        ak = f"avg_{k}"
        t[tk] = t.get(tk, 0) + engagement.get(k, 0)
        t[ak] = round(t[tk] / t["uses"], 2)
    t["score"] = round(_compute_score(t), 4)


def _compute_score(t: dict) -> float:
    """Per spec: 0.30 views + 0.20 likes + 0.20 replies + 0.15 reposts + 0.15 archetype_bonus."""
    # Normalization happens at rerank time, so this is a rough 0-1 sum.
    raw = (
        0.30 * min(t.get("avg_views", 0) / 5000, 1.0)
        + 0.20 * min(t.get("avg_likes", 0) / 200, 1.0)
        + 0.20 * min(t.get("avg_replies", 0) / 20, 1.0)
        + 0.15 * min(t.get("avg_reposts", 0) / 10, 1.0)
        + 0.15 * min(t.get("uses", 0) / 10, 1.0)
    )
    return round(raw, 4)


# ─── Ranker ──────────────────────────────────────────────────────────────

def rerank(perf: dict) -> dict:
    """Re-rank templates per platform using the perf scores. Returns recommendations."""
    if not TEMPLATES_FILE.exists():
        return {"platforms": {}, "score_changes": {}}
    try:
        import yaml
        text = TEMPLATES_FILE.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
    except Exception:
        return {"platforms": {}, "score_changes": {}}

    platforms = data.get("platforms", {})
    recommendations = {}
    score_changes = {}

    for platform, pdata in platforms.items():
        templates = pdata.get("templates", []) or []
        # Score each template
        scored = []
        for t in templates:
            tid = t.get("id", "")
            cur = perf.get("templates", {}).get(tid, {})
            score = cur.get("score", 0.0)
            # Boost by default_factor
            default_factor = t.get("default_factor", 1.0)
            final = score * default_factor
            scored.append((tid, final))
        # Sort desc
        scored.sort(key=lambda x: -x[1])
        recommendations[platform] = [tid for tid, _ in scored[:3]]
        # Score change = how much the top-3 moved
        for tid, s in scored:
            prev = perf.get("templates", {}).get(tid, {}).get("prev_score", 0.0)
            score_changes[tid] = round(s - prev, 4)
            perf.setdefault("templates", {}).setdefault(tid, {})["prev_score"] = s

    return {"platforms": recommendations, "score_changes": score_changes}


# ─── Pull (one draft) ────────────────────────────────────────────────────

def pull_draft(draft_path: Path) -> dict:
    """Pull engagement for a single posted draft. Returns a JSON report."""
    text = draft_path.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)
    platform = (fm.get("platform") or "").lower()
    template_id = fm.get("template_id", "unknown")

    # Find Buffer post ids
    buf_ids = fm.get("buffer_post_ids", {}) or {}
    tweet_id = fm.get("tweet_id", "")
    linkedin_urn = fm.get("linkedin_share_urn", "")
    blog_url = fm.get("blog_url", "")

    token = load_buffer_token()
    engagement: dict = {"views": 0, "likes": 0, "replies": 0, "reposts": 0}
    if not token:
        return {
            "draft": str(draft_path),
            "platform": platform,
            "ok": False,
            "reason": "BUFFER_ACCESS_TOKEN not set in .env",
        }

    # Pull for each platform present
    if buf_ids:
        for svc, post_id in buf_ids.items():
            stats = pull_buffer_engagement(post_id, token)
            engagement["views"] += stats.get("views", 0)
            engagement["likes"] += stats.get("likes", 0)
            engagement["replies"] += stats.get("replies", 0)
            engagement["reposts"] += stats.get("reposts", 0)
    elif tweet_id or linkedin_urn:
        # X / LinkedIn direct
        for pid in [tweet_id, linkedin_urn]:
            if pid:
                stats = pull_buffer_engagement(pid, token)
                engagement["views"] += stats.get("views", 0)
                engagement["likes"] += stats.get("likes", 0)
                engagement["replies"] += stats.get("replies", 0)
                engagement["reposts"] += stats.get("reposts", 0)
    elif blog_url:
        # No engagement API for blog — leave at 0, mark as such
        engagement["_blog"] = True
        engagement["views"] = 0

    pulled_at = datetime.now().isoformat(timespec="seconds")

    # Update perf ledger
    perf = load_perf()
    update_perf(perf, template_id, engagement)
    save_perf(perf)

    # Append rank-history row
    RANK_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with RANK_HISTORY.open("a", encoding="utf-8") as f:
        row = {
            "ts": pulled_at,
            "template_id": template_id,
            "platform": platform,
            "engagement": engagement,
            "score": perf["templates"][template_id]["score"],
        }
        f.write(json.dumps(row) + "\n")

    return {
        "ok": True,
        "draft": str(draft_path.relative_to(VAULT)) if draft_path.is_relative_to(VAULT) else str(draft_path),
        "platform": platform,
        "template_id": template_id,
        "engagement": engagement,
        "pulled_at": pulled_at,
    }


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="SpielOS Analyst — engagement + re-rank")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pull", help="Pull engagement for one posted draft")
    p.add_argument("--draft", required=True, help="Path to posted .md file")

    pa = sub.add_parser("pull-all", help="Pull engagement for all recently-posted drafts")
    pa.add_argument("--since", default="24h", help="Time window: 24h, 7d, 30d")

    sub.add_parser("rerank", help="Re-rank templates from current perf ledger")

    r = sub.add_parser("report", help="Summarize perf for a platform")
    r.add_argument("--platform", required=True, choices=["x", "linkedin", "blog"])
    r.add_argument("--days", type=int, default=30)

    args = parser.parse_args()

    if args.cmd == "pull":
        draft = Path(args.draft)
        if not draft.is_absolute():
            draft = VAULT / draft
        if not draft.exists():
            print(f"ERROR: draft not found: {draft}", file=sys.stderr)
            return 1
        try:
            result = pull_draft(draft)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 2

    if args.cmd == "pull-all":
        posted_dir = VAULT / "content" / "posted"
        if not posted_dir.exists():
            print("[]")
            return 0
        # Parse --since
        since_map = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
        cutoff = datetime.now() - since_map.get(args.since, timedelta(hours=24))
        results = []
        for d in sorted(posted_dir.glob("*.md")):
            try:
                text = d.read_text(encoding="utf-8")
                fm, _ = parse_frontmatter(text)
                posted_at = fm.get("posted_at", "")
                if posted_at:
                    try:
                        ts = datetime.fromisoformat(posted_at)
                        if ts < cutoff:
                            continue
                    except Exception:
                        pass
            except Exception:
                continue
            try:
                r = pull_draft(d)
                results.append(r)
            except Exception as e:
                results.append({"draft": d.name, "ok": False, "reason": str(e)})
        print(json.dumps(results, indent=2))
        return 0

    if args.cmd == "rerank":
        perf = load_perf()
        result = rerank(perf)
        save_perf(perf)
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "report":
        perf = load_perf()
        # Filter rank-history by platform + days
        cutoff = datetime.now() - timedelta(days=args.days)
        rows = []
        if RANK_HISTORY.exists():
            for line in RANK_HISTORY.read_text().splitlines():
                try:
                    r = json.loads(line)
                    if r.get("platform") != args.platform:
                        continue
                    if datetime.fromisoformat(r["ts"]) < cutoff:
                        continue
                    rows.append(r)
                except Exception:
                    continue
        report = {
            "platform": args.platform,
            "days": args.days,
            "rows": len(rows),
            "templates": perf.get("templates", {}),
        }
        print(json.dumps(report, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
