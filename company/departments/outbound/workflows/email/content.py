#!/usr/bin/env python3
"""Outbound email content banks (subject/body/CTA variants per segment).

The Department can only touch copy through these banks: a lever change is a
one-key JSON edit (data/content_variables.json), never a code rewrite.
Banks live in data, defaults below are re-seeded when a bank is empty.
"""

import json

from . import config

DEFAULT_CONTENT = {
    "subject_patterns": {
        "recruitment-workflow": [
            "Staffing loop at {company}",
            "Recruiting ops at {company}",
            "Screening loop at {company}",
            "Shortlist stage at {company}",
        ],
        "agency-delivery": [
            "Delivery loop at {company}",
            "Client work at {company}",
            "Handoff time at {company}",
            "Drafts at {company}",
        ],
        "saas-ops": [
            "Support loop at {company}",
            "Inbox triage at {company}",
            "Request queue at {company}",
        ],
        "generic-workflow": [
            "One workflow at {company}",
            "Manual loop at {company}",
            "Repetitive work at {company}",
        ],
    },
    "body_variants": {},
    "cta_variants": {},
}


def load_content() -> dict:
    if config.CONTENT_PATH.exists():
        try:
            with open(config.CONTENT_PATH) as f:
                data = json.load(f)
            for k, v in DEFAULT_CONTENT.items():
                if k not in data or not data[k]:
                    data[k] = v
            return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONTENT))


def save_content(data: dict) -> None:
    with open(config.CONTENT_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def subject_bank_for(segment_key: str, content: dict | None = None) -> list:
    data = content or load_content()
    return data.get("subject_patterns", {}).get(segment_key) or data.get(
        "subject_patterns", {}).get("generic-workflow", [])


def rotate_bank(segment_key: str, note: str = "") -> list:
    """Rotate the segment's subject bank (first -> last). Returns the new
    active first subject. This is the subject lever's mechanical effect."""
    data = load_content()
    bank = data.get("subject_patterns", {}).get(segment_key) or \
        list(data.get("subject_patterns", {}).get("generic-workflow", []))
    if len(bank) > 1:
        rotated = bank[1:] + bank[:1]
        data.setdefault("subject_patterns", {})[segment_key] = rotated
        save_content(data)
    return bank[1:] + bank[:1] if len(bank) > 1 else bank
