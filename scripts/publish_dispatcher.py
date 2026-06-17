#!/usr/bin/env python3
"""publish_dispatcher.py — Route a draft to the right publisher.

Single entry point for publishing. The orchestrator calls
dispatch_publish(draft_path) and gets back either:
  - {"ok": True, "post_ids": {...}, "urls": {...}, "archived": Path}
  - {"ok": False, "reason": "..."}

This module owns:
  - The platform -> publisher mapping
  - The dry-run gate
  - The pre-publish cadence check
  - The post-publish archive + verify
  - Logging

It does NOT own:
  - The actual API calls (those live in publishers/)
  - The state machine transitions (those live in state_handlers.py)

No CLI. No LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from datetime import datetime, timedelta

import cadence
import ui
from engine_state import QUEUE_DIR, POSTED_DIR
from engine_frontmatter import parse_frontmatter
from engine_serial import log, log_err

import archive as archive_mod
import verify as verify_mod


class DispatchError(Exception):
    pass


PLATFORM_ROUTING = {
    "x":         "publishers.buffer",       # Try Buffer first
    "twitter":   "publishers.buffer",
    "linkedin":  "publishers.buffer",        # Try Buffer first
    "blog":      "publishers.blog",
    "pillar":    "publishers.blog",
    "buffer":    "publishers.buffer",
}

FALLBACK_ROUTING = {
    "x":         "publishers.twitter",
    "linkedin":  "publishers.linkedin",
}


def _platform_of(draft_path: Path) -> str:
    try:
        text = draft_path.read_text()
        fm, _ = parse_frontmatter(text)
    except (OSError, ValueError):
        fm = {}
    plat = (fm.get("platform") or "").lower().strip()
    if plat:
        return plat
    n = draft_path.name.lower()
    if "tweet" in n or "-x-" in n:
        return "x"
    if "linkedin" in n:
        return "linkedin"
    if "pillar" in n or "blog" in n:
        return "blog"
    return ""


def _route(platform: str) -> str:
    return PLATFORM_ROUTING.get(platform.lower(), "")


def _import_publisher(module_path: str):
    import importlib
    return importlib.import_module(module_path)


def _normalize_buffer_results(results: list[dict]) -> tuple[dict, dict]:
    """Buffer returns a list of per-channel results. Flatten to post_ids and urls."""
    post_ids: dict = {}
    urls: dict = {}
    for r in results or []:
        if not isinstance(r, dict):
            continue
        service = r.get("service") or r.get("channel_service") or ""
        service = service.lower()
        if service in ("twitter", "x"):
            post_ids["x"] = r.get("update_id") or r.get("id") or post_ids.get("x")
            if r.get("url"):
                urls["x"] = r["url"]
        elif service in ("linkedin", "linkedin-page", "linkedin-profile"):
            post_ids["linkedin"] = r.get("update_id") or r.get("id") or post_ids.get("linkedin")
            if r.get("url"):
                urls["linkedin"] = r["url"]
        elif service == "threads":
            post_ids["threads"] = r.get("update_id") or r.get("id") or post_ids.get("threads")
            if r.get("url"):
                urls["threads"] = r["url"]
    return post_ids, urls


def check_dedup(draft_path: Path, platform: str,
                posted_dir: Path | None = None) -> tuple[bool, str]:
    """Reject if a draft with same pillar + platform was posted in the last 24h."""
    posted_dir = posted_dir or POSTED_DIR
    if not posted_dir.exists():
        return True, "no posted dir yet"
    try:
        text = draft_path.read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
    except (OSError, ValueError):
        return True, "can't parse draft"
    pillar = fm.get("pillar", "")
    if not pillar:
        return True, "no pillar to dedup on"
    cutoff = datetime.now() - timedelta(hours=24)
    for posted_file in sorted(posted_dir.glob("*.md")):
        try:
            pfm, _ = parse_frontmatter(posted_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (pfm.get("pillar") or "") != pillar:
            continue
        if (pfm.get("platform") or "").lower() != platform:
            continue
        posted_at_str = pfm.get("posted_at", "")
        if not posted_at_str:
            continue
        try:
            posted_dt = datetime.fromisoformat(posted_at_str)
            if posted_dt > cutoff:
                title = pfm.get("title", "?")
                return False, f"'{title}' already posted on {platform} at {posted_at_str}"
        except ValueError:
            continue
    return True, "no duplicate found"


def dispatch_publish(
    draft_path: Path,
    *,
    dry_run: bool = False,
    skip_cadence: bool = False,
    skip_dedup: bool = False,
    auto_confirm: bool = False,
    require_confirm: bool = True,
    confirm_fn=None,
    queue_dir: Path | None = None,
    posted_dir: Path | None = None,
) -> dict:
    """Publish a single draft. Returns a result dict.

    Args:
        draft_path: Path to draft in content/queue/.
        dry_run: If True, run publishers with dry_run=True. No API calls.
        skip_cadence: If True, skip cadence check (e.g. for testing).
        auto_confirm: If True, skip the manual confirm prompt.
        require_confirm: If True, ask for confirm unless auto_confirm.
        confirm_fn: Optional callable to use for confirm. Defaults to input().

    Returns:
        {"ok": bool, "post_ids": {...}, "urls": {...}, "archived": Path|None,
         "reason": str (on failure), "skipped": bool (cadence)}
    """
    draft_path = Path(draft_path)
    queue_dir = queue_dir or QUEUE_DIR
    posted_dir = posted_dir
    result: dict[str, Any] = {
        "ok": False,
        "post_ids": {},
        "urls": {},
        "archived": None,
        "reason": "",
        "skipped": False,
    }
    if not draft_path.exists():
        result["reason"] = f"draft not found: {draft_path}"
        log_err("dispatch", result["reason"])
        return result
    if draft_path.parent != queue_dir:
        result["reason"] = f"draft must be in {queue_dir}, got {draft_path.parent}"
        log_err("dispatch", result["reason"])
        return result
    platform = _platform_of(draft_path)
    if not platform:
        result["reason"] = f"could not determine platform for {draft_path.name}"
        log_err("dispatch", result["reason"])
        return result
    if platform not in PLATFORM_ROUTING:
        result["reason"] = f"unknown platform: {platform}"
        log_err("dispatch", result["reason"])
        return result
    if not skip_cadence and platform in ("x", "linkedin", "blog"):
        ok, reason = cadence.check_cadence(platform, posted_dir=posted_dir)
        if not ok:
            result["reason"] = f"cadence: {reason}"
            result["skipped"] = True
            log("WARN", "dispatch", "skipped (cadence)",
                draft=str(draft_path), platform=platform, reason=reason)
            return result
    if not skip_dedup:
        ok, reason = check_dedup(draft_path, platform, posted_dir=posted_dir)
        if not ok:
            result["reason"] = f"dedup: {reason}"
            result["skipped"] = True
            log("WARN", "dispatch", "skipped (dedup)",
                draft=str(draft_path), platform=platform, reason=reason)
            return result
    if require_confirm and not auto_confirm and not dry_run:
        if confirm_fn is None:
            confirm_fn = _default_confirm
        try:
            confirmed = confirm_fn(draft_path, platform)
        except (EOFError, KeyboardInterrupt):
            result["reason"] = "publish cancelled by user"
            return result
        if not confirmed:
            result["reason"] = "publish cancelled by user"
            return result
    module_path = _route(platform)
    if not module_path:
        result["reason"] = f"no publisher for platform: {platform}"
        return result
    api_result = None
    tried = []
    candidates = [module_path]
    if platform in FALLBACK_ROUTING and module_path == "publishers.buffer":
        candidates.append(FALLBACK_ROUTING[platform])
    for attempt_mod in candidates:
        if attempt_mod in tried:
            continue
        tried.append(attempt_mod)
        try:
            publisher = _import_publisher(attempt_mod)
        except ImportError:
            continue
        log("INFO", "dispatch", "publishing",
            draft=str(draft_path), platform=platform,
            publisher=attempt_mod, dry_run=dry_run)
        try:
            kwargs = {"dry_run": dry_run}
            if attempt_mod == "publishers.buffer" and platform in ("x", "linkedin"):
                kwargs["service"] = platform
            api_result = publisher.publish(draft_path, **kwargs)
            break
        except RuntimeError as e:
            if attempt_mod == "publishers.buffer" and platform in FALLBACK_ROUTING:
                log("WARN", "dispatch", "Buffer unavailable, falling back",
                    platform=platform, reason=str(e))
                continue
            result["reason"] = f"publisher {attempt_mod}.publish failed: {e}"
            log_err("dispatch", result["reason"], error=str(e))
            return result
        except Exception as e:
            result["reason"] = f"publisher {attempt_mod}.publish failed: {e}"
            log_err("dispatch", result["reason"], error=str(e))
            return result
    if api_result is None:
        result["reason"] = f"no publisher available for {platform} (tried: {tried})"
        return result
    if isinstance(api_result, list):
        post_ids, urls = _normalize_buffer_results(api_result)
    elif isinstance(api_result, dict):
        post_ids, urls = _normalize_buffer_results(api_result.get("results") or [])
        if not post_ids:
            post_ids, urls = _single_result(api_result, platform)
    else:
        post_ids, urls = {}, {}
    if dry_run:
        result["ok"] = True
        result["post_ids"] = post_ids
        result["urls"] = urls
        result["reason"] = "dry-run"
        return result
    try:
        archived = archive_mod.archive_draft(
            draft_path,
            post_ids=post_ids,
            urls=urls,
            queue_dir=queue_dir,
            posted_dir=posted_dir,
        )
    except archive_mod.ArchiveError as e:
        result["reason"] = f"archive failed: {e}"
        log_err("dispatch", result["reason"])
        return result
    checks = verify_mod.verify_archive(
        draft_path, archived,
        queue_dir=queue_dir, posted_dir=posted_dir,
    )
    if not all(checks.values()):
        failed = [k for k, v in checks.items() if not v]
        result["reason"] = f"verify failed: {', '.join(failed)}"
        log_err("dispatch", result["reason"], failed_checks=failed)
        result["archived"] = archived
        return result
    result["ok"] = True
    result["post_ids"] = post_ids
    result["urls"] = urls
    result["archived"] = archived
    log("INFO", "dispatch", "published",
        draft=str(draft_path),
        platform=platform,
        archived=str(archived),
        post_ids=post_ids,
    )
    return result


def _single_result(api_result, platform: str) -> tuple[dict, dict]:
    if not isinstance(api_result, dict):
        return {}, {}
    post_ids: dict = {}
    urls: dict = {}
    pid = (api_result.get("post_id") or api_result.get("id") or
           api_result.get("tweet_id") or api_result.get("urn"))
    url = api_result.get("url") or api_result.get("tweet_url")
    if platform == "x":
        if pid:
            post_ids["x"] = pid
        if url:
            urls["x"] = url
    elif platform == "linkedin":
        if pid:
            post_ids["linkedin"] = pid
        if url:
            urls["linkedin"] = url
    elif platform in ("blog", "pillar"):
        if url:
            urls["blog"] = url
    return post_ids, urls


def _default_confirm(draft_path: Path, platform: str) -> bool:
    print()
    print(ui.status("info", f"About to publish {draft_path.name} via {platform}"))
    print(ui.status("arrow", f"Run: publishers.{platform}.publish({draft_path.name})"))
    print()
    try:
        ans = input("  Dispatch? (y/N): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in ("y", "yes")


def dispatch_bulk(
    queue_dir: Path,
    decisions: dict[str, str] | None = None,
    *,
    dry_run: bool = False,
    auto_confirm: bool = False,
    skip_cadence: bool = False,
    posted_dir: Path | None = None,
) -> dict:
    """Publish multiple drafts. decisions maps filename -> "publish" | "hold" | "skip" | "edit".

    If decisions is None, publishes everything in queue_dir.
    Returns a summary dict.
    """
    queue_dir = Path(queue_dir)
    drafts = sorted(queue_dir.glob("*.md"))
    summary = {
        "published": [],
        "skipped_cadence": [],
        "held": [],
        "skipped": [],
        "edited": [],
        "failed": [],
    }
    for d in drafts:
        decision = (decisions or {}).get(d.name, "publish")
        if decision == "publish":
            res = dispatch_publish(
                d,
                dry_run=dry_run,
                auto_confirm=auto_confirm,
                skip_cadence=skip_cadence,
                queue_dir=queue_dir,
                posted_dir=posted_dir,
            )
            if res["ok"]:
                summary["published"].append(d.name)
            elif res.get("skipped"):
                summary["skipped_cadence"].append(d.name)
            else:
                summary["failed"].append((d.name, res["reason"]))
        elif decision == "hold":
            summary["held"].append(d.name)
        elif decision == "edit":
            summary["edited"].append(d.name)
        elif decision == "skip":
            summary["skipped"].append(d.name)
    return summary
