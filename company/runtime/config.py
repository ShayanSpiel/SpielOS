"""User configuration layer over generic runtime defaults.

Prep for packaging: identity-specific values (funnel metrics, owner lists,
capability maps, alert copy, version) are sourced from here instead of being
compiled into generic modules. Resolution order:

1. ``GENERIC_DEFAULTS`` — the shipped defaults. They reproduce today's
   behavior, so an absent or empty user file changes nothing.
2. ``config.user.json`` beside this module (the user layer, optional) —
   top-level keys override the defaults.

Typed accessors return immutable values; callers must not mutate them.
"""

from __future__ import annotations

import json
from pathlib import Path

COMPANY_ROOT = Path(__file__).resolve().parents[1]
USER_CONFIG_PATH = COMPANY_ROOT / "config.user.json"

# Runtime version: defined once here; every other module imports it.
VERSION = "6.2.5"

# Generic defaults. Values mirror the current SpielOS deployment so behavior
# is unchanged whether or not config.user.json exists.
GENERIC_DEFAULTS: dict = {
    # Metrics that count as real market outcomes (business truth gating).
    "business_outcome_metrics": [
        "reply_rate", "sales", "booked_calls", "leads", "qualified_leads",
        "daily_leads", "daily_visits", "visits", "services_leads",
    ],
    # Owners whose goals are technical by definition (never business truth).
    "technical_owners": ["system-improvement"],
    # Metrics the Director handler accepts on its own goals.
    "director_metrics": [
        "all_children_achieved", "achieved_children",
        "reply_rate", "sales", "booked_calls",
    ],
    # Department attention capability -> catalog employee/workflow mapping.
    "capability_employees": {"lead_research": "lead-researcher"},
    "capability_workflows": {"lead_research": "lead-research"},
    # Resource-conflict channel groups: owners that share one exclusive
    # channel and cannot run concurrently. Single source consumed by the
    # store's busy-goal projection and continuation's resource keys.
    "channel_groups": {"email": ["email", "outbound"]},
    # macOS supervisor notification title (user-facing brand copy).
    "supervisor_alert_title": "SpielOS supervisor",
}

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    merged = {key: list(value) if isinstance(value, list)
              else dict(value) if isinstance(value, dict)
              else value for key, value in GENERIC_DEFAULTS.items()}
    try:
        user = json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        user = {}
    if isinstance(user, dict):
        for key, value in user.items():
            merged[key] = value
    _cache = merged
    return merged


def get(key: str, default=None):
    """Raw accessor over the merged configuration."""
    values = _load()
    if key in values:
        return values[key]
    return default


def business_outcome_metrics() -> frozenset:
    return frozenset(get("business_outcome_metrics") or ())


def technical_owners() -> frozenset:
    return frozenset(get("technical_owners") or ())


def director_metrics() -> tuple:
    return tuple(get("director_metrics") or ())


def capability_employees() -> dict:
    return dict(get("capability_employees") or {})


def capability_workflows() -> dict:
    return dict(get("capability_workflows") or {})


def channel_groups() -> dict:
    return dict(get("channel_groups") or {})


def channel_for_owner(owner_id: str) -> str | None:
    """The shared channel group an owner belongs to, else None.

    Single derivation for both consumers (store busy-goal projection and
    continuation resource keys), so they can never disagree about which
    owners contend for one exclusive channel.
    """
    for channel, owners in channel_groups().items():
        if owner_id in (owners or ()):
            return channel
    return None


def resource_key(owner_id: str, config: dict | None = None,
                 system_improvement_owner: str = "system-improvement") -> tuple:
    """The exclusive-resource key a goal occupies.

    System-improvement goals contend on their declared file scope; owners in
    a shared channel group contend on the channel; everyone else contends on
    the owner id itself.
    """
    config = config or {}
    if owner_id == system_improvement_owner:
        files = tuple(sorted(config.get("allowed_files") or ()))
        return ("files", files) if files else ("owner", owner_id)
    channel = channel_for_owner(owner_id)
    if channel is not None:
        return ("channel", channel)
    return ("owner", owner_id)


def supervisor_alert_title() -> str:
    return str(get("supervisor_alert_title") or "SpielOS supervisor")
