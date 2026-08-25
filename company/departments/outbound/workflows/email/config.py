#!/usr/bin/env python3
"""
SpielOS Outbound — configuration.

Everything is driven by environment variables (see `company/.env.example`).
The one private company env file lives at `.spielos/.env` and is ignored.
"""

import os
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.resolve()
from .....runtime.paths import find_project_root

# Project root discovery is centralized (runtime/paths.py): SPIELOS_HOME env,
# nearest ancestor containing .spielos/state or .agents/company, else the
# vendored checkout. Works identically for the product repo and for homes
# where this package is vendored under .agents/company/.
PROJECT_ROOT = find_project_root()
AGENTS_DIR = PROJECT_ROOT / ".agents"
DATA_DIR = Path(os.environ.get(
    "SPIELOS_DATA_DIR", PROJECT_ROOT / ".spielos" / "data" / "outbound")).expanduser()
ENV_PATH = Path(os.environ.get(
    "SPIELOS_ENV_FILE", PROJECT_ROOT / ".spielos" / ".env")).expanduser()
# Machine runtime state belongs to the company harness, never source packages.
RUNTIME_DIR = Path(os.environ.get("OUTBOUND_RUNTIME_DIR", PROJECT_ROOT / ".spielos" / "state" / "outbound"))


def load_env() -> None:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


load_env()

# ── Provider ───────────────────────────────────────────────────────────────────
# resend | sendgrid | mailgun | smtp
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "resend").strip().lower()

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "").strip()
MAILGUN_API_KEY = os.environ.get("MAILGUN_API_KEY", "").strip()
MAILGUN_DOMAIN = os.environ.get("MAILGUN_DOMAIN", "").strip()
POSTMARK_API_TOKEN = os.environ.get("POSTMARK_API_TOKEN", "").strip()
POSTMARK_ACCOUNT_TOKEN = os.environ.get("POSTMARK_ACCOUNT_TOKEN", "").strip()
POSTMARK_DOMAIN = os.environ.get("POSTMARK_DOMAIN", "").strip()
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
EMAILOCTOPUS_API_KEY = os.environ.get("EMAILOCTOPUS_API_KEY", "").strip()
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "").strip()
SMTP_TLS = os.environ.get("SMTP_TLS", "true").strip().lower() in ("1", "true", "yes")

# ── Sender identity ────────────────────────────────────────────────────────────
FROM_EMAIL = os.environ.get("EMAIL_FROM", "shayan@spielos.xyz").strip()
FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Shayan Spiel").strip()
# Owner inbox: every captured human reply is forwarded here once
# (forward-on-capture in email_workflow.py).
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "shayan@spielos.xyz").strip()
# Per-provider From address: each provider must send from a domain it has
# verified (FKIM/SPF). Falling back to FROM_EMAIL only for the default provider.
PROVIDER_FROM_EMAILS = {}
for _pair in os.environ.get("PROVIDER_FROM_EMAILS", "").split(","):
    if ":" in _pair:
        _k, _v = _pair.split(":", 1)
        PROVIDER_FROM_EMAILS[_k.strip()] = _v.strip()
PROVIDER_FROM_EMAILS.setdefault("mailgun", f"shayan@{MAILGUN_DOMAIN}")
PROVIDER_FROM_EMAILS.setdefault("postmark", f"shayan@{POSTMARK_DOMAIN}")
SIGNATURE_TITLE = os.environ.get("SIGNATURE_TITLE", "Founder of SpielOS · AI Agent Architect").strip()
SIGNATURE_AVATAR_URL = os.environ.get("SIGNATURE_AVATAR_URL", "https://spielos.xyz/assets/avatars/avatar.jpg").strip()
SIGNATURE_LINKEDIN = os.environ.get("SIGNATURE_LINKEDIN", "https://linkedin.com/in/shayantawabi").strip()
SIGNATURE_X = os.environ.get("SIGNATURE_X", "https://x.com/ShayanSpiel").strip()
# Owner directive 2026-08-25: exactly FOUR links in every outbound signature:
# Home, X, LinkedIn, Telegram (@Shntwb). UTM-tagged so PostHog attributes clicks.
SIGNATURE_HOME = os.environ.get(
    "SIGNATURE_HOME",
    "https://spielos.xyz/?utm_source=outbound-email&utm_medium=email&utm_campaign=outbound-sig",
).strip()
SIGNATURE_TELEGRAM = os.environ.get("SIGNATURE_TELEGRAM", "https://t.me/Shntwb").strip()
# Superseded 2026-08-25: the Apply CTA (and earlier booking links) are retired
# from signatures entirely per owner directive. Four links only - see above.

# ── Data ───────────────────────────────────────────────────────────────────────
def _resolve_path(value: str, default: str, base: Path = DATA_DIR) -> Path:
    p = Path(os.environ.get(value, default)).expanduser()
    return p if p.is_absolute() else base / p


DATABASE_PATH = _resolve_path(
    "EMAIL_LIST_PATH",
    "leads.xlsx",
)
SENT_LOG_PATH = _resolve_path("SENT_LOG_PATH", "sent.json", base=RUNTIME_DIR)
CONTENT_PATH = _resolve_path("CONTENT_PATH", "content_variables.json", base=RUNTIME_DIR)
SHEET_NAME = os.environ.get("EMAIL_SHEET_NAME", "Master Outreach").strip()

# ── Behavior ───────────────────────────────────────────────────────────────────
# 50 emails in 2 hours = 1 email every 144s (owner cadence 2026-08-08).
THROTTLE_SECONDS = float(os.environ.get("THROTTLE_SECONDS", "144"))
BLOCK_SIZE = int(os.environ.get("BLOCK_SIZE", "50"))
VARIANT_ROTATE = int(os.environ.get("VARIANT_ROTATE", "10"))
PERSONALIZATION_HOOK_MAX_LEN = 200


def validate() -> None:
    missing = None
    if EMAIL_PROVIDER == "resend":
        if not RESEND_API_KEY:
            missing = "RESEND_API_KEY"
    elif EMAIL_PROVIDER == "sendgrid":
        if not SENDGRID_API_KEY:
            missing = "SENDGRID_API_KEY"
    elif EMAIL_PROVIDER == "mailgun":
        if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
            missing = "MAILGUN_API_KEY / MAILGUN_DOMAIN"
    elif EMAIL_PROVIDER == "smtp":
        if not SMTP_HOST:
            missing = "SMTP_HOST"
    else:
        raise SystemExit(f"ERROR: unknown EMAIL_PROVIDER '{EMAIL_PROVIDER}' (resend|sendgrid|mailgun|smtp)")

    if missing:
        raise SystemExit(
            f"ERROR: {missing} not set for provider '{EMAIL_PROVIDER}'. "
            f"Add it to {ENV_PATH} (see company/.env.example)."
        )

    if not DATABASE_PATH.exists():
        raise SystemExit(f"ERROR: email list not found at {DATABASE_PATH}. Set EMAIL_LIST_PATH.")

# ── Email Data (analytics) ───────────────────────────────────────────────────
# Where per-email provider status + recorded replies are stored
METRICS_PATH = _resolve_path("METRICS_PATH", "metrics.json", base=RUNTIME_DIR)
# How often `metrics` re-checks provider status (hours). Cron-friendly: the
# command exits early when the last check is fresher than this.
METRICS_INTERVAL_HOURS = float(os.environ.get("METRICS_INTERVAL_HOURS", "12"))

# ── Goals (Email Data feedback loop) ─────────────────────────────────────────
# The loop keeps working until these are met (see strategy.py).
# 2026-08-08: goals raised from fidelity data: delivery 0.95→0.99, open 0.30→0.80,
# reply 0.10→0.30, bounce ceiling 0.04→0.02 (industry: bounce <2% ideal, Instantly 2026).
GOAL_REPLY_RATE = float(os.environ.get("GOAL_REPLY_RATE", "0.30"))       # replies / sent — THE goal
GOAL_OPEN_RATE = float(os.environ.get("GOAL_OPEN_RATE", "0.80"))         # opened / delivered
GOAL_CLICK_RATE = float(os.environ.get("GOAL_CLICK_RATE", "0.05"))       # clicked / delivered
GOAL_DELIVERED_RATE = float(os.environ.get("GOAL_DELIVERED_RATE", "0.99"))  # delivered / sent
MAX_BOUNCE_RATE = float(os.environ.get("MAX_BOUNCE_RATE", "0.02"))       # bounced / sent (industry: <2%)
MAX_SPAM_RATE = float(os.environ.get("MAX_SPAM_RATE", "0.0008"))         # complained / sent (Resend free limit)

# ── Send cadence (deterministic, see SKILL.md Part 4 "Deterministic sending rules") ──
# One batch is BATCH_SIZE emails spaced THROTTLE_SECONDS apart (default 1 email
# every 10 minutes = 50 min per 6-batch). Benchmarks (Instantly 2026, ReachIQ 2026)
# favor <80-word emails and steady pacing.
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "6"))
# Phase ceilings (env-driven so the account can top up all provider daily
# limits once warmup allows). The REAL guardrails are per-provider daily caps
# (PROVIDER_DAILY_CAPS) + halt conditions (bounce/spam/delivery/429) — the
# phase cap only picks the *total* volume across providers.
#   day <= 14: WARMUP_DAILY_CAP   (default 30, owner set 200 on 2026-08-08)
#   day 15-28: RAMP_DAILY_CAP     (default 60)
#   day 29+  : STEADY_DAILY_CAP   (default 100)
DAILY_CAP_HARD = 100
MONTHLY_CAP_HARD = 3000
WARMUP_DAILY_CAP = int(os.environ.get("WARMUP_DAILY_CAP", "200"))
RAMP_DAILY_CAP = int(os.environ.get("RAMP_DAILY_CAP", "200"))
STEADY_DAILY_CAP = int(os.environ.get("STEADY_DAILY_CAP", "200"))

# ── Multi-provider sending (scaling) ─────────────────────────────────────────
# Ordered list of enabled send providers (first = default). Every provider in
# this list must have working credentials in .env (SENDGRID_API_KEY,
# MAILGUN_API_KEY + MAILGUN_DOMAIN, SMTP_*). Each one uses its own verified
# sending identity/domain. Send rotation picks the provider with the most
# daily headroom (provider caps below); a provider at its cap is skipped, the
# batch degrades gracefully.
SEND_PROVIDERS = [p.strip() for p in
                  os.environ.get("SEND_PROVIDERS", EMAIL_PROVIDER).split(",") if p.strip()]
# Deterministic per-provider daily ceilings (free tiers, 2026):
#   resend 100/day · sendgrid 100/day · mailgun 500/day · smtp discretionary
PROVIDER_DAILY_CAPS = {}
for _pair in os.environ.get("PROVIDER_DAILY_CAPS", "").split(","):
    if ":" in _pair:
        _k, _v = _pair.split(":", 1)
        try:
            PROVIDER_DAILY_CAPS[_k.strip()] = int(_v.strip())
        except ValueError:
            pass
PROVIDER_DAILY_CAPS.setdefault("resend", 100)
PROVIDER_DAILY_CAPS.setdefault("sendgrid", 100)
PROVIDER_DAILY_CAPS.setdefault("mailgun", 100)
PROVIDER_DAILY_CAPS.setdefault("postmark", 400)   # owner-approved 2026-08-10: 400/day
PROVIDER_DAILY_CAPS.setdefault("brevo", 300)
PROVIDER_DAILY_CAPS.setdefault("smtp", 200)
# Total daily ceiling from the enabled providers' free caps (topped up
# 2026-08-08: resend 100 + mailgun 100 + brevo 300 (+ sendgrid/posti if keyed).
PROVIDER_DAILY_TOTAL = sum(
    PROVIDER_DAILY_CAPS.get(p, 100) for p in SEND_PROVIDERS
)

# ── Send cadence (deterministic — see SKILL Part 4 "Deterministic sending rules") ──
# One batch is BLOCK_SIZE emails spaced THROTTLE_SECONDS apart. Benchmarks
# (Instantly 2026, ReachIQ 2026) favor <80-word emails and steady pacing.

# ── Replies ───────────────────────────────────────────────────────────────────
# Reply-To on outbound emails: point this at a Resend receiving domain
# (e.g. replies@in.spielos.xyz) so replies are auto-detected on every
# `metrics` run. Leave empty for no Reply-To (replies land in the From
# inbox and are recorded with `record-reply`).
REPLY_TO = os.environ.get("REPLY_TO", "").strip()
# Unified reply capture (owner direction 2026-08-10): every send sets
# Reply-To: replies@spielos.xyz; Cloudflare Email Routing forwards that
# address to the founder inbox; REPLY_CAPTURE=gmail_imap makes the runtime
# read that Gmail inbox over IMAP (no receiving domain, no plan upgrade).
REPLY_CAPTURE = os.environ.get("REPLY_CAPTURE", "").strip().lower()
GMAIL_IMAP_USER = os.environ.get("GMAIL_IMAP_USER", "").strip()
GMAIL_IMAP_APP_PASSWORD = os.environ.get("GMAIL_IMAP_APP_PASSWORD", "").strip()
# How far back the Gmail reply sweep looks (hours).
REPLY_LOOKBACK_HOURS = float(os.environ.get("REPLY_LOOKBACK_HOURS", "96") or 96)
# Comma-separated subject markers that identify auto-replies (out-of-office,
# etc.) — recorded but excluded from the reply-rate goal.
AUTO_REPLY_KEYWORDS = os.environ.get(
    "AUTO_REPLY_KEYWORDS",
    "out of office,out of the office,automatic reply,auto reply,auto-reply,vacation",
).strip()

# ── Analytics behavior ────────────────────────────────────────────────────────
# Cache of provider-host IPs so flaky DNS/VPN can be bypassed (see providers.py)
IP_CACHE_PATH = _resolve_path("IP_CACHE_PATH", "ip_cache.json", base=RUNTIME_DIR)
# Minimum sample before rates are trusted / variants compared
MIN_TOTAL_SAMPLE = int(os.environ.get("MIN_TOTAL_SAMPLE", "10"))
MIN_VARIANT_SAMPLE = int(os.environ.get("MIN_VARIANT_SAMPLE", "5"))

# ── Goals ─────────────────────────────────────────────────────────────────────
# Single source of truth for workflow targets (strategy.py). Each entry:
#   name, metric (key in analytics.aggregate), target, kind ("floor" = higher
#   is better; "ceiling" = lower is better), stage, severity, action text.
# Add a goal here (or via GOAL_*/MAX_* env vars) and the loop will enforce it.
GOALS = [
    {
        "name": "reply rate",
        "metric": "reply_rate",
        "target": GOAL_REPLY_RATE,
        "kind": "floor",
        "stage": "reply",
        "severity": "high",
        "action": "rewrite the question so only this lead can answer it, sharpen the offer, "
                  "cut anything generic (Part 1: Rules 3, 4, 7)",
    },
    {
        "name": "open rate",
        "metric": "open_rate",
        "target": GOAL_OPEN_RATE,
        "kind": "floor",
        "stage": "open",
        "severity": "medium",
        "action": "work the subject lines: 2-5 words, name the topic in the reader's vocabulary, "
                  "no spam words (Part 1: Rule 2)",
    },
    {
        "name": "click rate",
        "metric": "click_rate",
        "target": GOAL_CLICK_RATE,
        "kind": "floor",
        "stage": "click",
        "severity": "medium",
        "action": "make the CTA unmissable: one link, one action, a line that tells them "
                  "what happens when they click",
    },
    {
        "name": "delivered rate",
        "metric": "delivered_rate",
        "target": GOAL_DELIVERED_RATE,
        "kind": "floor",
        "stage": "deliverability",
        "severity": "medium",
        "action": "verify DNS records, check provider deliverability insights, keep the list clean",
    },
    {
        "name": "bounce rate",
        "metric": "bounce_rate",
        "target": MAX_BOUNCE_RATE,
        "kind": "ceiling",
        "stage": "deliverability",
        "severity": "high",
        "action": "verify emails before sending (see provider bounce reasons), check SPF/DKIM/DMARC",
    },
    {
        "name": "spam rate",
        "metric": "spam_rate",
        "target": MAX_SPAM_RATE,
        "kind": "ceiling",
        "stage": "deliverability",
        "severity": "high",
        "action": "slow the throttle, warm up the domain, cut spammy phrasing from the templates",
    },
]
