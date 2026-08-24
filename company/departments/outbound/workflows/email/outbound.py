#!/usr/bin/env python3
"""
Email workflow — the campaign database library.

Reads the master outreach database (xlsx), the sent log, and the send caps.
This is the email bundle's data layer: the loop never calls it directly —
only through the workflow bundle (observer/decider/actor/evaluator).

Runtime data lives in .spielos/state/outbound/ (sent.json, metrics.json); the
master lead database stays in .spielos/data/outbound/.
"""

import json
import os
import tempfile
from datetime import datetime, timezone

from . import config

config.CONFIG_ERROR = ""
try:
    config.validate()
except SystemExit as e:
    config.CONFIG_ERROR = str(getattr(e, "code", e) or "config validation failed")

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip3 install openpyxl")
    raise SystemExit(1)

SHEET_NAME = config.SHEET_NAME

COL_MAP = {
    "lead_id": 0,
    "send_recommendation": 1,
    "outreach_tier": 2,
    "company_contact_rank": 3,
    "contactability": 4,
    "market": 5,
    "company": 6,
    "company_domain": 7,
    "contact_name": 8,
    "title": 9,
    "email": 10,
    "email_status": 11,
    "person_linkedin": 12,
    "website": 13,
    "segment": 14,
    "country": 15,
    "employees": 16,
    "annual_revenue": 17,
    "technologies": 18,
    "need_buying_signals": 19,
    "icp_confidence": 20,
    "qualification_rationale": 21,
    "pain_hypothesis": 22,
    "recommended_pilot": 23,
    "personalization_hook": 24,
    "suggested_cta": 25,
    "language": 26,
    "source": 27,
    "source_url": 28,
    "agent_instructions": 29,
    "sequence_status": 30,
    "last_checked": 31,
    "notes": 32,
    "apollo_contact_id": 33,
    "apollo_account_id": 34,
}

LANG_ALIASES = {"en": "English", "fa": "Persian", "english": "English", "persian": "Persian"}


# ── Sent log ──────────────────────────────────────────────────────────────────

def load_sent_log() -> dict:
    if config.SENT_LOG_PATH.exists():
        with open(config.SENT_LOG_PATH) as f:
            return json.load(f)
    return {"sent": [], "failed": []}


def save_sent_log(log: dict):
    """Atomic write (unique tmp + rename) — a torn file must never reach the
    next reader, and concurrent workers never collide on one shared temp path.
    The temp file is unique per writer (same directory, so os.replace stays
    atomic) and is cleaned up if the write fails."""
    fd, tmp = tempfile.mkstemp(
        dir=str(config.SENT_LOG_PATH.parent),
        prefix=config.SENT_LOG_PATH.name + ".",
        suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(log, f, indent=2, default=str)
        os.replace(tmp, config.SENT_LOG_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def already_sent(lead_id: str, log: dict) -> bool:
    return any(s.get("lead_id") == lead_id for s in log.get("sent", []))


def sent_today(log: dict, now=None) -> int:
    """Count sent entries whose timestamp is on the same UTC day as now."""
    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    return sum(1 for s in log.get("sent", []) if str(s.get("timestamp", "")).startswith(day))


def daily_cap(now=None) -> tuple:
    """Deterministic daily send cap: warmup ramp by account age, hard-capped
    by the sum of the enabled providers' free-plan daily limits.
    Returns (cap, phase)."""
    now = now or datetime.now(timezone.utc)
    log = load_sent_log()
    sent = log.get("sent", [])
    if not sent:
        cap = min(config.WARMUP_DAILY_CAP, config.PROVIDER_DAILY_TOTAL)
        return cap, f"warmup (<={cap}/day, no history)"
    first = _parse_ts(sent[0].get("timestamp"))
    if first is None:
        cap = min(config.WARMUP_DAILY_CAP, config.PROVIDER_DAILY_TOTAL)
        return cap, f"warmup (<={cap}/day)"
    age_days = (now - first).total_seconds() / 86400.0
    if age_days <= 14:
        cap = min(config.WARMUP_DAILY_CAP, config.PROVIDER_DAILY_TOTAL)
        phase = f"warmup day {age_days:.0f}/14 (<={cap}/day)"
    elif age_days <= 28:
        cap = min(config.RAMP_DAILY_CAP, config.PROVIDER_DAILY_TOTAL)
        phase = f"ramp day {age_days:.0f}/28 (<={cap}/day)"
    else:
        cap = min(config.STEADY_DAILY_CAP, config.PROVIDER_DAILY_TOTAL)
        phase = f"steady (<={cap}/day, provider hard caps)"
    return cap, phase


def _parse_ts(value):
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        return None


# ── Master database ───────────────────────────────────────────────────────────

def read_contacts(lang_filter=None, tier_filter=None):
    wb = openpyxl.load_workbook(config.DATABASE_PATH, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]
    contacts = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        if not row or not row[COL_MAP["email"]]:
            continue
        contact = {k: row[v] for k, v in COL_MAP.items()}
        contact["_row"] = i + 2

        contact["language"] = str(contact.get("language") or "English").strip()
        contact["email"] = str(contact["email"]).strip().lower()
        contact["company"] = str(contact.get("company") or "").strip()
        contact["contact_name"] = str(contact.get("contact_name") or "").strip()
        contact["title"] = str(contact.get("title") or "").strip()
        contact["domain"] = str(contact.get("company_domain") or "").strip()
        contact["website"] = str(contact.get("website") or "").strip()
        contact["country"] = str(contact.get("country") or "").strip()
        contact["segment"] = str(contact.get("segment") or "").strip()
        contact["personalization_hook"] = str(contact.get("personalization_hook") or "").strip()
        contact["suggested_cta"] = str(contact.get("suggested_cta") or "").strip()
        contact["lead_id"] = str(contact.get("lead_id") or "").strip()
        contact["sequence_status"] = str(contact.get("sequence_status") or "").strip()
        contact["send_recommendation"] = str(contact.get("send_recommendation") or "").strip()
        contact["outreach_tier"] = str(contact.get("outreach_tier") or "").strip()
        contact["email_status"] = str(contact.get("email_status") or "").strip()

        if lang_filter and contact["language"].lower() != lang_filter.lower():
            continue
        if tier_filter and contact["outreach_tier"].upper() != tier_filter.upper():
            continue

        contacts.append(contact)

    wb.close()
    return contacts


def get_first_name(contact: dict) -> str:
    name = contact.get("contact_name") or ""
    if not name:
        return ""
    return name.strip().split()[0]


def pick_variant(lang: str, index: int):
    from .templates import TEMPLATES
    variants = TEMPLATES.get(lang, TEMPLATES["English"])
    return variants[(index // config.VARIANT_ROTATE) % len(variants)]


def render_template(template_str: str, contact: dict) -> str:
    from .templates import SIGNATURE_HTML, SIGNATURE_TEXT
    first_name = get_first_name(contact)
    if not first_name:
        first_name = "there"

    return template_str.format(
        contact_name=contact.get("contact_name") or "",
        first_name=first_name,
        company=contact.get("company") or "",
        title=contact.get("title") or "",
        domain=contact.get("domain") or "",
        personalization_hook=contact.get("personalization_hook") or "",
        suggested_cta=contact.get("suggested_cta") or "",
        website=contact.get("website") or "",
        country=contact.get("country") or "",
        segment=contact.get("segment") or "",
        SIGNATURE_HTML=SIGNATURE_HTML,
        SIGNATURE_TEXT=SIGNATURE_TEXT,
    )


def templates_ready() -> bool:
    from .templates import TEMPLATES
    return all(
        "TODO" not in v["subject"] and "TODO" not in v["body_html"]
        for variants in TEMPLATES.values()
        for v in variants
    )
