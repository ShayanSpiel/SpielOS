"""Direct, approval-gated Buffer GraphQL Connection.

Buffer accepts public media URLs rather than binary uploads. This module keeps
the credential local, validates that constraint before a request, and exposes a
small explicit surface for the Content publisher and connection self-tests.

Dispatch contract: a pre-dispatch duplicate guard queries the real Buffer queue
(scheduled/sent/draft) and aborts with zero posts created when any package item
is already committed; `dispatch()` returns ok:true only when every requested
post is committed by Buffer (scheduled or sent) with per-item provider post ids
and a commitment_type, so a draft-only or partial result never produces a valid
receipt. `--queue` lists the real queue read-only for pre-dispatch verification.

`--metrics-campaign` is the read-only engagement refresh used by funnel
analysis: it lists campaign posts per channel inside an optional createdAt/dueAt
window and returns the LIVE per-post metrics (views, likes, replies, reposts,
shares, followers where the platform exposes them) together with
metricsUpdatedAt staleness, so send-time snapshots replace themselves when
refreshed data exists. Buffer reports the platform-native metric types `views`,
`reactions` (likes), `comments` (replies), `reposts`, plus service extras
(`clicks`, `impressions`, `quotes`, `engagementRate`); the normalization maps
`reactions` -> likes and `comments` -> replies so the canonical funnel keys are
populated, while counts the platform does not expose stay `missing`, never
zero. The read pages through Buffer's cursor-based posts connection
(`first`/`after`/`pageInfo`) so campaign posts beyond the first page (for
example batch-01) are reachable. ZERO write side effects; the duplicate guard
and receipt semantics are untouched.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..runtime.campaign_contract import (
    COMPATIBLE_SCHEMA_VERSIONS,
    SCHEMA_VERSION as CAMPAIGN_SCHEMA_VERSION,
    publication_package,
)


API_URL = "https://api.buffer.com"
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".spielos" / ".env"
DEFAULT_ORGANIZATION_ID = "62f24e9ed7fef68ddf794937"


class BufferError(RuntimeError):
    """A safe Buffer error message that never embeds credentials."""


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


def environment() -> dict[str, str]:
    values = _env_values()
    return {**values, **{key: value for key, value in os.environ.items() if value}}


def _public_https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise BufferError("Buffer media must use a stable public HTTPS URL")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".local"):
        raise BufferError("Buffer media URL must be publicly reachable")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return value
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise BufferError("Buffer media URL must not target a private address")
    return value


def _graphql_string(value: str) -> str:
    return json.dumps(str(value))


def _normalize_caption(value: str) -> str:
    """Turn escaped line-break markers into the paragraph breaks platforms render."""
    return str(value).replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")


def _normalize_fingerprint_text(value: str) -> str:
    """Collapse every whitespace run to one space for stable content matching."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _media_public_urls(item: dict[str, Any]) -> tuple[str, ...]:
    """Sorted, deduplicated public media URLs for one post or delivery item."""
    urls: list[str] = []
    for asset in item.get("assets") or []:
        url = str(asset.get("source") or asset.get("url") or "").strip()
        if url:
            urls.append(url)
    return tuple(sorted(set(urls)))


def content_fingerprint(item: dict[str, Any]) -> str:
    """Stable duplicate identity for one Buffer post or delivery item.

    creative_signature when present + normalized text + sorted public media
    URLs. Whitespace runs collapse so copy re-flowing never changes the
    identity; the signature keeps distinct renditions of the same copy apart
    whenever both sides carry one.
    """
    parts: list[str] = []
    signature = str(item.get("creative_signature") or "").strip()
    if signature:
        parts.append(f"sig:{signature}")
    parts.append(f"text:{_normalize_fingerprint_text(item.get('text') or item.get('description') or '')}")
    parts.extend(f"media:{url}" for url in _media_public_urls(item))
    return "|".join(parts)


def _content_matches(package_item: dict[str, Any], queue_post: dict[str, Any]) -> bool:
    """True when a delivery item is already committed in the real Buffer queue.

    The creative signature must agree whenever BOTH sides carry one (Buffer
    queue nodes never do); the normalized text and the public media URLs must
    match exactly so whitespace or line-break differences cannot hide a
    duplicate.
    """
    package_signature = str(package_item.get("creative_signature") or "").strip()
    queue_signature = str(queue_post.get("creative_signature") or "").strip()
    if package_signature and queue_signature and package_signature != queue_signature:
        return False
    if (_normalize_fingerprint_text(package_item.get("text") or "")
            != _normalize_fingerprint_text(queue_post.get("text") or "")):
        return False
    return _media_public_urls(package_item) == _media_public_urls(queue_post)


COMMITTED_STATUSES = frozenset({"scheduled", "sent"})


def commitment_type(status: str | None) -> str | None:
    """Map a Buffer post status to its publish commitment, or None.

    scheduled and sent are committed publication states; draft (and error,
    needs_approval, sending) are NOT publish commitments. A draft-only result
    must never produce a valid receipt.
    """
    normalized = str(status or "").lower()
    return normalized if normalized in COMMITTED_STATUSES else None


def _rate_limits(headers: Any) -> dict[str, str]:
    items = headers.items() if hasattr(headers, "items") else []
    return {str(key): str(value) for key, value in items
            if "rate" in str(key).lower() or "limit" in str(key).lower()}


def _posts_query(organization_id: str, channel_ids: list[str] | None,
                 with_metrics: bool, after: str | None = None,
                 first: int = 100) -> str:
    """Build the read-only posts query; with_metrics adds live engagement fields.

    Paging walks Buffer's cursor-based posts connection: `first`/`after` are
    top-level Query.posts arguments and `pageInfo` reports whether another page
    exists, so campaign posts beyond the newest page (e.g. batch-01) stay
    reachable instead of silently dropping out of the read.
    """
    ids = [str(item) for item in (channel_ids or [])]
    filter_clause = ""
    if ids:
        rendered = ", ".join(_graphql_string(item) for item in ids)
        filter_clause = f", filter: {{ channelIds: [{rendered}] }}"
    paging = ""
    if after is not None:
        paging += f"after: {_graphql_string(after)}, "
    paging += f"first: {int(first)}, "
    date_fields = " createdAt" if with_metrics else ""
    metrics_fields = " metrics { type name value unit } metricsUpdatedAt" if with_metrics else ""
    return """query GetPosts {
      posts(%sinput: { organizationId: %s%s }) {
        pageInfo { hasNextPage endCursor }
        edges { cursor node { id status dueAt sentAt%s channelId channelService text assets { id mimeType source }%s } }
      }
    }""" % (paging, _graphql_string(organization_id), filter_clause, date_fields, metrics_fields)


def _iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 Buffer timestamp; returns None when unparseable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _window_allows(value: Any, since: str | None, until: str | None) -> bool:
    """True when an ISO timestamp sits inside the optional createdAt/dueAt window."""
    if not since and not until:
        return True
    parsed = _iso_datetime(value)
    if parsed is None:
        return False
    if since:
        start = _iso_datetime(since)
        if start is None or parsed < start:
            return False
    if until:
        end = _iso_datetime(until)
        if end is None or parsed >= end:
            return False
    return True


MAX_POST_PAGES = 200  # defensive cap; real org has far fewer pages


def _walk_posts(client: BufferClient, channel_ids: list[str] | None,
                with_metrics: bool) -> list[dict[str, Any]]:
    """Walk every page of the cursor-based posts connection, deduplicated by id.

    Buffer returns only one page per request; without paging, campaign posts
    older than the newest page silently drop out of the read. This helper
    follows `pageInfo.endCursor` until `hasNextPage` is false (with a defensive
    page cap) and merges nodes by post id so the queue/guard and metrics reads
    see the complete post set.
    """
    seen: dict[str, dict[str, Any]] = {}
    cursor: str | None = None
    for _ in range(MAX_POST_PAGES):
        query = _posts_query(client.organization_id, channel_ids, with_metrics,
                             after=cursor)
        result = client.graphql(query).get("posts") or {}
        for edge in result.get("edges") or []:
            node = edge.get("node") or {}
            post_id = str(node.get("id") or "")
            if not post_id:
                continue
            existing = seen.get(post_id)
            if existing is None:
                seen[post_id] = node
            elif with_metrics and not existing.get("metrics") and node.get("metrics"):
                # A later page may carry the metrics-bearing node while the
                # first-seen duplicate is metric-free; keep the richer node.
                seen[post_id] = node
        page_info = result.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break
    return list(seen.values())


METRICS_KEYS = ("views", "likes", "replies", "reposts", "shares", "followers")

# Buffer's platform-native PostMetric types mapped onto the canonical funnel
# metric keys. `reactions` (Threads/YouTube likes) -> likes and `comments`
# (Threads/YouTube replies) -> replies so the funnel keys are populated with the
# same platform engagement; counts no platform exposes (e.g. followers/shares)
# stay missing, never zero.
BUFFER_METRIC_ALIASES = {"reactions": "likes", "comments": "replies"}


def _normalize_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Map Buffer PostMetric entries to canonical keys; absent metrics stay None."""
    by_key: dict[str, Any] = {}
    for metric in metrics or []:
        raw = str(metric.get("type") or metric.get("name") or "").strip().lower()
        key = BUFFER_METRIC_ALIASES.get(raw, raw)
        if key in METRICS_KEYS:
            by_key.setdefault(key, metric.get("value"))
    return {key: by_key.get(key) for key in METRICS_KEYS}


def metric_staleness(metrics_updated_at: Any, stale_after_hours: float,
                     now: datetime | None = None) -> str:
    """fresh|stale|missing verdict for a post's metricsUpdatedAt.

    missing: no metricsUpdatedAt (platform never reported engagement yet);
    fresh: the refresh timestamp is younger than stale_after_hours;
    stale: the last refresh lag is older than stale_after_hours and the
    reported numbers may no longer reflect the live engagement.
    """
    updated = _iso_datetime(metrics_updated_at)
    if updated is None:
        return "missing"
    age = (now or datetime.now(timezone.utc)) - updated
    return "fresh" if age < timedelta(hours=float(stale_after_hours)) else "stale"


class BufferClient:
    def __init__(self, api_key: str | None = None, organization_id: str | None = None):
        values = environment()
        self.api_key = api_key or values.get("BUFFER_API_KEY", "")
        self.organization_id = (organization_id or values.get("BUFFER_ORGANIZATION_ID")
                                or DEFAULT_ORGANIZATION_ID)
        if not self.api_key:
            raise BufferError("BUFFER_API_KEY is not configured")
        self.last_rate_limits: dict[str, str] = {}

    def graphql(self, query: str) -> dict[str, Any]:
        payload = json.dumps({"query": query}).encode("utf-8")
        request = Request(API_URL, data=payload, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
        })
        try:
            with urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS endpoint
                self.last_rate_limits = _rate_limits(response.headers)
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            self.last_rate_limits = _rate_limits(error.headers)
            raise BufferError(f"Buffer request failed with HTTP {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise BufferError("Buffer request could not reach the API") from error
        if result.get("errors"):
            raise BufferError("Buffer GraphQL error: " + "; ".join(
                str(item.get("message", "unknown error")) for item in result["errors"]))
        return result.get("data") or {}

    def channels(self) -> list[dict[str, Any]]:
        query = """query GetChannels {
          channels(input: { organizationId: %s }) { id name displayName service isQueuePaused }
        }""" % _graphql_string(self.organization_id)
        return list(self.graphql(query).get("channels") or [])

    def channel(self, service: str) -> dict[str, Any] | None:
        expected = service.lower()
        return next((item for item in self.channels()
                     if str(item.get("service", "")).lower() == expected), None)

    def post(self, post_id: str) -> dict[str, Any] | None:
        query = """query GetPost {
          post(input: { id: %s }) { id text channelId dueAt status metrics { type name value unit } metricsUpdatedAt }
        }""" % _graphql_string(post_id)
        return self.graphql(query).get("post")

    def queue_posts(self, channel_ids: list[str] | None = None,
                    statuses: tuple[str, ...] = ("scheduled", "sent", "draft")) -> list[dict[str, Any]]:
        """Read the real Buffer posting queue; never writes.

        Returns scheduled/sent/draft posts for the named channels (all channels
        when omitted) with the fields the duplicate guard and the read-only
        --queue command need: id, status, dueAt, sentAt, channelId,
        channelService, text, and asset public URLs. Walks every page of the
        posts connection so posts beyond the newest page are included.
        """
        post_nodes = _walk_posts(self, channel_ids, with_metrics=False)
        posts: list[dict[str, Any]] = []
        for node in post_nodes:
            if node.get("status") in statuses:
                posts.append(node)
        return posts

    def campaign_posts(self, channel_ids: list[str] | None = None,
                       statuses: tuple[str, ...] = ("scheduled", "sent", "draft"),
                       since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
        """Read campaign posts per channel inside a createdAt/dueAt window; never writes.

        Same read-only queue read as queue_posts (every page of the posts
        connection) but also returns createdAt and the LIVE per-post metrics
        (Post.metrics: type/name/value/unit) plus metricsUpdatedAt so funnel
        analysis can refresh engagement instead of trusting the send-time
        snapshot. Window filtering uses createdAt when present, otherwise dueAt;
        a post with neither timestamp inside the window is excluded from the
        read.
        """
        post_nodes = _walk_posts(self, channel_ids, with_metrics=True)
        posts: list[dict[str, Any]] = []
        for node in post_nodes:
            if node.get("status") not in statuses:
                continue
            created = node.get("createdAt")
            due = node.get("dueAt")
            if _window_allows(created or due, since, until):
                posts.append(node)
        return posts

    def create_post(self, *, channel_id: str, text: str, mode: str = "draft",
                    due_at: str | None = None, assets: list[dict[str, str]] | None = None,
                    metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        modes = {"draft": "addToQueue", "queue": "addToQueue", "scheduled": "customScheduled", "now": "shareNow"}
        if mode not in modes:
            raise BufferError("Buffer mode must be draft, queue, scheduled, or now")
        if mode == "scheduled" and not due_at:
            raise BufferError("A scheduled Buffer post needs an ISO-8601 due_at timestamp")
        text = _normalize_caption(text)
        fields = [f"text: {_graphql_string(text)}", f"channelId: {_graphql_string(channel_id)}",
                  "schedulingType: automatic", f"mode: {modes[mode]}"]
        if mode == "draft":
            fields.append("saveToDraft: true")
        if due_at:
            fields.append(f"dueAt: {_graphql_string(due_at)}")
        rendered_assets = []
        for asset in assets or []:
            kind = str(asset.get("type", "")).lower()
            if kind not in {"image", "video"}:
                raise BufferError("Buffer assets must be image or video URLs")
            url = _public_https_url(str(asset.get("url", "")))
            rendered_assets.append(f"{{ {kind}: {{ url: {_graphql_string(url)} }} }}")
        if rendered_assets:
            fields.append("assets: [" + ", ".join(rendered_assets) + "]")
        youtube = (metadata or {}).get("youtube") if isinstance(metadata, dict) else None
        if youtube:
            title = str(youtube.get("title") or "").strip()
            category_id = str(youtube.get("categoryId") or "").strip()
            if not title or not category_id:
                raise BufferError("YouTube posts need metadata.youtube.title and categoryId")
            fields.append(f"metadata: {{ youtube: {{ title: {_graphql_string(title)}, "
                          f"categoryId: {_graphql_string(category_id)} }} }}")
        query = """mutation CreatePost {
          createPost(input: { %s }) {
            ... on PostActionSuccess { post { id text channelId dueAt status assets { id mimeType source } } }
            ... on InvalidInputError { message }
            ... on LimitReachedError { message }
            ... on UnauthorizedError { message }
            ... on UnexpectedError { message }
          }
        }""" % ", ".join(fields)
        result = self.graphql(query).get("createPost") or {}
        post = result.get("post")
        if not post:
            raise BufferError("Buffer rejected post: " + str(result.get("message", "unknown error")))
        return post

    def delete_post(self, post_id: str) -> str:
        query = """mutation DeletePost {
          deletePost(input: { id: %s }) {
            ... on DeletePostSuccess { id }
            ... on VoidMutationError { message }
          }
        }""" % _graphql_string(post_id)
        result = self.graphql(query).get("deletePost") or {}
        deleted = result.get("id")
        if not deleted:
            raise BufferError("Buffer could not delete the post: " + str(result.get("message", "unknown error")))
        return str(deleted)

    def posting_limits(self, channel_ids: list[str]) -> list[dict[str, Any]]:
        ids = ", ".join(_graphql_string(item) for item in channel_ids)
        query = """query DailyPostingLimits {
          dailyPostingLimits(input: { channelIds: [%s] }) { channelId isAtLimit limit scheduled sent }
        }""" % ids
        return list(self.graphql(query).get("dailyPostingLimits") or [])

    def available_capacity(self, channel_ids: list[str]) -> dict[str, int | None]:
        """Return remaining daily post capacity from Buffer, never a guessed quota."""
        limits = self.posting_limits(channel_ids)
        capacity: dict[str, int | None] = {}
        for item in limits:
            channel_id = str(item.get("channelId") or "")
            if item.get("limit") is None:
                # Buffer reports no per-day cap for this channel. `None` is an
                # explicit unlimited capacity, not an invented numeric quota.
                capacity[channel_id] = 0 if item.get("isAtLimit") else None
                continue
            try:
                limit = int(item["limit"])
                scheduled = int(item.get("scheduled") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            capacity[channel_id] = max(0, limit - scheduled)
        return capacity

    def health_check(self) -> dict[str, Any]:
        channels = self.channels()
        services = {str(item.get("service", "")).lower() for item in channels}
        return {"ok": "threads" in services and "youtube" in services,
                "organization_id": self.organization_id, "channels": channels,
                "services": sorted(services), "rate_limits": self.last_rate_limits,
                "posting_limits": self.posting_limits([str(item["id"]) for item in channels
                                                       if str(item.get("service", "")).lower() in {"threads", "youtube"}])}


def _delivery_posts(package: dict[str, Any], client: BufferClient) -> list[dict[str, Any]]:
    posts = list(package.get("posts") or [package])
    if not posts:
        raise BufferError("Approved Buffer package needs one or more posts")
    resolved: list[dict[str, Any]] = []
    shared_campaign = package.get("schema_version") in COMPATIBLE_SCHEMA_VERSIONS
    if shared_campaign:
        for field in ("campaign_id", "batch_id"):
            if not package.get(field):
                raise BufferError(f"Approved campaign package needs {field}")
        if package.get("approval_required") is not True:
            raise BufferError("Campaign package must preserve the explicit approval gate")
    for item in posts:
        if not isinstance(item, dict):
            raise BufferError("Approved Buffer posts must be structured packages")
        post = dict(item)
        channel_id = str(post.get("channel_id") or post.get("channelId") or "")
        if not channel_id and post.get("platform"):
            channel = client.channel(str(post["platform"]))
            channel_id = str((channel or {}).get("id") or "")
        text = str(post.get("text") or post.get("description") or "")
        if not channel_id or not text:
            raise BufferError("Approved Buffer post needs a connected channel and text")
        if shared_campaign:
            for field in ("campaign_id", "batch_id", "item_id", "content_id",
                          "creative_signature", "platform", "approval_id"):
                if not post.get(field):
                    raise BufferError(f"Approved campaign post needs {field}")
            if post["campaign_id"] != package["campaign_id"] or post["batch_id"] != package["batch_id"]:
                raise BufferError("Campaign post identity does not match its package")
            if not list(post.get("assets") or []):
                raise BufferError("Approved campaign post needs its Design rendition")
        post["channel_id"] = channel_id
        post["text"] = text
        resolved.append(post)
    return resolved


def _publication_input(package: dict[str, Any]) -> dict[str, Any]:
    """Turn one already-approved batch handoff into the Buffer input.

    Batch review is the sole owner authorization. The asset-promotion step
    carries that decision into per-rendition IDs for provenance; this helper
    refuses anything that has not completed that promotion.
    """
    manifest = package.get("campaign_manifest") if isinstance(package, dict) else None
    if manifest is None:
        return package
    if package.get("review_required") is not True:
        raise BufferError("Campaign handoff must preserve the explicit batch approval gate")
    if not isinstance(manifest, dict) or manifest.get("phase") != "approved":
        raise BufferError("Campaign handoff needs the hosted approved campaign Artifact")
    try:
        return publication_package(manifest)
    except ValueError as error:
        raise BufferError(str(error)) from error


def _guard_duplicates(client: BufferClient, posts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pre-flight duplicate check against the real Buffer queue.

    Returns None when the package is clear to create; otherwise an ok:false
    result with zero posts created and the already-committed queue post ids.
    The guard is fail-closed: any match blocks the whole package so a
    re-dispatch can never duplicate content that is already committed.
    """
    channel_ids = sorted({str(item["channel_id"]) for item in posts})
    queue = client.queue_posts(channel_ids)
    matches: list[dict[str, Any]] = []
    for item in posts:
        for queued in queue:
            if not _content_matches(item, queued):
                continue
            matches.append({
                "item_id": item.get("item_id"), "content_id": item.get("content_id"),
                "platform": item.get("platform"),
                "creative_signature": item.get("creative_signature"),
                "fingerprint": content_fingerprint(item),
                "queue_post_id": queued.get("id"), "queue_status": queued.get("status"),
            })
    if not matches:
        return None
    return {
        "ok": False,
        "message": "Buffer queue already contains this package content; refusing duplicate dispatch",
        "duplicate_guard": "blocked",
        "existing_post_ids": sorted({str(match["queue_post_id"]) for match in matches}),
        "matches": matches,
        "rate_limits": client.last_rate_limits,
    }


def dispatch(package: dict[str, Any], execution_mode: str, *,
             client: BufferClient | None = None) -> dict[str, Any]:
    """Dispatch an already-approved publisher package; never infer a channel or text.

    Receipt semantics: ok:true ONLY when every requested post is committed by
    Buffer (status scheduled or sent) with per-item provider post ids and a
    commitment_type of "scheduled" or "sent". A pre-dispatch duplicate guard
    queries the real Buffer queue first and aborts with zero posts created if
    any package item is already committed. ok:false means zero or partial
    creation: no receipt, no goal achievement.
    """
    if execution_mode != "live":
        return {"ok": False, "message": "Buffer dispatch is a dry run; no post was created"}
    client = client or BufferClient()
    publication = _publication_input(package)
    posts = _delivery_posts(publication, client)
    blocked = _guard_duplicates(client, posts)
    if blocked is not None:
        return blocked
    channel_ids = [str(item["channel_id"]) for item in posts]
    capacity = client.available_capacity(sorted(set(channel_ids)))
    requested = {channel_id: channel_ids.count(channel_id) for channel_id in set(channel_ids)}
    unavailable = {channel_id: count for channel_id, count in requested.items()
                   if capacity.get(channel_id, 0) is not None and capacity.get(channel_id, 0) < count}
    if unavailable:
        return {"ok": False, "message": "Buffer daily posting capacity is unavailable for this package",
                "capacity": capacity, "requested": unavailable}
    created = []
    receipts = []
    for item in posts:
        created_post = client.create_post(channel_id=item["channel_id"], text=item["text"],
                                          mode=str(item.get("mode") or "draft"),
                                          due_at=item.get("due_at") or item.get("dueAt"),
                                          assets=list(item.get("assets") or []),
                                          metadata=item.get("metadata"))
        created.append(created_post)
        receipts.append({
            "campaign_id": item.get("campaign_id"), "batch_id": item.get("batch_id"),
            "item_id": item.get("item_id"), "content_id": item.get("content_id"),
            "creative_signature": item.get("creative_signature"),
            "platform": item.get("platform"), "approval_id": item.get("approval_id"),
            "provider_post_id": created_post.get("id"), "verified": bool(created_post.get("id")),
            "status": created_post.get("status"),
            "commitment_type": commitment_type(created_post.get("status")),
        })
    limits = client.posting_limits(sorted(set(channel_ids)))
    if not all(receipt["commitment_type"] for receipt in receipts):
        return {
            "ok": False,
            "message": ("Buffer did not commit every requested post; only scheduled/sent are "
                        "publish commitments, draft/error results are not"),
            "created_posts": created,
            "uncommitted": [{"item_id": receipt["item_id"], "platform": receipt["platform"],
                             "provider_post_id": receipt["provider_post_id"],
                             "status": receipt["status"]} for receipt in receipts
                            if not receipt["commitment_type"]],
            "posting_limits": limits, "rate_limits": client.last_rate_limits,
        }
    return {"ok": True, "post": created[0] if len(created) == 1 else None, "posts": created,
            "campaign_id": publication.get("campaign_id"), "batch_id": publication.get("batch_id"),
            "delivery_receipts": receipts,
            "rate_limits": client.last_rate_limits, "posting_limits": limits, "capacity_before_dispatch": capacity}


def _probe_draft(client: BufferClient) -> dict[str, Any]:
    channel = client.channel("threads")
    if not channel:
        raise BufferError("No Threads channel is connected to Buffer")
    post = client.create_post(channel_id=str(channel["id"]),
                              text="SpielOS Buffer connection check — delete this draft.", mode="draft")
    verified = client.post(str(post["id"]))
    deleted_id = client.delete_post(str(post["id"]))
    return {"ok": True, "draft_id": post["id"], "verified": bool(verified),
            "deleted_id": deleted_id, "rate_limits": client.last_rate_limits}


def _post_metrics(client: BufferClient, post_ids: list[str]) -> dict[str, Any]:
    """Read post status and metrics without returning post copy or credentials."""
    posts = []
    for post_id in post_ids:
        post = client.post(post_id)
        if not post:
            posts.append({"post_id": post_id, "found": False})
            continue
        posts.append({
            "post_id": str(post.get("id") or post_id),
            "found": True,
            "channel_id": post.get("channelId"),
            "due_at": post.get("dueAt"),
            "status": post.get("status"),
            "metrics": list(post.get("metrics") or []),
            "metrics_updated_at": post.get("metricsUpdatedAt"),
        })
    return {"ok": True, "posts": posts, "rate_limits": client.last_rate_limits}


def _queue_report(client: BufferClient, channel_ids: list[str] | None = None) -> dict[str, Any]:
    """Read-only queue listing for pre-dispatch verification and evidence."""
    posts = client.queue_posts(channel_ids)
    per_channel: dict[str, list[dict[str, Any]]] = {}
    for post in posts:
        channel_id = str(post.get("channelId") or post.get("channelService") or "unknown")
        text = _normalize_fingerprint_text(post.get("text") or "")
        per_channel.setdefault(channel_id, []).append({
            "id": post.get("id"), "status": post.get("status"),
            "due_at": post.get("dueAt"), "sent_at": post.get("sentAt"),
            "text_excerpt": text[:120] + ("…" if len(text) > 120 else ""),
            "media_urls": list(_media_public_urls(post)),
        })
    return {"ok": True, "count": len(posts), "channels": per_channel,
            "rate_limits": client.last_rate_limits}


def _metrics_campaign_report(client: BufferClient, channel_ids: list[str] | None = None,
                             since: str | None = None, until: str | None = None,
                             stale_after_hours: float = 6.0,
                             now: datetime | None = None) -> dict[str, Any]:
    """Read-only live engagement refresh for funnel analysis; never writes.

    Walks every page of the posts connection and lists campaign posts per
    channel inside the optional createdAt/dueAt window, returning the refreshed
    per-post metrics (views, likes, replies, reposts, shares, followers where
    the platform exposes them), metricsUpdatedAt staleness, and which metrics
    are missing. Buffer's native `reactions`/`comments` types map to
    likes/replies; missing counts are labeled missing (None), never zero,
    because an absent metric means the platform has not exposed it yet.
    """
    posts = client.campaign_posts(channel_ids, since=since, until=until)
    refreshed = []
    for post in posts:
        metrics = _normalize_metrics(post.get("metrics") or [])
        updated_at = post.get("metricsUpdatedAt")
        refreshed.append({
            "post_id": post.get("id"),
            "channel_id": post.get("channelId"),
            "channel_service": post.get("channelService"),
            "status": post.get("status"),
            "created_at": post.get("createdAt"),
            "due_at": post.get("dueAt"),
            "sent_at": post.get("sentAt"),
            "metrics": metrics,
            "metrics_updated_at": updated_at,
            "staleness": metric_staleness(updated_at, stale_after_hours, now=now),
            "missing_metrics": [key for key, value in metrics.items() if value is None],
        })
    return {"ok": True, "count": len(refreshed),
            "window": {"since": since, "until": until,
                       "stale_after_hours": stale_after_hours},
            "posts": refreshed, "rate_limits": client.last_rate_limits}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe direct Buffer Connection")
    parser.add_argument("--check", action="store_true", help="List connected channels; never writes")
    parser.add_argument("--probe-draft", action="store_true", help="Create, verify, and delete one Threads draft")
    parser.add_argument("--metrics", metavar="POST_ID", action="append",
                        help="Read one Buffer post's status and metrics; repeat for multiple posts")
    parser.add_argument("--queue", action="store_true",
                        help="List scheduled/sent/draft posts in the real Buffer queue; never writes")
    parser.add_argument("--metrics-campaign", action="store_true",
                        help="Refresh live per-post engagement metrics for campaign posts in a date window; never writes")
    parser.add_argument("--channel", metavar="CHANNEL_ID", action="append",
                        help="Restrict --queue or --metrics-campaign to channel ids; repeat for multiple")
    parser.add_argument("--since", metavar="ISO",
                        help="With --metrics-campaign: include posts created/due at or after this ISO-8601 time")
    parser.add_argument("--until", metavar="ISO",
                        help="With --metrics-campaign: include posts created/due before this ISO-8601 time")
    parser.add_argument("--stale-after-hours", type=float, default=None,
                        help="With --metrics-campaign: a post's metrics are stale when metricsUpdatedAt is older than this (default 6)")
    args = parser.parse_args(argv)
    selected = int(args.check) + int(args.probe_draft) + int(bool(args.metrics)) + int(args.queue) + int(args.metrics_campaign)
    if selected != 1:
        parser.error("choose exactly one of --check, --probe-draft, --metrics, --queue, or --metrics-campaign")
    if (args.since or args.until or args.stale_after_hours is not None) and not args.metrics_campaign:
        parser.error("--since, --until, and --stale-after-hours apply only to --metrics-campaign")
    try:
        client = BufferClient()
        if args.probe_draft:
            result = _probe_draft(client)
        elif args.metrics:
            result = _post_metrics(client, args.metrics)
        elif args.metrics_campaign:
            result = _metrics_campaign_report(client, args.channel, since=args.since,
                                              until=args.until,
                                              stale_after_hours=args.stale_after_hours or 6.0)
        elif args.queue:
            result = _queue_report(client, args.channel)
        else:
            result = client.health_check()
    except BufferError as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
