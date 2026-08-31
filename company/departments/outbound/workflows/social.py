"""Validation boundary for agent-produced social prospects and DM drafts."""

from urllib.parse import urlparse

CHANNELS = {"linkedin", "x"}


def normalize_prospect(value: dict) -> dict | None:
    channel = str(value.get("channel") or "").strip().lower()
    profile_url = str(value.get("profile_url") or "").strip()
    sources = [str(item).strip() for item in value.get("source_urls") or [] if str(item).strip()]
    if channel not in CHANNELS or not profile_url or not _http_url(profile_url):
        return None
    if not value.get("name") or not value.get("company") or not value.get("role"):
        return None
    if not value.get("research_fact") or not value.get("operational_consequence"):
        return None
    if not sources or not all(_http_url(item) for item in sources):
        return None
    score = int(value.get("icp_score") or 0)
    if score < int(value.get("min_icp_score") or 75) or value.get("excluded"):
        return None
    return {
        "lead_id": str(value.get("lead_id") or profile_url).strip(),
        "name": str(value["name"]).strip(),
        "company": str(value["company"]).strip(),
        "role": str(value["role"]).strip(),
        "channel": channel,
        "profile_url": profile_url,
        "icp_score": score,
        "research_fact": str(value["research_fact"]).strip(),
        "operational_consequence": str(value["operational_consequence"]).strip(),
        "source_urls": sources,
    }


def normalize_dm(value: dict, prospects: dict[str, dict]) -> dict | None:
    lead_id = str(value.get("lead_id") or "").strip()
    prospect = prospects.get(lead_id)
    channel = str(value.get("channel") or (prospect or {}).get("channel") or "").strip().lower()
    message = str(value.get("message") or "").strip()
    if not prospect or channel not in CHANNELS or not message:
        return None
    limit = 500 if channel == "linkedin" else 280
    if len(message) > limit:
        return None
    fact = prospect["research_fact"].lower()
    tokens = [token for token in fact.replace("/", " ").split() if len(token) >= 5]
    if tokens and not any(token.strip(".,:;()[]").lower() in message.lower() for token in tokens[:8]):
        return None
    return {"lead_id": lead_id, "channel": channel, "message": message,
            "profile_url": prospect["profile_url"], "status": "draft"}


def prospects_from_evidence(evidence) -> list[dict]:
    values = []
    seen = set()
    for item in evidence:
        if item.get("kind") != "social_prospect":
            continue
        prospect = normalize_prospect(item.get("payload") or {})
        if prospect and prospect["lead_id"] not in seen:
            seen.add(prospect["lead_id"])
            values.append(prospect)
    return values


def drafts_from_evidence(evidence, prospects) -> list[dict]:
    by_id = {item["lead_id"]: item for item in prospects}
    values = []
    seen = set()
    for item in evidence:
        if item.get("kind") != "dm_draft":
            continue
        draft = normalize_dm(item.get("payload") or {}, by_id)
        key = (draft or {}).get("lead_id"), (draft or {}).get("channel")
        if draft and key not in seen:
            seen.add(key)
            values.append(draft)
    return values


def _http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
