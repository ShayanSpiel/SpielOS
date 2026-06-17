#!/usr/bin/env python3
"""buffer_client.py — Wrapper for Buffer API engagement lookups.

Pure functions where possible. HTTP calls live here. Reads creds from env.

Functions:
    load_config()                       -> Buffer config dict
    list_channels(token, ...)           -> list of channel dicts
    fetch_interactions(token, update_id) -> dict of engagement metrics
    aggregate_metrics(interactions)    -> summarized metrics dict
    fetch_for_post(token, post_ids)    -> combined metrics for multi-platform post

The engagement fields we surface:
    reactions  (likes, favorites, etc.)
    comments   (replies, comments)
    reposts    (retweets, shares)
    impressions (views)
    rate       (engagements / impressions)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import engine_state


BUFFER_API_URL = "https://api.buffer.com"
DEFAULT_TIMEOUT = 30


def _read_env() -> dict:
    out = {}
    for k in ("BUFFER_ACCESS_TOKEN", "BUFFER_CHANNEL_IDS"):
        v = os.environ.get(k)
        if v:
            out[k] = v
    return out


def _read_dotenv_for(path_keys: list[str]) -> dict:
    candidates = [
        Path(engine_state.VAULT) / ".env",
        Path.home() / ".config" / "opencode" / ".env",
    ]
    found = {}
    for env_path in candidates:
        if not env_path.exists():
            continue
        try:
            text = env_path.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in path_keys:
                found[k] = v
    return found


def load_config() -> dict:
    """Load Buffer config from env + .env files."""
    creds = _read_env()
    creds.update(_read_dotenv_for(list(creds.keys()) or [
        "BUFFER_ACCESS_TOKEN", "BUFFER_CHANNEL_IDS"
    ]))
    return creds


def _graphql_request(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        BUFFER_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")[:500] if hasattr(e, "read") else ""
        raise RuntimeError(f"Buffer API HTTP {e.code}: {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Buffer API URLError: {e.reason}") from e


def list_channels(token: str) -> list[dict]:
    """List Buffer channels for the authenticated user."""
    query = """
    query {
      account { id }
      channels { id name service }
    }
    """
    data = _graphql_request(query, {}, token)
    return data.get("data", {}).get("channels", []) or []


def fetch_interactions(token: str, update_id: str) -> dict:
    """Fetch engagement interactions for a single Buffer update.

    Returns a dict of {reactions, comments, reposts, impressions} or
    a dict with 'error' key on failure.
    """
    query = """
    query ($id: ID!) {
      update(id: $id) {
        id
        statistics {
          reach
          engagements_count
          reactions
          comments
          shares
        }
      }
    }
    """
    try:
        data = _graphql_request(query, {"id": update_id}, token)
    except RuntimeError as e:
        return {"error": str(e), "update_id": update_id}
    update = data.get("data", {}).get("update")
    if not update:
        return {"error": "update not found", "update_id": update_id}
    stats = update.get("statistics") or {}
    return {
        "update_id":   update_id,
        "reactions":   int(stats.get("reactions") or 0),
        "comments":    int(stats.get("comments") or 0),
        "reposts":     int(stats.get("shares") or 0),
        "impressions": int(stats.get("reach") or 0),
        "engagements": int(stats.get("engagements_count") or 0),
    }


def aggregate_metrics(per_platform: dict[str, dict]) -> dict:
    """Combine per-platform engagement into a single metrics dict."""
    keys = ("reactions", "comments", "reposts", "impressions", "engagements")
    totals = {k: 0 for k in keys}
    for plat_data in per_platform.values():
        if not isinstance(plat_data, dict) or "error" in plat_data:
            continue
        for k in keys:
            totals[k] += int(plat_data.get(k, 0) or 0)
    if totals["impressions"] > 0:
        totals["rate"] = totals["engagements"] / totals["impressions"]
    else:
        totals["rate"] = 0.0
    return totals


def fetch_for_post(token: str, post_ids: dict[str, str]) -> dict:
    """Fetch engagement for a multi-platform post.

    post_ids maps service name (x, linkedin, threads) to Buffer update_id.
    Returns {per_platform: {...}, aggregate: {...}}.
    """
    per_platform: dict[str, dict] = {}
    for service, update_id in (post_ids or {}).items():
        if not update_id:
            continue
        per_platform[service] = fetch_interactions(token, update_id)
    return {
        "per_platform": per_platform,
        "aggregate": aggregate_metrics(per_platform),
    }


def parse_channel_ids(channel_ids_str: str) -> list[str]:
    """Parse the BUFFER_CHANNEL_IDS env var (comma-separated)."""
    if not channel_ids_str:
        return []
    return [s.strip() for s in channel_ids_str.split(",") if s.strip()]


def is_configured() -> bool:
    """Returns True if Buffer creds are present."""
    cfg = load_config()
    return bool(cfg.get("BUFFER_ACCESS_TOKEN"))
