#!/usr/bin/env python3
"""Outbound email composition used during the company runtime's ACT stage.

STRICT (owner rule 2026-08-09): an email is only composed when the lead's
research columns compose real, per-lead content (parseable hook + a
pain_hypothesis that is NOT an auto-generated placeholder). No research ->
skip with a reason. The segment-observation fallback that produced generic
copy is DELETED: unprepared leads never reach an inbox, and validators
(validators.py) mechanically reject any artifact that still contains a
segment-generic observation sentence.

OFFER (owner direction 2026-08-10): the harness IS the offer and IS the
company — positioning is "building agentic companies and departments". The
retired "supervised AI employees" offer line is replaced by four A/B variants
(OFFER_VARIANTS), rotated per lead with the VARIANT_ROTATE cadence and tagged
in the composed email features so reply-rate A/B is measurable per variant.
validators.py mechanically bans the retired phrase so it can never ship again
from any render path.

SPAM (owner rule 2026-08-10): the Rule 6 banned vocabulary (SPAM_WORDS) is a
hard ban — render_checked rejects any English subject/body containing one and
validators.py flags it mechanically, so spammy phrasing never reaches the
REVIEW gate.

PROVEN PATTERN (owner rule 2026-08-18, goal-bbdb31c1b0): the only sendable
English class is a researched owner-operator lead with firm-specific pain and
a per-lead hook (strategy.md PROVEN PATTERN RULES 1-4, locked 2026-08-18).
The bulk-framework anti-pattern — list-signature titles ("Named framework
contact"), segment-generic pain repeated verbatim across leads, and GCA CSV
bulk sources — produced 0 replies / 3 clicks at 51% opens (324-run) and is
rejected here as "unprepared" so it can never reach an inbox. The proven
class (EN-1358 SDG Accountant, EN-1157 Sigma Recruitment) still composes.
The Persian template ladder is untouched: the gate guards the English STRICT
path only.
"""

import html as html_mod
import re

from . import config
from . import content as content_bank
from . import outbound
from .templates import SIGNATURE_HTML, SIGNATURE_TEXT

ALLOWED_RECS = {"Routing email only", "Ready to personalized", "Research and verify"}
FORBIDDEN = {"Backup; wait", "Do not automate"}

TIER_ORDER = {
    "Verified": 0,
    "Catch-all; unverified": 1,
    "Publicly listed; not deliverability-verified": 2,
}
UNSENDABLE = ("Bounced; suppressed", "Invalid", "Bounced")

# Placeholder pain marker: auto-generated research ("The company likely has
# ...") is NOT per-lead evidence — such leads are unprepared and are skipped.
PLACEHOLDER_PAIN_MARKER = "the company likely has"

# Segment-generic observation sentences that must never appear in a rendered
# email. VALIDATE bans these mechanically (the 2026-08-09 incident: the
# fallback produced "Recruitment runs on repeated shortlisting..." for an
# unresearched lead and it shipped).
FORBIDDEN_OBSERVATIONS = (
    "recruitment runs on repeated shortlisting",
    "delivery runs on repeated drafts",
    "support and product feedback get triaged by hand",
    "every scaling business has one repetitive workflow",
    "staffs {segment} roles for {country} clients",
)

# Retired offer phrasing (owner direction 2026-08-10: the harness IS the
# offer and IS the company). VALIDATE bans these mechanically from every
# render so the old "supervised AI employees" line can never ship again,
# from STRICT compose or the legacy template ladder.
FORBIDDEN_OFFER_PHRASES = (
    "supervised ai employees",
)

# Spam-word hard ban (outbound-email SKILL.md, Part 1 Rule 6): the banned
# vocabulary and classic spam triggers must never appear in a rendered
# English subject/body. render_checked rejects English renders containing
# one; VALIDATE flags it mechanically (code "spam_word") so the human
# REVIEW gate never sees spammy copy even from a hand-edited template.
SPAM_WORDS = (
    # Rule 6 hard-banned words.
    "leverage", "streamline", "optimize", "elevate", "empower",
    "ai-powered", "cutting-edge", "game-changing", "revolutionary",
    "i wanted to reach out", "i'm reaching out", "i am reaching out",
    "hope this finds you well", "circle back", "2x output", "half the cost",
    "cost-effective",
    # Deceptive-urgency and fake-scarcity triggers.
    "act now", "limited time", "click here", "buy now",
    "only 3 slots", "free trial", "no obligation",
)

# Owner direction 2026-08-10 offer variants — the company line is "building
# agentic companies and departments", one workflow at a time, supervised by
# the buyer's people. Rotated per lead and tagged as offer-1..offer-4 in the
# composed email features so reply-rate A/B is measurable.
OFFER_VARIANTS = (
    "I build agentic companies - {company} loop carried end to end by supervised AI agents, with your people approving each step.",
    "SpielOS is an agentic department that runs on its own harness; I build the same supervised agent departments for companies like {company}.",
    "I build agentic departments: your ops workflow running as supervised agents, a person in the loop on every step.",
    "I build agentic companies and departments. One workflow at a time, supervised by your team, starting with the most manual loop at {company}.",
)


# ── Proven-pattern gate (owner rule 2026-08-18, goal-bbdb31c1b0) ──────────────
# strategy.md PROVEN PATTERN RULES 1-4 (locked 2026-08-18): a lead is
# NON-SENDABLE ("unprepared") until it has a real owner-operator title, a
# firm-specific pain_hypothesis, a per-lead hook, and a researched source.
# The 324-run GCA bulk cohort (EN-1419/1508/1834 style) — title "Named
# framework contact", segment-generic verbatim pain, source "GCA framework
# public supplier contacts" CSV — produced 0 replies / 3 clicks at 51% opens;
# those signatures are rejected deterministically here.

# Titles that identify a bulk-list export row rather than an owner-operator.
# A lead whose title/role is one of these has no real title to greet and is
# treated exactly like a missing title.
_LIST_SIGNATURE_TITLE_MARKERS = (
    "named framework contact",
    "framework contact",
    "named contact",
    "list contact",
    "supplier contact",
    "bulk contact",
)

# Framework/list identifiers used by bulk supplier exports (GCA CSVs:
# RM6281, RM6376, RM6281:2, RM6376%3A1 ...). Present in a pain hypothesis or
# source URL, they mark segment-generic/bulk-list data, not per-lead research.
_FRAMEWORK_ID_RE = re.compile(r"RM\d+[:]?\d*", re.IGNORECASE)

# Bulk-list source signatures (RULE 1.2): a public framework/supplier export
# is not a sendable source by itself. Company-website and Director-web-
# research sources never match these.
_BULK_SOURCE_MARKERS = (
    "gca ",
    "framework public supplier",
    "framework supplier contacts",
    "public supplier contacts",
    "supplier contacts",
    "bulk framework",
    "bulk list",
    "csv export",
    "public supplier list",
)


def _normalize_pain(text: str) -> str:
    """Task-specified normalization for comparing pain hypotheses: lowercase
    and strip every non-alphanumeric character."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").casefold())


# Known segment-generic pain signatures: verbatim sentences repeated across
# bulk leads (0-reply GCA cohort) plus the FORBIDDEN_OBSERVATIONS sentences
# that must never appear in a render. Stored normalized; a pain is rejected
# when its normalized form matches one of these exactly OR contains an
# RM#### framework identifier. Template sentences with {placeholders} are
# excluded — their literal form never appears in a real pain.
SEGMENT_GENERIC_PAINS = frozenset(
    _normalize_pain(p) for p in FORBIDDEN_OBSERVATIONS if "{" not in p
) | frozenset(_normalize_pain(p) for p in (
    # 324-run GCA cohort (EN-1419/EN-1834, EN-1508): segment-generic pain
    # repeated verbatim across leads, 0 replies / 3 clicks at 51% opens.
    "Clinical and healthcare staffing runs on manual candidate sourcing, "
    "compliance handling and placement administration per role.",
    "Supply teacher and support staff placement runs on manual candidate "
    "matching, school chasing and compliance tracking per booking.",
))


def _source_is_bulk_list(contact: dict) -> bool:
    """True when source/source_url identifies an unresearched bulk export
    (GCA framework CSV pattern and similar), not a per-lead researched
    source. RULE 1.2: bulk lists are not a sendable source by themselves."""
    src = (contact.get("source") or "").casefold()
    url = (contact.get("source_url") or "").casefold()
    if any(m in src for m in _BULK_SOURCE_MARKERS):
        return True
    if url:
        if ".csv" in url or "lot-suppliers" in url or "/agreements/" in url:
            return True
        if _FRAMEWORK_ID_RE.search(url):
            return True
    return False


def _proven_pattern_violation(contact: dict) -> str | None:
    """STRICT proven-pattern gate (strategy.md RULES 1-4, locked 2026-08-18):
    a sendable English lead must have a real owner-operator title, a
    firm-specific pain, and a researched (non-bulk) source. Returns an
    'unprepared' skip reason, or None when the lead may proceed to compose."""
    title = (contact.get("title") or "").casefold()
    if any(m in title for m in _LIST_SIGNATURE_TITLE_MARKERS):
        return ("unprepared: title is a list/framework signature with no real "
                "owner-operator title — prepare content before send")
    pain = (contact.get("pain_hypothesis") or "").strip()
    if pain and (
        _FRAMEWORK_ID_RE.search(pain)
        or _normalize_pain(pain) in SEGMENT_GENERIC_PAINS
    ):
        return ("unprepared: pain_hypothesis is segment-generic, not "
                "firm-specific — prepare content before send")
    if _source_is_bulk_list(contact):
        return ("unprepared: source is an unresearched bulk supplier list — "
                "prepare content before send")
    return None


def offer_variant_index(seq: int) -> int:
    """Deterministic per-lead A/B index, same cadence as outbound.pick_variant
    (variants[(seq // VARIANT_ROTATE) % len(variants)]): the offer flips every
    VARIANT_ROTATE leads so reply-rate A/B is measurable per variant."""
    return (seq // config.VARIANT_ROTATE) % len(OFFER_VARIANTS)


_HOOK_PERSON = re.compile(r"(?:Reference|Address)\s+(.+?)(?:'s role as|\s+by name)")
_HOOK_ROLE = re.compile(r"'s role as\s+(.+?)(?:\s+and one observable|\.)")
_HOOK_WORK = re.compile(r"Reference\s+(.+?)'s work in\s+(.+?)(?:\.|$)")
_PLACEHOLDER_TITLES = {"general / new business", "general enquiries", "named company contact"}


def segment_variant(segment: str) -> str:
    s = segment.lower()
    if "recruit" in s:
        return "recruitment-workflow"
    if "agen" in s or "digital" in s:
        return "agency-delivery"
    if "saas" in s or "softwar" in s:
        return "saas-ops"
    return "generic-workflow"


def variant_by_label(lang: str, label: str) -> dict:
    from .templates import TEMPLATES
    for v in TEMPLATES.get(lang, TEMPLATES["English"]):
        if v["label"] == label:
            return v
    return None


def _hook_fields(contact: dict) -> dict:
    """Extract per-lead research from personalization_hook. Returns
    {person, role, company_hook} where any field may be None."""
    hook = contact.get("personalization_hook") or ""
    person = None
    role = None
    company_hook = None
    m = _HOOK_PERSON.search(hook)
    if m:
        person = m.group(1).strip().strip("'")
        role = contact.get("title") or ""
        rm = _HOOK_ROLE.search(hook)
        if rm:
            role = rm.group(1).strip().rstrip(".")
        if role.lower() in _PLACEHOLDER_TITLES:
            role = None
    wm = _HOOK_WORK.search(hook)
    if wm and not person:
        company_hook = wm.group(2).strip().rstrip(".")
    if person and person.lower() in (contact.get("company") or "").lower():
        person = None
    return {"person": person, "role": role, "company_hook": company_hook}


_SEGMENT_Q = {
    "recruitment-workflow": (
        "If that loop is still manual at {company}, I'd be happy to map it "
        "with you. What do you think?",
        "",
    ),
    "agency-delivery": (
        "If either of those is still manual at {company}, I'd be happy to map "
        "that stage with you. What do you think?",
        "",
    ),
    "saas-ops": (
        "If triage is still manual at {company}, I'd be happy to map it with "
        "you. What do you think?",
        "",
    ),
    "generic-workflow": (
        "If that loop is still manual at {company}, I'd be happy to map it "
        "with you. What do you think?",
        "",
    ),
}

_SEGMENT_SUBJECT = {
    "recruitment-workflow": "Staffing loop at {company}",
    "agency-delivery": "Delivery loop at {company}",
    "saas-ops": "Support loop at {company}",
    "generic-workflow": "One workflow at {company}",
}


def compose_researched(contact: dict, label: str, seq: int = 0) -> dict | None:
    """Research-first body: the lead's own pain_hypothesis as the observation,
    the hook's person+role as the opener, the segment question, and a
    conditional close. Returns {subject, body_html, body_text} or None when
    the lead has no usable research — the caller SKIPS the lead (no fallback)."""
    pain = (contact.get("pain_hypothesis") or "").strip().rstrip(".")
    if not pain or len(pain.split()) < 8:
        return None
    if pain.casefold().startswith(PLACEHOLDER_PAIN_MARKER):
        return None
    q, close = _SEGMENT_Q.get(label, _SEGMENT_Q["generic-workflow"])
    q = q.format(company=contact["company"])
    hook = _hook_fields(contact)
    first = outbound.get_first_name(contact) or "there"
    company = contact["company"]
    idx = offer_variant_index(seq)
    offer = OFFER_VARIANTS[idx].format(company=company)
    offer_variant = f"offer-{idx + 1}"

    if hook["person"] and hook["role"]:
        opener = f"Hi {first}, I saw you are {hook['role']} at {company}."
    elif hook["person"]:
        seg_word = "recruitment" if label == "recruitment-workflow" else "delivery"
        opener = f"Hi {first}, I have been looking at {company}'s {seg_word} work."
    elif hook["company_hook"]:
        opener = f"Hi {first}, I have been looking at {company}'s {hook['company_hook']} work."
    else:
        return None

    observation = pain.replace(" are likely ", " are ")
    observation = observation.replace(" is likely ", " is ")
    observation = observation.replace(" likely require ", " require ")
    observation = observation.replace(" likely have ", " have ")

    bank = content_bank.subject_bank_for(label)
    if bank:
        subject = bank[seq % len(bank)].format(company=company)
    else:
        subject = _SEGMENT_SUBJECT.get(label, _SEGMENT_SUBJECT["generic-workflow"]).format(company=company)
    subject = subject[:45]

    html = (
        f"<p>{html_mod.escape(opener)}</p>\n"
        f"<p>{html_mod.escape(observation)}.</p>\n"
        f"<p>{html_mod.escape(offer)}</p>\n"
        f"<p>{html_mod.escape(q)} {html_mod.escape(close)}</p>\n"
        "<p>Best,<br>Shayan</p>\n"
        "{SIGNATURE_HTML}"
    )
    text = (
        f"{opener}\n\n"
        f"{observation}.\n\n"
        f"{offer}\n\n"
        f"{q} {close}\n\n"
        "Best,\nShayan\n\n"
        "{SIGNATURE_TEXT}"
    )
    return {"subject": subject, "body_html": html, "body_text": text,
            "variant": offer_variant}


def render_checked(contact: dict, seq: int = 0) -> tuple:
    """Render subject/body for one lead. STRICT: an English lead is sent ONLY
    when it clears the proven-pattern gate (real owner-operator title,
    firm-specific pain, researched non-bulk source; strategy.md RULES 1-4)
    AND the research columns compose real content (parseable hook +
    pain_hypothesis, never a placeholder). No research -> skip with a reason.
    Persian leads use the prepared Persian template ladder.
    Returns (subject, html, text, reason) — reason None means sendable."""
    label = segment_variant(contact.get("segment") or "")
    if label in ("recruitment-workflow", "agency-delivery") and not contact.get("country"):
        label = "generic-workflow"

    lang = str(contact.get("language") or "English").strip()
    if lang == "English":
        violation = _proven_pattern_violation(contact)
        if violation:
            return (None, None, None, violation)
        composed = compose_researched(contact, label, seq)
        if composed is None:
            return (None, None, None,
                    "unprepared: no parseable hook + pain research — "
                    "prepare content before send")
        subject = outbound.render_template(composed["subject"], contact)
        body_html = outbound.render_template(composed["body_html"], contact)
        body_text = outbound.render_template(composed["body_text"], contact)
    else:
        tmpl = variant_by_label(lang, label) or outbound.pick_variant(lang, 0)
        if not tmpl:
            return (None, None, None, f"no template for language {lang}")
        subject = outbound.render_template(tmpl["subject"], contact)
        body_html = outbound.render_template(tmpl["body_html"], contact)
        body_text = outbound.render_template(tmpl["body_text"], contact)

    def _norm(s: str) -> str:
        return re.sub(r"\s*\u2014\s*", ", ", s)
    subject = _norm(subject)
    body_html = _norm(body_html)
    body_text = _norm(body_text)
    text_only = body_text.replace(SIGNATURE_TEXT, "").strip()
    html_only = body_html.replace(SIGNATURE_HTML, "")
    words = len(text_only.split())
    if words > 85:
        return None, None, None, f"body {words} words > 85"
    if "\u2014" in subject + text_only:
        return None, None, None, "em dash found"
    if lang == "English":
        lower_copy = (subject + " " + text_only).casefold()
        hit = next((w for w in SPAM_WORDS if w in lower_copy), None)
        if hit:
            return None, None, None, f"spam word {hit!r} found"
    if lang == "English" and "http" in subject + html_only:
        return None, None, None, "external link found"
    if not subject or not body_html or not body_text:
        return None, None, None, "empty render"
    return subject, body_html, body_text, None


def _email_type(email: str) -> str:
    """personal vs company: role addresses (info@, hello@, ...) are
    company-type — a known cohort feature for diagnosis."""
    local = (email or "").split("@")[0].lower()
    role = {"info", "hello", "contact", "support", "admin", "office", "sales",
            "team", "hr", "careers", "jobs", "enquiries", "mail", "noreply",
            "business", "billing"}
    if local in role or local.startswith(("info.", "hello.", "contact.")):
        return "company"
    return "personal"


def pick_queue(cohort_filters: dict | None = None,
               reserved_lead_ids=()) -> list:
    """Ordered, deduped send queue from the master database. Filters come
    from the owner's control knobs (min_tier, skip_unverified, language); the
    queue never lowers the ICP bar — it only deepens or shallowens by tier.
    cohort_filters.language (e.g. "English") restricts the queue to contacts
    whose language matches case-insensitively — Persian is postponed, so the
    campaign passes language="English" and no Persian email can send.

    reserved_lead_ids excludes leads already claimed by a prepared-
    not-executed batch, so concurrent prepares build disjoint batches; the
    parameter is optional for backward compatibility (report/observer call
    with filters only)."""
    filters = cohort_filters or {}
    reserved = set(reserved_lead_ids or ())
    min_tier = str(filters.get("min_tier") or "plausible").lower()
    skip_unverified = bool(filters.get("skip_unverified"))
    lang_filter = str(filters.get("language") or "").strip()
    contacts = outbound.read_contacts()
    log_data = outbound.load_sent_log()

    queued = []
    for c in contacts:
        if c["lead_id"] in reserved:
            continue
        if lang_filter and str(c.get("language") or "").strip().lower() != lang_filter.lower():
            continue
        if outbound.already_sent(c["lead_id"], log_data):
            continue
        if c["send_recommendation"] not in ALLOWED_RECS:
            continue
        if c["send_recommendation"] in FORBIDDEN:
            continue
        status = (c.get("email_status") or "").strip()
        if status in UNSENDABLE:
            continue
        if skip_unverified and status == "Publicly listed; not deliverability-verified":
            continue
        tier = TIER_ORDER.get(status, 2)
        if min_tier == "verified" and tier != 0:
            continue
        queued.append((tier, c))
    order = {"Routing email only": 0, "Ready to personalized": 1, "Research and verify": 2}
    queued.sort(key=lambda tc: (tc[0], order.get(tc[1]["send_recommendation"], 9), tc[1]["lead_id"]))
    q = [c for _t, c in queued]
    q.sort(key=lambda c: 0 if str(c.get("language") or "").strip().lower() == "english" else 1)
    return q


def build_batch_emails(batch_id: str, leads: list, hypothesis: str,
                       limit: int | None = None) -> dict:
    """Compose leads into the batch artifact. Strict mode: unprepared leads
    are skipped with a reason; domains are deduped within the batch.

    Owner order 2026-08-11 (batch floor): when `limit` is set, the WHOLE
    queue is walked and composition stops as soon as `limit` emails are
    composed — skips inside the first block (unprepared leads, same-domain
    duplicates) no longer shrink the batch. Strict rules are NEVER relaxed
    to reach the limit; when the queue cannot fill it, what is available is
    returned with queue_exhausted=true. With limit=None (default) the
    behavior is unchanged and the result is exactly
    {"emails": [...], "skipped": [...]}.

    Returns {"emails": [...], "skipped": [...], "queue_exhausted": bool}."""
    emails = []
    skipped = []
    seen_domains = set()
    for i, c in enumerate(leads):
        domain = str(c.get("email") or "").split("@")[-1].lower()
        if domain in seen_domains:
            skipped.append({"lead_id": c["lead_id"], "reason":
                            f"domain {domain} already in this batch"})
            continue
        subject, html, text, reason = render_checked(c, seq=i)
        if reason:
            skipped.append({"lead_id": c["lead_id"], "reason": reason})
            continue
        seen_domains.add(domain)
        emails.append({
            "lead_id": c["lead_id"],
            "subject": subject,
            "body_html": html,
            "body_text": text,
            "features": {
                "source": c.get("source") or "",
                "country": c.get("country") or "",
                "segment": c.get("segment") or "",
                "verified": c.get("email_status") or "",
                "email_type": _email_type(c.get("email") or ""),
                "title": c.get("title") or "",
                "variant": f"offer-{offer_variant_index(i) + 1}",
            },
        })
        if limit is not None and len(emails) >= limit:
            break
    result = {"emails": emails, "skipped": skipped}
    if limit is not None:
        result["queue_exhausted"] = len(emails) < limit
    return result
