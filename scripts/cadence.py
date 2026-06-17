#!/usr/bin/env python3
"""cadence.py — Per-platform posting rate limits.

Reads limits from rules.yaml §cadence. Counts today's and this-week's
posts in content/posted/ via the `posted_at` frontmatter field. Returns
(ok, reason) so the publish dispatcher can decide whether to dispatch,
skip, or block.

Pure functions. No file I/O (besides reading posted/ at call time). No CLI.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from engine_state import POSTED_DIR
from engine_frontmatter import parse_frontmatter
from engine_config import config


_VALID_PLATFORMS = {"x", "linkedin", "blog", "pillar", "buffer"}


def _parse_posted_at(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value
    s = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            try:
                return datetime.strptime(s[: len(fmt)], fmt)
            except ValueError:
                continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _platform_of(frontmatter: dict, fallback_path: Path) -> str:
    plat = (frontmatter.get("platform") or "").lower().strip()
    if plat:
        return plat
    name = fallback_path.name.lower()
    if "tweet" in name or "-x-" in name or "-x." in name:
        return "x"
    if "linkedin" in name:
        return "linkedin"
    if "pillar" in name or "blog" in name:
        return "blog"
    return "other"


def _is_in_window(dt: datetime, start: datetime, end: datetime) -> bool:
    return start <= dt <= end


def _counts(platform: str, posted_dir: Path | None = None) -> dict:
    """Return {'today': N, 'this_week': N, 'total': N} for the given platform."""
    posted_dir = posted_dir or POSTED_DIR
    if not posted_dir.exists():
        return {"today": 0, "this_week": 0, "total": 0}
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    today = 0
    week = 0
    total = 0
    for f in posted_dir.glob("*.md"):
        try:
            text = f.read_text()
            fm, _ = parse_frontmatter(text)
        except (OSError, ValueError):
            continue
        if not fm:
            continue
        if _platform_of(fm, f) != platform:
            continue
        dt = _parse_posted_at(fm.get("posted_at"))
        if not dt:
            continue
        total += 1
        if _is_in_window(dt, today_start, now):
            today += 1
        if _is_in_window(dt, week_start, now):
            week += 1
    return {"today": today, "this_week": week, "total": total}


def _limits_for(platform: str) -> dict:
    cadence = config.cadence or {}
    plat = cadence.get(platform) or cadence.get("default") or {}
    return {
        "per_day": int(plat.get("per_day", 99)),
        "per_week": int(plat.get("per_week", 99)),
    }


def check_cadence(platform: str, posted_dir: Path | None = None) -> tuple[bool, str]:
    """Returns (ok, reason). ok=False if cadence limit hit.

    `reason` is empty when ok, or a human-readable message when not.
    """
    platform = (platform or "").lower().strip()
    if platform not in _VALID_PLATFORMS:
        return True, ""
    limits = _limits_for(platform)
    counts = _counts(platform, posted_dir=posted_dir)
    if counts["today"] >= limits["per_day"]:
        return False, (
            f"daily limit hit for {platform} "
            f"({counts['today']}/{limits['per_day']} today)"
        )
    if counts["this_week"] >= limits["per_week"]:
        return False, (
            f"weekly limit hit for {platform} "
            f"({counts['this_week']}/{limits['per_week']} this week)"
        )
    return True, ""


def status(platforms: list[str] | None = None, posted_dir: Path | None = None) -> str:
    """Render a multi-line cadence status for the given platforms."""
    platforms = platforms or sorted(_VALID_PLATFORMS)
    lines = []
    for p in platforms:
        if p not in _VALID_PLATFORMS:
            continue
        limits = _limits_for(p)
        counts = _counts(p, posted_dir=posted_dir)
        remaining_day = max(0, limits["per_day"] - counts["today"])
        remaining_week = max(0, limits["per_week"] - counts["this_week"])
        lines.append(
            f"  {p:10s}  {counts['today']:>2}/{limits['per_day']:>2} today  ·  "
            f"{counts['this_week']:>2}/{limits['per_week']:>2} this week  ·  "
            f"{remaining_day} day / {remaining_week} week remaining"
        )
    return "\n".join(lines)
