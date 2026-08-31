"""Read-only PostHog evidence Connection used by the Analytics Department.

Read surfaces (owner directive 2026-08-17, verified live 2026-08-17): the
working server-side read channel is the project-scoped Query API on the EU
region, `POST https://eu.posthog.com/api/projects/{project_id}/query/` (project
id 92369, "Default project"), authenticated with the personal API key
`POSTHOG_PERSONAL_API_KEY` (`phx_...`, stored only in gitignored
`.spielos/.env`) sent as `Authorization: Bearer`. The PostHog MCP server
registered in `opencode.json` under `mcp.servers.posthog` (`type: remote`,
URL `https://mcp.posthog.com/mcp`, `oauth: false`) uses the same personal API
key via `{env:POSTHOG_PERSONAL_API_KEY}` with `x-posthog-read-only: true`; it
is the agent-facing read channel. The old `us.posthog.com/api/warehouse/query/`
route with the `phc_` client-side project key (`POSTHOG_PROJECT_TOKEN`) is NOT
a working channel for this project (404/401: region and credential mismatch)
and is not used.

The `PostHogClient` HogQL helpers below are the deterministic, unit-tested
interface to that working channel; they never hardcode credentials and never
write, mutate, or forward events. Funnel taxonomy (current loader v4, full
capture 2026-08-18): the loader emits `cta_clicked` (engagement),
`content_landing` (attention), and the lead-gen events `lead_form_view`,
`lead_form_start`, `lead_form_submit`, `lead_form_success`, and
`lead_form_error` (intent/lead). The retired loader names
`agent_briefing_form_start/submit/success`, `waitlist_form_submit/success`,
`click_contact`, and `click_install` are no longer emitted; they are labeled
`missing`, never zero, because an absent event means it was not captured, not
that zero people behaved that way. Events are captured for ALL visitors
(owner directive 2026-08-18 — no consent gate): PostHog session replay is ON,
`person_profiles: 'always'` enables anonymous funnel analysis, and
`mask_all_inputs: true` means raw form values are never stored; funnel events
only count starts/submits/successes.

Changelog:
- v1.5.0 (2026-08-18, goal-analytics-full-capture-v1-20260818): loader v4
  full-capture taxonomy. REAL_LOADER_EVENTS is now
  (`cta_clicked`, `content_landing`, `lead_form_view`, `lead_form_start`,
  `lead_form_submit`, `lead_form_success`, `lead_form_error`);
  LEAD_SUCCESS_EVENTS is (`lead_form_success`,); the waitlist/agent-brief/
  support-CTA names moved to RETIRED_FUNNEL_EVENTS (missing, never zero).
  Consent-gate language removed: events are captured for ALL visitors
  (owner directive 2026-08-18); PostHog runs `person_profiles: 'always'`,
  session replay ON, `mask_all_inputs: true`.
- v1.4.0 (2026-08-18, change-e69f419da9): added the per-template funnel
  dimension. `_rendition_lines` carries `template_id` from the manifest item
  design orders into the joined rows, and `consume_batch_evidence` emits a
  `template_breakdown` block of per-template platform views built from the
  joined per-post rows with the same honesty rules as the rest of the funnel
  (missing stays missing, never zero; a registered archetype with no per-post
  row in the batch reports a labeled missing entry). Website events
  (content_landing, cta_clicked, leads) stay batch-level only — never
  per-template attribution without per-post tracking.
- v1.3.0 (2026-08-17): EU project-scoped Query API read channel with the
  personal API key; corrected funnel event taxonomy (retired loader names
  stay missing, never zero).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".spielos" / ".env"
# Working server-side read channel (owner directive 2026-08-17, verified live):
# EU region project-scoped Query API with a personal API key Bearer credential.
POSTHOG_API_HOST = "https://eu.posthog.com"
DEFAULT_PROJECT_ID = 92369
MCP_SERVER_URL = "https://mcp.posthog.com/mcp"


def project_query_url(project_id: int = DEFAULT_PROJECT_ID) -> str:
    """The project-scoped HogQL Query API route for one PostHog project."""
    return f"{POSTHOG_API_HOST}/api/projects/{int(project_id)}/query/"


# Canonical funnel stage events defined by the funnel contract (funnel.json);
# read-only reference for the analytics skill and honest missing labeling.
FUNNEL_STAGE_EVENTS = (
    "$pageview", "content_landing", "cta_clicked", "lead_form_view",
    "lead_form_start", "lead_form_submit", "lead_form_success",
    "qualified_lead", "booked_call", "sale",
)

# Events the REAL deployed loader emits (loader v4, full capture
# 2026-08-18). The retired loader names below are no longer emitted by the
# loader; absence stays missing.
RETIRED_FUNNEL_EVENTS = (
    "agent_briefing_form_start", "agent_briefing_form_submit",
    "agent_briefing_form_success",
    "waitlist_form_submit", "waitlist_form_success",
    "click_contact", "click_install",
)
REAL_LOADER_EVENTS = (
    "cta_clicked",
    "content_landing",
    "lead_form_view", "lead_form_start", "lead_form_submit",
    "lead_form_success", "lead_form_error",
)
# Live lead-success events consumed as the funnel's `leads` stage.
LEAD_SUCCESS_EVENTS = ("lead_form_success",)

# Per-batch funnel consumption set: retired names keep honest missing labels,
# live names carry the real observed counts (never zero when absent).
FUNNEL_EVENTS = RETIRED_FUNNEL_EVENTS + REAL_LOADER_EVENTS

# Campaign-to-lead identity chain preserved on every join.
BATCH_JOIN_KEYS = ("campaign_id", "batch_id", "item_id", "content_id",
                   "creative_signature")

PLATFORMS = ("threads", "youtube")


class PostHogError(RuntimeError):
    """A safe PostHog error that never embeds credentials."""


def _env_values(path: Path = ENV_PATH) -> dict[str, str]:
    """Read dotenv assignments without executing the file as shell code."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def posthog_token() -> str:
    """The personal API key from the host environment or .spielos/.env; never inline."""
    values = _env_values()
    token = (os.environ.get("POSTHOG_PERSONAL_API_KEY")
             or values.get("POSTHOG_PERSONAL_API_KEY") or "").strip()
    if not token:
        raise PostHogError(
            "POSTHOG_PERSONAL_API_KEY is not configured; keep it only in .spielos/.env")
    return token


class PostHogClient:
    """Read-only HogQL client (POST {POSTHOG_API_HOST}/api/projects/{id}/query/)."""

    def __init__(self, api_key: str | None = None,
                 project_id: int = DEFAULT_PROJECT_ID,
                 api_url: str | None = None):
        self.api_key = api_key or posthog_token()
        self.project_id = int(project_id)
        self.api_url = api_url or project_query_url(self.project_id)

    def query(self, hogql: str, timeout: int = 30) -> dict[str, Any]:
        """Run one read-only HogQL query and return the raw warehouse result."""
        payload = json.dumps({"query": {"kind": "HogQLQuery", "query": hogql}}).encode("utf-8")
        request = Request(self.api_url, data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })
        try:
            with urlopen(request, timeout=timeout) as response:  # nosec B310: fixed HTTPS endpoint
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = ""
            try:
                detail = error.read().decode("utf-8")[:300]
            except Exception:  # noqa: BLE001 - body may be empty or binary
                pass
            suffix = f": {detail}" if detail else ""
            raise PostHogError(f"PostHog query failed with HTTP {error.code}{suffix}") from error
        except (URLError, TimeoutError) as error:
            raise PostHogError("PostHog could not be reached") from error
        if isinstance(result, dict) and result.get("error"):
            raise PostHogError("PostHog query error: " + str(result["error"]))
        if not isinstance(result, dict):
            raise PostHogError("PostHog query returned an unexpected response")
        return result

    def rows(self, hogql: str, timeout: int = 30) -> dict[str, Any]:
        """Run a read-only HogQL query into [{column: value}, ...] rows.

        The project-scoped Query API returns the result under `results` as a
        list-of-lists aligned with `columns` (example verified live 2026-08-17:
        results [["scroll_depth", 3061], ...]). Older shapes may return object
        rows under `rows`; both are parsed defensively so an empty read is a
        real empty result, not a silently-misparsed payload.
        """
        result = self.query(hogql, timeout=timeout)
        columns = list(result.get("columns") or [])
        raw_rows = result.get("rows")
        if raw_rows is None:
            raw_rows = result.get("results") or []
        if not isinstance(raw_rows, list):
            raw_rows = []
        parsed: list[dict[str, Any]] = []
        for raw in raw_rows:
            if isinstance(raw, dict):
                parsed.append(raw)
                continue
            parsed.append({columns[index]: value for index, value in enumerate(raw)})
        return {"query_id": result.get("query_id"), "columns": columns, "rows": parsed}

    def event_counts(self, events: tuple[str, ...] = FUNNEL_EVENTS, *,
                     since: str | None = None, until: str | None = None,
                     properties: dict[str, Any] | None = None,
                     timeout: int = 30) -> dict[str, Any]:
        """Count captured funnel events read-only; absent events are `missing`.

        Events with no captured rows are reported under `missing_events`, never
        as an invented zero count: absence means the event was not captured.
        Optional `properties` filters (e.g. utm_campaign, cta_type) must use
        lowercase keys per the event taxonomy.
        """
        wanted = tuple(events) or FUNNEL_EVENTS
        rendered = ", ".join("'" + str(item).replace("'", "\\'") + "'" for item in wanted)
        where = f"event in ({rendered})"
        if since:
            where += f" and timestamp >= '{str(since).replace(chr(39), chr(92) + chr(39))}'"
        if until:
            where += f" and timestamp < '{str(until).replace(chr(39), chr(92) + chr(39))}'"
        for key, value in (properties or {}).items():
            key = str(key).replace(chr(39), chr(92) + chr(39))
            value = str(value).replace(chr(39), chr(92) + chr(39))
            where += f" and properties['{key}'] = '{value}'"
        hogql = (f"select event, count() as c from events where {where} "
                 "group by event order by event")
        payload = self.rows(hogql, timeout=timeout)
        counts = {str(row["event"]): int(row["c"]) for row in payload["rows"]
                  if "event" in row and row.get("event") is not None}
        observed = set(counts)
        return {
            "ok": True,
            "events": {event: counts[event] for event in wanted if event in counts},
            "missing_events": sorted(set(wanted) - observed),
            "query_id": payload["query_id"],
        }


def _rendition_lines(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Every delivery identity the campaign contract requires, in order.

    Each line carries the item's `template_id` from the manifest design
    order (creative dimension, v1.4.0); joined rows inherit it by spreading
    the line (`_join_buffer_refresh`), which drives the per-template funnel
    breakdown.
    """
    lines: list[dict[str, Any]] = []
    for item in (manifest or {}).get("items") or []:
        for platform in PLATFORMS:
            rendition = ((item or {}).get("renditions") or {}).get(platform) or {}
            lines.append({
                "item_id": (item or {}).get("item_id"),
                "platform": platform,
                "content_id": rendition.get("content_id"),
                "creative_signature": rendition.get("creative_signature"),
                "template_id": (rendition.get("design") or {}).get("template_id"),
            })
    return lines


METRIC_KEYS = ("views", "likes", "replies", "reposts", "shares", "followers")

# Read-only creative authority used to enumerate registered archetypes per
# platform kind (the Design registry; never modified here).
DESIGN_REGISTRY_PATH = REPO_ROOT / "company" / "departments" / "design" / "templates" / "registry.json"
# Which creative kind each channel platform draws from.
PLATFORM_TEMPLATE_KIND = {"threads": "social", "youtube": "shorts"}


def _registered_templates_by_kind() -> dict[str, list[str]]:
    """Registered archetype ids keyed by kind (registry order, read-only)."""
    try:
        registry = json.loads(DESIGN_REGISTRY_PATH.read_text(encoding="utf-8"))
    except OSError:
        return {}
    by_kind: dict[str, list[str]] = {}
    for entry in registry.get("archetypes") or []:
        by_kind.setdefault(str(entry.get("kind") or ""), []).append(str(entry.get("id") or ""))
    return by_kind


def template_breakdown(joined: list[dict[str, Any]],
                       manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Per-template platform views from the joined per-post rows.

    Honesty rules match the rest of the funnel: a template whose per-post
    views are missing stays missing (never zero), a registered archetype with
    no per-post row in the batch reports a labeled missing entry, and website
    events (content_landing, cta_clicked, leads) are batch-level only — the
    loader has no per-post tracking that would support per-template
    attribution, so that is stated rather than invented. When the manifest
    design orders are absent, the whole dimension is one labeled missing.
    """
    kinds = _registered_templates_by_kind()
    platform_orders = {platform: kinds.get(PLATFORM_TEMPLATE_KIND[platform], [])
                       for platform in PLATFORMS}
    known_templates = bool(manifest) and any(platform_orders.values())
    rows_by_key: dict[tuple[Any, str], list[dict[str, Any]]] = {}
    for row in joined:
        key = (row.get("template_id"), str(row.get("platform") or ""))
        rows_by_key.setdefault(key, []).append(row)
    per_template: list[dict[str, Any]] = []
    if known_templates:
        attributed: set[tuple[Any, str]] = set()
        for platform in PLATFORMS:
            for template_id in platform_orders[platform]:
                attributed.add((template_id, platform))
                rows = rows_by_key.get((template_id, platform), [])
                if not rows:
                    per_template.append({
                        "template_id": template_id, "platform": platform,
                        "posts": 0, "views": None, "missing": True,
                        "missing_reason": "no per-post row for this archetype in the batch",
                    })
                    continue
                missing_ids = [
                    str(row["content_id"]) for row in rows
                    if not isinstance(row["metrics"].get("views"), (int, float))
                ]
                if missing_ids:
                    per_template.append({
                        "template_id": template_id, "platform": platform,
                        "posts": len(rows), "views": None, "missing": True,
                        "missing_reason": "per-post views incomplete: " + ", ".join(missing_ids),
                    })
                else:
                    per_template.append({
                        "template_id": template_id, "platform": platform,
                        "posts": len(rows),
                        "views": sum(float(row["metrics"]["views"]) for row in rows),
                        "missing": False,
                    })
        # Defensive: joined rows whose template_id is not a registered
        # archetype of the platform kind are labeled missing, never dropped.
        stray = {key: rows for key, rows in rows_by_key.items()
                 if key not in attributed and key[1] in PLATFORMS}
        for key, rows in sorted(stray.items(), key=lambda pair: (pair[0][1], str(pair[0][0]))):
            per_template.append({
                "template_id": key[0], "platform": key[1],
                "posts": len(rows), "views": None, "missing": True,
                "missing_reason": "template_id not registered for this platform kind",
            })
    else:
        # No manifest design orders: per-template attribution is impossible.
        for platform in PLATFORMS:
            per_template.append({
                "template_id": None, "platform": platform,
                "posts": 0, "views": None, "missing": True,
                "missing_reason": "manifest design orders absent; template_id not tracked for this batch",
            })
    return {
        "basis": "manifest item design orders joined to per-post Buffer rows",
        "website_events": ("batch-level only: content_landing, cta_clicked, and leads are never "
                           "attributed per template without per-post tracking"),
        "per_template": per_template,
    }


def _join_buffer_refresh(renditions: list[dict[str, Any]],
                         delivery_receipts: list[dict[str, Any]] | None,
                         buffer_refresh: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Attach refreshed per-post metrics to each content rendition by post id."""
    refresh_by_post = {str(post.get("post_id")): post
                       for post in (buffer_refresh or {}).get("posts") or []}
    receipt_by_content = {str(receipt.get("content_id")): receipt
                          for receipt in (delivery_receipts or [])
                          if receipt.get("content_id")}
    joined: list[dict[str, Any]] = []
    for line in renditions:
        receipt = receipt_by_content.get(str(line["content_id"]))
        post_id = str((receipt or {}).get("provider_post_id") or "")
        refreshed = refresh_by_post.get(post_id) if post_id else None
        metrics = dict((refreshed or {}).get("metrics") or {})
        joined.append({
            **line,
            "provider_post_id": post_id or None,
            "provider_status": (refreshed or {}).get("status"),
            "metrics": metrics,
            "metrics_updated_at": (refreshed or {}).get("metrics_updated_at"),
            "staleness": (refreshed or {}).get("staleness", "missing")
                          if refreshed else "missing",
            "missing_metrics": [key for key, value in metrics.items() if value is None]
                               if refreshed else sorted(METRIC_KEYS),
        })
    return joined


def _funnel_entry(value: Any, source: str, *, missing_reason: str | None = None) -> dict[str, Any]:
    """One funnel count: observed with source, or missing (never zero)."""
    if missing_reason:
        return {"value": None, "source": source, "missing": True,
                "missing_reason": missing_reason}
    return {"value": value, "source": source, "missing": False}


def consume_batch_evidence(*, manifest: dict[str, Any] | None = None,
                           campaign_id: str | None = None,
                           batch_id: str | None = None,
                           delivery_receipts: list[dict[str, Any]] | None = None,
                           buffer_refresh: dict[str, Any] | None = None,
                           posthog_events: dict[str, Any] | None = None,
                           evidence_window: dict[str, Any] | None = None,
                           join_keys: tuple[str, ...] = BATCH_JOIN_KEYS) -> dict[str, Any]:
    """Join refreshed Buffer engagement and PostHog warehouse events per batch.

    This is the funnel-analysis consumption step: one campaign batch's live
    platform engagement (Buffer) plus full-capture website funnel counts
    (PostHog warehouse) joined by the preserved campaign identity chain.
    Counts that could not be observed are labeled `missing` and never
    reported as zero.
    The rendition list comes from the delivered manifest when present,
    otherwise from the delivery receipts' content ids. Since v1.4.0 the
    envelope also carries a `template_breakdown` of per-template platform
    views derived from the manifest design orders; website events remain
    batch-level only. The envelope is `technical_only` evidence; the
    canonical funnel_report handoff additionally requires complete
    full-capture business evidence before any learning conclusion (see the
    Analytics skill and README).
    """
    campaign_id = campaign_id or (manifest or {}).get("campaign_id")
    batch_id = batch_id or (manifest or {}).get("batch_id")
    if manifest:
        renditions = _rendition_lines(manifest)
    else:
        renditions = [
            {"item_id": receipt.get("item_id"), "platform": receipt.get("platform"),
             "content_id": receipt.get("content_id"),
             "creative_signature": receipt.get("creative_signature")}
            for receipt in (delivery_receipts or []) if receipt.get("content_id")
        ]
    joined = _join_buffer_refresh(renditions, delivery_receipts, buffer_refresh)

    # Buffer side: platform views must cover every rendition before a total is
    # reported; missing any rendition makes the platform total missing, not 0.
    view_values = [row["metrics"].get("views") for row in joined]
    missing_renditions = [
        f"{row['content_id']}:{key}"
        for row in joined
        for key in row["missing_metrics"]
    ]
    stale_post_ids = [str(row["provider_post_id"]) for row in joined
                      if row.get("staleness") == "stale" and row.get("provider_post_id")]
    if not renditions:
        complete_views = False
        platform_missing = "no campaign renditions to measure"
        platform_views = 0.0
    else:
        complete_views = all(isinstance(value, (int, float)) for value in view_values)
        platform_views = sum(float(value) for value in view_values
                             if isinstance(value, (int, float)))
        platform_missing = None
        if not complete_views:
            platform_missing = ("platform views incomplete; "
                                + (", ".join(missing_renditions) if missing_renditions else "no rendition reported views"))

    # PostHog side: full-capture count per funnel event; absent event is
    # missing (never an invented zero).
    events = dict((posthog_events or {}).get("events") or {})
    missing_events = sorted((posthog_events or {}).get("missing_events") or [])
    landings = events.get("content_landing")
    clicks = events.get("cta_clicked")
    # Live lead stage: the loader emits lead_form_success; the retired loader
    # names are never captured. Leads is the observed total; absent lead
    # events stay missing (never an invented zero).
    observed_lead_success = [events[name] for name in LEAD_SUCCESS_EVENTS
                             if name in events]
    leads_value = (sum(int(value) for value in observed_lead_success)
                   if observed_lead_success else None)

    funnel = {
        "platform_views": _funnel_entry(
            platform_views if complete_views else None, "buffer_refresh",
            missing_reason=platform_missing),
        "content_landings": _funnel_entry(
            landings, "posthog_warehouse",
            missing_reason=("content_landing not captured in the warehouse; "
                            "absence is missing, never zero") if landings is None else None),
        "service_cta_clicks": _funnel_entry(
            clicks, "posthog_warehouse",
            missing_reason="cta_clicked not captured in the warehouse" if clicks is None else None),
        "leads": _funnel_entry(
            leads_value, "posthog_warehouse",
            missing_reason=("no lead_form_success event captured; "
                            "absence is missing, never zero")
            if leads_value is None else None),
    }
    views = funnel["platform_views"]["value"]
    landing_count = funnel["content_landings"]["value"]
    click_count = funnel["service_cta_clicks"]["value"]
    lead_count = funnel["leads"]["value"]
    funnel["ctr"] = (landing_count / views if views and landing_count is not None else None)
    funnel["service_intent_rate"] = (click_count / landing_count
                                     if landing_count and click_count is not None else None)
    funnel["lead_conversion_rate"] = (lead_count / landing_count
                                      if landing_count and lead_count is not None else None)

    return {
        "kind": "funnel_measurement_evidence",
        "schema_version": "1.5.0",
        "campaign_id": campaign_id,
        "batch_id": batch_id,
        "join_keys": list(join_keys),
        "evidence_window": dict(evidence_window or {}),
        "technical_only": True,
        "honesty_rules": [
            "Missing counts are labeled missing, never zero",
            "An absent warehouse event is not a confirmed zero",
            "Refreshed Buffer metrics are technical_only delivery evidence",
            "Per-template platform views stay missing-labeled, never zero",
            "Website funnel events (content_landing, cta_clicked, leads) are batch-level only",
        ],
        "buffer_refresh": {
            "stale_after_hours": ((buffer_refresh or {}).get("window") or {}).get("stale_after_hours"),
            "fetched_posts": int((buffer_refresh or {}).get("count") or 0),
            "stale_post_ids": sorted(stale_post_ids),
            "missing_metric_labels": sorted(set(missing_renditions)),
            "staleness_by_rendition": {
                str(row["content_id"]): row["staleness"] for row in joined},
            "renditions": joined,
        },
        "template_breakdown": template_breakdown(joined, manifest),
        "posthog_warehouse": {
            "read_source": project_query_url(DEFAULT_PROJECT_ID),
            "events": {event: events[event] for event in FUNNEL_EVENTS if event in events},
            "missing_events": missing_events,
            "lead_funnel": {
                "lead_form_view": events.get("lead_form_view"),
                "lead_form_start": events.get("lead_form_start"),
                "lead_form_submit": events.get("lead_form_submit"),
                "lead_form_success": events.get("lead_form_success"),
                "lead_form_error": events.get("lead_form_error"),
            },
        },
        "funnel": funnel,
    }
