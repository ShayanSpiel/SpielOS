#!/usr/bin/env python3
"""Outbound email mechanical artifact validation rules.

Every prepared email must pass these before it reaches the human REVIEW
gate. This is the machine checkpoint that caught the 2026-08-09 class of
bug (segment-generic fallback copy shipping because the human rubber-
stamped the preview). It also enforces the 2026-08-10 mechanical bans:
the retired "supervised AI employees" offer line (retired_offer) and the
Rule 6 spam vocabulary (spam_word) never reach the gate. Issues are
{lead_id, code, message, skippable}: skippable issues drop that email from
the batch; structural issues hold the batch for owner attention.
"""

import re
from urllib.parse import urlparse

from . import outbound
from .compose import FORBIDDEN_OBSERVATIONS, FORBIDDEN_OFFER_PHRASES, SPAM_WORDS
from .config import (SIGNATURE_HOME, SIGNATURE_LINKEDIN, SIGNATURE_TELEGRAM,
                     SIGNATURE_X)
from .templates import SIGNATURE_HTML, SIGNATURE_TEXT

# Structural link allowance (2026-08-19 deliverability insight): every absolute
# http(s) URL in a rendered email must live on these domains, so a mismatched
# CTA (e.g. cal.com) never reaches the review gate again. Substring/host match,
# case-insensitive, on the URL's hostname.
def _allowed_link_domains() -> tuple[str, ...]:
    """Hosts configured for the signature, plus their registrable fallbacks.

    The shipped package has intentionally generic signature defaults.  A
    validator must therefore follow the configured identity rather than
    silently hard-code the source project's production domain.
    """

    defaults = {"linkedin.com", "x.com", "t.me"}
    for value in (SIGNATURE_HOME, SIGNATURE_LINKEDIN, SIGNATURE_X,
                  SIGNATURE_TELEGRAM):
        host = (urlparse(value).hostname or "").casefold()
        if host:
            defaults.add(host)
            parts = host.split(".")
            if len(parts) >= 2:
                defaults.add(".".join(parts[-2:]))
    return tuple(sorted(defaults))


def _link_domain_violations(body_html: str) -> list:
    bad = []
    allowed_domains = _allowed_link_domains()
    for url in re.findall(r"https?://[^\s\"'<>]+", body_html or ""):
        host = (urlparse(url).hostname or "").casefold()
        if not any(host == allowed or host.endswith("." + allowed)
                   for allowed in allowed_domains):
            bad.append(url)
    return bad


def sent_log_matches(recipient: str, lead_id: str, log: dict) -> bool:
    """Hard-dedup signal (goal-4357632a68): True when `recipient`
    (case-insensitive) or `lead_id` already appears in the sent log's `sent`
    list (matched against each entry's `email` and `lead_id` fields). Shared
    by the validator's non-skippable resend_guard issue and the actor's
    fail-fast gate so both gates use exactly the same match semantics."""
    recipient = str(recipient or "").casefold()
    lead_id = str(lead_id or "")
    for item in (log or {}).get("sent", []):
        if str(item.get("email") or "").casefold() == recipient:
            return True
        if str(item.get("lead_id") or "") == lead_id:
            return True
    return False


def _text_only(body_text: str) -> str:
    return body_text.replace(SIGNATURE_TEXT, "").strip()


def validate(ctx, batch: dict) -> list:
    issues = []
    sent_log = outbound.load_sent_log()
    for e in batch.get("emails", []):
        lead_id = e.get("lead_id", "?")
        subject = e.get("subject") or ""
        body_text = _text_only(e.get("body_text") or "")
        body_html = e.get("body_html") or ""

        if not subject or not body_text or not body_html:
            issues.append({"lead_id": lead_id, "code": "empty_render",
                           "message": "subject/body missing", "skippable": True})

        lower = (subject + " " + body_text).casefold()
        for obs in FORBIDDEN_OBSERVATIONS:
            if obs in lower:
                issues.append({"lead_id": lead_id, "code": "segment_fallback",
                               "message": f"segment-generic observation detected: {obs!r}",
                               "skippable": True})
        for phrase in FORBIDDEN_OFFER_PHRASES:
            if phrase in lower:
                issues.append({"lead_id": lead_id, "code": "retired_offer",
                               "message": f"retired offer phrase detected: {phrase!r}",
                               "skippable": True})
        for word in SPAM_WORDS:
            if word in lower:
                issues.append({"lead_id": lead_id, "code": "spam_word",
                               "message": f"spam word detected: {word!r}",
                               "skippable": True})

        words = len(body_text.split())
        if words > 85:
            issues.append({"lead_id": lead_id, "code": "over_word_limit",
                           "message": f"body {words} words > 85", "skippable": True})
        if "\u2014" in subject + body_text:
            issues.append({"lead_id": lead_id, "code": "em_dash",
                           "message": "em dash found in rendered copy", "skippable": True})
        if "http" in subject + body_html.replace(SIGNATURE_HTML, ""):
            issues.append({"lead_id": lead_id, "code": "external_link",
                           "message": "external link outside the signature", "skippable": True})

        for url in _link_domain_violations(body_html):
            issues.append({"lead_id": lead_id, "code": "link_domain",
                           "message": ("link outside configured signature domains "
                                       f"({', '.join(_allowed_link_domains())}): {url}"),
                           "skippable": False})

        # Hard dedup process gate (goal-4357632a68): a recipient
        # (case-insensitive) or lead_id already in the sent log is a
        # structural, NON-skippable violation — the whole batch is held at
        # prepare/validate, never silently skipped per lead.
        if sent_log_matches(e.get("email"), lead_id, sent_log):
            issues.append({"lead_id": lead_id, "code": "resend_guard",
                           "message": "lead/email already sent", "skippable": False})

    return issues
