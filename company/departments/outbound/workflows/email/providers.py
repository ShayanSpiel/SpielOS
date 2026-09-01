#!/usr/bin/env python3
"""
Outbound Department — email provider adapters.

Sending contract:
  send_email(to_email, subject, html, text, reply_to="")
    Success:  {"id": "<provider message id>"}
    Failure:  {"error": True, "status": <int>, "message": "<detail>"}

Email Data contract (used by analytics.py / strategy.py):
  cap_status()            -> can this provider report per-email status?
  cap_list_sent()         -> can we list sent emails (id backfill)?
  cap_received()          -> can we list received emails (auto-replies)?
  fetch_email_status(id)  -> {"last_event": <canonical event>, ...}
  list_sent_emails()      -> sent emails
  list_received_emails()  -> received emails

Supported providers (EMAIL_PROVIDER env var):

  Provider  status  list_sent  received   notes
  resend    yes     yes        yes        GET /emails/{id} for status; /emails
                                         to backfill ids; /emails/receiving for
                                         replies. Key must have Full access
                                         (sending-only keys return 404 on reads).
  mailgun   yes*    no         no         events API per message-id for status.
                                         Delivery/engagement only; no listing.
  sendgrid  no      no         no         v3 send has no free read API; open/click
                                         need the Event Webhook + their plans.
  smtp      no      no         no         relays have no tracking; replies are
                                         manual only.

Canonical event vocabulary (whatever the provider calls it, every status
buckets to one of): sent, delivered, delivery_delayed, opened, clicked,
bounced, complained (marked spam), failed, suppressed, replied.

Transport resilience: every HTTP call retries with backoff, and caches the
provider host IPs so a flaky VPN / broken DNS can be bypassed on later calls
(see IP_CACHE_PATH).
"""

import base64
import email
import imaplib
import json
import os
import smtplib
import socket
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

from .config import (
    EMAIL_PROVIDER,
    IP_CACHE_PATH,
    RESEND_API_KEY,
    SENDGRID_API_KEY,
    MAILGUN_API_KEY,
    MAILGUN_DOMAIN,
    POSTMARK_API_TOKEN,
    POSTMARK_DOMAIN,
    BREVO_API_KEY,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_TLS,
    FROM_EMAIL,
    FROM_NAME,
)
from .config import SEND_PROVIDERS as _CFG_SEND_PROVIDERS
from . import config as _cfg_module

_UA = "SpielOS-Outbound/1.1"

_CAPABILITIES = {
    "resend": {"status": True, "list_sent": True, "received": True},
    "mailgun": {"status": True, "list_sent": True, "received": False},
    "brevo": {"status": True, "list_sent": False, "received": False},
    "sendgrid": {"status": False, "list_sent": False, "received": False},
    "postmark": {"status": True, "list_sent": False, "received": True},
    "smtp": {"status": False, "list_sent": False, "received": False},
}


def cap_status() -> bool:
    return _CAPABILITIES.get(EMAIL_PROVIDER, {}).get("status", False)


def cap_list_sent() -> bool:
    return _CAPABILITIES.get(EMAIL_PROVIDER, {}).get("list_sent", False)


def cap_received(provider: str = "") -> bool:
    explicit = bool(str(provider).strip())
    provider = (provider or EMAIL_PROVIDER or "").strip().lower()
    if provider == "gmail_imap":
        return bool(_cfg_module.GMAIL_IMAP_USER and _cfg_module.GMAIL_IMAP_APP_PASSWORD)
    if not explicit and _cfg_module.REPLY_CAPTURE == "gmail_imap" and provider == EMAIL_PROVIDER.strip().lower():
        return bool(_cfg_module.GMAIL_IMAP_USER and _cfg_module.GMAIL_IMAP_APP_PASSWORD)
    return _CAPABILITIES.get(provider, {}).get("received", False)


# ── Transport (retry + DNS/IP fallback) ──────────────────────────────────────

_real_getaddrinfo = socket.getaddrinfo


def _remember_ips(host: str) -> None:
    try:
        ips = _dns_fallback(host) or _cached_ips(host)
        if not ips:
            return
        cache = {}
        if IP_CACHE_PATH.exists():
            cache = json.loads(IP_CACHE_PATH.read_text())
        if cache.get(host) != ips:
            cache[host] = ips
            IP_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def _cached_ips(host: str):
    try:
        if IP_CACHE_PATH.exists():
            cache = json.loads(IP_CACHE_PATH.read_text())
            return cache.get(host) or []
    except Exception:
        pass
    return []


def _dns_skip_name(data: bytes, offset: int) -> int:
    """Walk a DNS name (handling compression pointers)."""
    while offset < len(data):
        ln = data[offset]
        if ln & 0xC0 == 0xC0:
            return offset + 2
        if ln == 0:
            return offset + 1
        offset += 1 + ln
    return offset


def _dns_query(ns: str, host: str, timeout: float = 3.0, qtype: int = 1) -> list:
    """Resolve records for host against a single nameserver (stdlib-only).
    qtype: 1 = A, 15 = MX. MX returns ('priority', 'exchange') tuples."""
    qname = b"".join(bytes([len(p)]) + p.encode() for p in host.split(".")) + b"\x00"
    tid = os.urandom(2)
    packet = tid + b"\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + bytes([0, qtype]) + b"\x00\x01"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (ns, 53))
        data, _ = sock.recvfrom(4096)
    except OSError:
        return []
    finally:
        sock.close()
    if len(data) < 12 or data[0:2] != tid or (data[3] & 0x0F) != 0:
        return []
    ancount = struct.unpack(">H", data[6:8])[0]
    if not ancount:
        return []
    offset = _dns_skip_name(data, 12) + 4
    out = []
    for _ in range(ancount):
        if offset + 10 > len(data):
            break
        offset = _dns_skip_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _rclass, _ttl, rdlen = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if rtype == qtype and qtype == 1 and rdlen == 4 and offset + 4 <= len(data):
            out.append(".".join(str(b) for b in data[offset:offset + 4]))
        elif rtype == qtype and qtype == 15:
            pref = struct.unpack(">H", data[offset:offset + 2])[0]
            # walk the exchange name with compression-pointer following
            parts = []
            p = offset + 2
            visited = set()
            while p < len(data):
                ln = data[p]
                if ln == 0:
                    p += 1
                    break
                if ln & 0xC0 == 0xC0:
                    if p in visited:
                        break
                    visited.add(p)
                    p = ((ln & 0x3F) << 8) | data[p + 1]
                    continue
                parts.append(data[p + 1:p + 1 + ln].decode("ascii", "ignore"))
                p += 1 + ln
            out.append((pref, ".".join(parts).lower()))
        offset += rdlen
    return out


def dns_mx(host: str) -> list:
    """Best-effort MX records for a domain (fresh query + cached fallback).
    Returns sorted [(priority, exchange)]; [] when the domain has no MX."""
    host = (host or "").strip().lower().lstrip(".")
    if not host:
        return []
    for ns in _NS_LIST():
        mx = _dns_query(ns, host, qtype=15)
        if mx:
            return sorted(mx, key=lambda t: t[0])
    return []


def dns_has_mx(host: str) -> bool:
    return bool(dns_mx(host))


def _NS_LIST() -> list:
    nameservers = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
    try:
        for line in open("/etc/resolv.conf"):
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                ns = parts[1]
                if ns not in nameservers:
                    nameservers.append(ns)
    except OSError:
        pass
    return nameservers


def _dns_fallback(host: str) -> list:
    """Resolve via public resolvers when the OS resolver is broken
    (macOS loses its DNS config when a VPN disconnects — Errno 8)."""
    nameservers = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
    try:
        for line in open("/etc/resolv.conf"):
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                ns = parts[1]
                if ns not in nameservers:
                    nameservers.append(ns)
    except OSError:
        pass
    for ns in nameservers:
        ips = _dns_query(ns, host)
        if ips:
            return ips
    return []


def _dns_fresh(host: str) -> list:
    """Raw-DNS answer (bounded, ~3s per server). Never touches the OS resolver,
    which can hang without bound when the system DNS stack is dead."""
    return _dns_fallback(host)


def _dns_broken() -> bool:
    try:
        if IP_CACHE_PATH.exists():
            return bool(json.loads(IP_CACHE_PATH.read_text()).get("system_dns_broken"))
    except Exception:
        pass
    return False


def _mark_dns_broken(broken: bool = True) -> None:
    try:
        cache = {}
        if IP_CACHE_PATH.exists():
            cache = json.loads(IP_CACHE_PATH.read_text())
        cache["system_dns_broken"] = bool(broken)
        IP_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def _system_resolve_bounded(host: str, cap: float = 15.0) -> list:
    """socket.getaddrinfo cannot be timed out, so probe the system resolver in
    a daemon thread with a hard cap. Returns [] if it hangs past the cap."""
    box = {}

    def _run():
        try:
            box["ips"] = [r[4][0] for r in _real_getaddrinfo(host, 443, socket.AF_INET)]
        except Exception:
            box["ips"] = []

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(cap)
    return box.get("ips", []) if not t.is_alive() else []


def _try_ips(url: str, headers: dict, payload, method: str, host: str) -> dict:
    """Attempt the request via fresh raw-DNS IPs (then the cache). Bounded:
    raw DNS caps at ~3s/server, HTTP at 30s, and the system resolver is never
    consulted. Returns a result dict on success, None when the transport fails."""
    ips = _dns_fresh(host) or _cached_ips(host)
    if not ips:
        return None
    last = None
    for ip in ips:
        try:
            r = _request_once(url, headers, payload, method, host_ip=ip)
            if not r.get("error"):
                return r
            last = r
            if r.get("status") in (401, 403, 404):
                return r
        except _TransportError:
            continue
    return last


def _open(url: str, method: str = "GET", payload=None, headers: dict = None, retries: int = 3) -> dict:
    """Deterministic transport: raw-DNS-resolved IPs first. If the raw-DNS IPs
    all fail, one bounded probe of the system resolver (cap 15s) adds its IPs.
    The system resolver is never allowed to hang the caller, but a failed raw
    attempt does NOT permanently skip it — every call gets one bounded probe."""
    host = urllib.parse.urlparse(url).hostname or ""
    headers = headers or {}
    last = None
    for attempt in range(retries):
        r = _try_ips(url, headers, payload, method, host)
        if r is not None:
            return r
        sys_ips = _system_resolve_bounded(host)
        if sys_ips:
            extra = [ip for ip in sys_ips if ip not in (_dns_fresh(host) or [])]
            if extra:
                r = _try_ips_list(url, headers, payload, method, host, extra)
                if r is not None:
                    _mark_dns_broken(False)
                    return r
        if not sys_ips:
            _mark_dns_broken(True)
        last = r
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    return last or {"error": True, "status": 0, "message": "unknown transport failure"}


def _try_ips_list(url: str, headers: dict, payload, method: str, host: str, ips: list) -> dict:
    last = None
    for ip in ips:
        try:
            r = _request_once(url, headers, payload, method, host_ip=ip)
            if not r.get("error"):
                return r
            last = r
            if r.get("status") in (401, 403, 404):
                return r
        except _TransportError:
            continue
    return last


def _patched_getaddrinfo(ip: str):
    def patched(host, port, *args, **kwargs):
        args = (socket.AF_INET, socket.SOCK_STREAM) + tuple(args[2:])
        return _real_getaddrinfo(ip, port, *args, **kwargs)
    return patched


class _TransportError(Exception):
    pass


def _request_once(url: str, headers: dict, payload=None, method: str = "GET", host_ip: str = None) -> dict:
    """One HTTP attempt. Returns a dict (possibly {"error": ...}) for HTTP-level
    failures, or raises _TransportError for connect/DNS/SSL failures."""
    orig = None
    if host_ip:
        orig = socket.getaddrinfo
        socket.getaddrinfo = _patched_getaddrinfo(host_ip)
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"User-Agent": _UA, **headers},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            result = json.loads(body) if body else {}
            # SendGrid returns 202 with no body; expose its tracking id header.
            msg_id = resp.headers.get("X-Message-Id")
            if msg_id:
                result["id"] = msg_id
            # Brevo returns {"messageId": ...} in the body, not "id" — without
            # this mapping every Brevo send logged an empty provider_id and
            # the log could not be trusted.
            if "id" not in result and "messageId" in result:
                result["id"] = result["messageId"]
            if "id" not in result and not body:
                result["id"] = f"{EMAIL_PROVIDER}:{resp.status}"
            return result
    except urllib.error.HTTPError as e:
        return {"error": True, "status": e.code, "message": e.read().decode("utf-8", errors="replace")}
    except Exception as e:
        raise _TransportError(str(e)) from e
    finally:
        if orig:
            socket.getaddrinfo = orig


# ── Sending ──────────────────────────────────────────────────────────────────

def _from() -> str:
    return f"{FROM_NAME} <{FROM_EMAIL}>"


def _from_for(provider: str) -> str:
    email = _cfg_module.PROVIDER_FROM_EMAILS.get(provider, FROM_EMAIL)
    return f"{FROM_NAME} <{email}>"


def _send_resend(to_email: str, subject: str, html: str, text: str, reply_to: str) -> dict:
    payload = {
        "from": _from_for("resend"),
        "to": to_email,
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to:
        payload["reply_to"] = [reply_to]
    return _open(
        "https://api.resend.com/emails",
        method="POST",
        payload=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
    )


def _send_sendgrid(to_email: str, subject: str, html: str, text: str, reply_to: str) -> dict:
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}
    return _open(
        "https://api.sendgrid.com/v3/mail/send",
        method="POST",
        payload=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
    )


def _send_mailgun(to_email: str, subject: str, html: str, text: str, reply_to: str) -> dict:
    data = {
        "from": _from_for("mailgun"),
        "to": to_email,
        "subject": subject,
        "text": text,
        "html": html,
    }
    if reply_to:
        data["h:Reply-To"] = reply_to
    token = base64.b64encode(f"api:{MAILGUN_API_KEY}".encode()).decode()
    return _open(
        f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
        method="POST",
        payload=urllib.parse.urlencode(data).encode("utf-8"),
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/x-www-form-urlencoded"},
    )


def _send_postmark(to_email: str, subject: str, html: str, text: str, reply_to: str) -> dict:
    payload = {
        "From": _from_for("postmark"),
        "To": to_email,
        "Subject": subject,
        "TextBody": text,
        "HtmlBody": html,
    }
    if reply_to:
        payload["ReplyTo"] = reply_to
    return _open(
        "https://api.postmarkapp.com/email",
        method="POST",
        payload=json.dumps(payload).encode("utf-8"),
        headers={
            "X-Postmark-Server-Token": POSTMARK_API_TOKEN,
            "Content-Type": "application/json",
        },
    )


def _send_brevo(to_email: str, subject: str, html: str, text: str, reply_to: str) -> dict:
    """Brevo (free tier: 300/day) — API v3 SMTP send. The sender address must
    be verified in the Brevo dashboard (their SPF/DKIM records), so the From
    comes from PROVIDER_FROM_EMAILS -> "brevo" (defaults to FROM_EMAIL)."""
    payload = {
        "sender": {"email": _from_for("brevo").rsplit(">", 1)[0].split("<", 1)[-1].strip(),
                   "name": FROM_NAME},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    r = _open(
        "https://api.brevo.com/v3/smtp/email",
        method="POST",
        payload=json.dumps(payload).encode("utf-8"),
        headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
    )
    # Brevo returns messageId, not id — normalize so sent_log entries carry a
    # queryable provider_id (owner rule 2026-08-08: without this, every brevo
    # send was stored with provider_id=None and metrics could never see it).
    if not r.get("error") and r.get("messageId"):
        r["id"] = r["messageId"]
    return r


def _send_smtp(to_email: str, subject: str, html: str, text: str, reply_to: str) -> dict:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _from()
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        if SMTP_TLS:
            server.starttls()
        if SMTP_USER:
            server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, [to_email], msg.as_string())
        server.quit()
        return {"id": f"smtp:{datetime.utcnow().isoformat()}"}
    except Exception as e:
        return {"error": True, "status": 0, "message": str(e)}


_SEND_HANDLERS = {
    "resend": _send_resend,
    "sendgrid": _send_sendgrid,
    "mailgun": _send_mailgun,
    "postmark": _send_postmark,
    "brevo": _send_brevo,
    "smtp": _send_smtp,
}


_BREVO_PROBE_CACHE = {"at": 0.0, "ok": None, "msg": ""}
_BREVO_PROBE_TTL = 300.0


def _brevo_probe() -> tuple:
    """Lazy probe of the Brevo key (GET /v3/account, 5-min cache). Brevo
    accounts can lock API access to allowlisted IPs (401 "unrecognised IP");
    while locked the provider is excluded from rotation instead of burning
    50-email blocks on failures. The moment the owner allows the IP, the
    probe passes and brevo auto-joins the rotation."""
    now = time.time()
    if now - _BREVO_PROBE_CACHE["at"] < _BREVO_PROBE_TTL:
        return _BREVO_PROBE_CACHE["ok"], _BREVO_PROBE_CACHE["msg"]
    r = _open("https://api.brevo.com/v3/account",
              headers={"api-key": BREVO_API_KEY})
    ok = not r.get("error")
    msg = str(r.get("message", ""))[:120] if r.get("error") else "ok"
    _BREVO_PROBE_CACHE.update({"at": now, "ok": ok, "msg": msg})
    return ok, msg


def available_providers() -> list:
    """Providers with usable credentials, in configured order. brevo is gated
    on a live key probe (IP-allowlist)."""
    ready = []
    for p in _CFG_SEND_PROVIDERS:
        key = {
            "resend": (RESEND_API_KEY or "").strip(),
            "sendgrid": (SENDGRID_API_KEY or "").strip(),
            "mailgun": (MAILGUN_API_KEY or "").strip() and (MAILGUN_DOMAIN or "").strip(),
            "postmark": (POSTMARK_API_TOKEN or "").strip() and (POSTMARK_DOMAIN or "").strip(),
            "smtp": (SMTP_HOST or "").strip(),
        }.get(p, "")
        if p == "brevo":
            ok, msg = _brevo_probe()
            if not (BREVO_API_KEY or "").strip():
                continue
            if not ok:
                print(f"[providers] brevo probe failed ({msg}); keeping brevo out of rotation", flush=True)
                continue
        elif not key:
            continue
        ready.append(p)
    return ready or ([EMAIL_PROVIDER] if EMAIL_PROVIDER else [])


def send_email_via(provider: str, to_email: str, subject: str, html: str, text: str, reply_to: str = "") -> dict:
    handler = _SEND_HANDLERS.get(provider)
    if not handler:
        return {"error": True, "status": 0, "message": f"unknown provider: {provider}"}
    return handler(to_email, subject, html, text, reply_to)


def send_email(to_email: str, subject: str, html: str, text: str, reply_to: str = "") -> dict:
    return send_email_via(EMAIL_PROVIDER, to_email, subject, html, text, reply_to)


def pick_provider(sent_log: dict, exclude=()) -> str:
    """Deterministic provider pick for one send: the configured provider that
    is least used today (minimum used/cap, i.e. the most daily headroom,
    used < cap); ties go to configured order. Providers with >=2 transport
    failures today are skipped (a dead VPN/filtered host must not stall the
    machine); they auto-return the next UTC day. It is a tuple."""
    from datetime import datetime, timezone
    import collections
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = collections.Counter()
    for s in sent_log.get("sent", []):
        ts = str(s.get("timestamp") or "")
        if ts[:10] == day:
            usage[s.get("provider") or EMAIL_PROVIDER] += 1
    failing = collections.Counter()
    for f in sent_log.get("failed", []):
        ts = str(f.get("timestamp") or "")
        if not ts[:10] == day:
            continue
        if not str(f.get("error", "")).startswith("send exceeded"):
            failing[f.get("provider") or "?"] += 1
    banned = {p for p in failing if failing[p] >= 2} | set(exclude)
    best, best_ratio = None, float("inf")
    for p in available_providers():
        cap = _cfg_module.PROVIDER_DAILY_CAPS.get(p, 100)
        used = usage.get(p, 0)
        if used >= cap:
            continue
        if p in banned:
            continue
        ratio = used / cap
        if ratio < best_ratio:
            best, best_ratio = p, ratio
    if best is None:
        best = [p for p in available_providers() if p not in banned]
        best = (best or available_providers())[0]
    return best


# ── Email Data (analytics) ───────────────────────────────────────────────────

def fetch_email_status(email_id: str, provider: str = "") -> dict:
    """Latest status for one sent email -> {"last_event": <canonical>}.

    Routed by the SENDING provider (owner rule 2026-08-08: this used to query
    the default EMAIL_PROVIDER for every entry, so all 116 brevo sends were
    measured against resend's API and came back unverified).

    resend:   GET /emails/{id} -> {"last_event": ...}
    mailgun:  events API per message-id (opened > clicked/delivered > ...)
    brevo:    v3 SMTP logs per messageId (most significant event wins)
    sendgrid: not available (needs Event Webhook / paid activity API)
    smtp:     no tracking at all
    """
    provider = (provider or EMAIL_PROVIDER or "").strip().lower()
    if provider == "resend":
        return _open(
            f"https://api.resend.com/emails/{urllib.parse.quote(email_id)}",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            retries=1,
        )
    if provider == "mailgun":
        return _mailgun_status(email_id)
    if provider == "brevo":
        return _brevo_status(email_id)
    return {"error": True, "status": 0, "message": f"{provider} does not report email status (no API-level tracking)"}


_MAILGUN_EVENT_RANK = {
    "rejected": "failed",
    "failed": "failed",
    "delivered": "delivered",
    "opened": "opened",
    "clicked": "clicked",
    "complained": "complained",
    "unsubscribed": "complained",
    "stored": "delivered",
}
_MAILGUN_ORDER = ["complained", "clicked", "opened", "delivered", "stored", "unsubscribed", "failed", "rejected"]


def _mailgun_status(msg_id: str) -> dict:
    token = base64.b64encode(f"api:{MAILGUN_API_KEY}".encode()).decode()
    base = f"https://api.mailgun.net/v3/{urllib.parse.quote(MAILGUN_DOMAIN)}/events"
    headers = {"Authorization": f"Basic {token}"}
    # ONE call instead of 9 (owner rule 2026-08-09): a single message-id
    # query returns the message's events in time order — the most significant
    # event wins locally. The old rank-ordered loop made up to 9 transport
    # calls per email, which is what turned a full collect into 20+ minutes.
    qs = urllib.parse.urlencode({"message-id": msg_id, "limit": 25})
    r = _open(f"{base}?{qs}", headers=headers, retries=1)
    if r.get("error"):
        return r
    items = r.get("items") or []
    if items:
        best = min(items, key=lambda e: _MAILGUN_ORDER.index(
            str(e.get("event") or "") if str(e.get("event") or "") in _MAILGUN_ORDER
            else len(_MAILGUN_ORDER)))
        return {"last_event": _MAILGUN_EVENT_RANK.get(best.get("event"), best.get("event"))}
    # No tracked events yet — plain "accepted" is the lowest-signal confirmation.
    qs = urllib.parse.urlencode({"event": "accepted", "message-id": msg_id, "limit": 1})
    r = _open(f"{base}?{qs}", headers=headers, retries=1)
    if not r.get("error") and r.get("items"):
        return {"last_event": "sent"}
    return {"error": True, "status": 0, "message": "mailgun: no events found for message id (not yet processed, or wrong id)"}


_BREVO_EVENT_RANK = {
    "complained": 0, "spam": 0, "unsubscribed": 0,
    "click": 1, "clicked": 1,
    "opened": 2, "uniqueOpened": 2,
    "hardBounce": 3, "blocked": 3, "invalid": 3,
    "softBounce": 4, "deferred": 4, "delayed": 4,
    "delivered": 5,
    "request": 6, "requests": 6,
    "error": 7, "failed": 7,
}
_BREVO_TO_CANONICAL = {
    "complained": "complained", "spam": "complained", "unsubscribed": "complained",
    "click": "clicked", "clicked": "clicked",
    "opened": "opened", "uniqueOpened": "opened",
    "hardBounce": "bounced", "blocked": "bounced", "invalid": "bounced",
    "softBounce": "delivery_delayed", "deferred": "delivery_delayed", "delayed": "delivery_delayed",
    "delivered": "delivered",
    "request": "sent", "requests": "sent",
    "error": "failed", "failed": "failed",
}


def _brevo_status(msg_id: str) -> dict:
    """Brevo v3 SMTP statistics events: GET /smtp/statistics/events
    ?messageId=... returns the event history for one message; the most
    significant event wins (owner rule 2026-08-08: /smtp/logs does not exist —
    404 'Invalid route/method' — the events endpoint is the real one)."""
    qs = urllib.parse.urlencode({"messageId": msg_id, "limit": 50})
    r = _open(f"https://api.brevo.com/v3/smtp/statistics/events?{qs}",
              headers={"api-key": BREVO_API_KEY})
    if r.get("error"):
        return r
    evs = r.get("events") or []
    if not evs:
        return {"error": True, "status": 0, "message": "brevo: no events found for message id"}
    best = min(evs, key=lambda e: _BREVO_EVENT_RANK.get(str(e.get("event") or "unknown"), 99))
    ev = str(best.get("event") or "")
    return {"last_event": _BREVO_TO_CANONICAL.get(ev, "unknown"), "provider_event": ev}


def list_sent_emails() -> dict:
    """Sent emails, used to backfill missing/truncated ids in the log."""
    if EMAIL_PROVIDER == "resend":
        # Max page size (100) so the backfill can see the whole send history.
        return _open("https://api.resend.com/emails?limit=100", headers={"Authorization": f"Bearer {RESEND_API_KEY}"})
    return {"error": True, "status": 0, "message": f"{EMAIL_PROVIDER} has no sent-email listing API"}


def list_received_emails(provider: str = "") -> dict:
    """Received emails, used to auto-detect replies. With
    REPLY_CAPTURE=gmail_imap the sweep reads the founder Gmail inbox over
    IMAP (unified capture, owner direction 2026-08-10) — same data shape as
    the Resend receiving API so analytics.sync_replies works unchanged."""
    explicit = bool(str(provider).strip())
    provider = (provider or EMAIL_PROVIDER or "").strip().lower()
    if provider == "gmail_imap":
        return _list_gmail_imap()
    if not explicit and _cfg_module.REPLY_CAPTURE == "gmail_imap" and provider == EMAIL_PROVIDER.strip().lower():
        return _list_gmail_imap()
    if provider == "resend":
        return _open("https://api.resend.com/emails/receiving", headers={"Authorization": f"Bearer {RESEND_API_KEY}"})
    return {"error": True, "status": 0, "message": f"{provider} has no received-email listing API"}


def receiving_domain_status(address: str, provider: str = "") -> dict:
    """Prove that the Reply-To domain is enabled for provider-side receiving."""
    provider = (provider or EMAIL_PROVIDER or "").strip().lower()
    raw = str(address or "").strip().lower()
    domain = raw.rsplit("@", 1)[-1]
    if not domain or domain == raw:
        return {"ready": False, "domain": None, "reason": "Reply-To address is missing or invalid"}
    if provider != "resend":
        return {"ready": False, "domain": domain,
                "reason": f"receiving-domain verification is not implemented for {provider}"}
    listing = _open("https://api.resend.com/domains",
                    headers={"Authorization": f"Bearer {RESEND_API_KEY}"})
    if listing.get("error"):
        return {"ready": False, "domain": domain,
                "reason": f"could not verify Resend receiving status: {listing.get('message')}"}
    match = next((item for item in listing.get("data") or []
                  if str(item.get("name") or "").strip().lower() == domain), None)
    if not match:
        return {"ready": False, "domain": domain,
                "reason": f"{domain} is not configured as a Resend domain"}
    capabilities = match.get("capabilities") or {}
    ready = match.get("status") == "verified" and capabilities.get("receiving") == "enabled"
    return {"ready": ready, "domain": domain, "status": match.get("status"),
            "receiving": capabilities.get("receiving"),
            "reason": None if ready else f"{domain} is not verified with Resend receiving enabled"}


# ── Unified Gmail reply capture (owner direction 2026-08-10) ────────────────
# Every send sets Reply-To: replies@spielos.xyz; Cloudflare Email Routing
# forwards that address to the founder inbox (66shayan@gmail.com); these
# functions read that inbox over IMAP so reply-rate evidence is automatic.
# No receiving domain, no plan upgrade, no MX changes.

def gmail_imap_status() -> dict:
    """Readiness probe: credentials present and IMAP login + INBOX select
    succeed. Same shape as receiving_domain_status for the ACT guardrail."""
    user = _cfg_module.GMAIL_IMAP_USER
    if not user or not _cfg_module.GMAIL_IMAP_APP_PASSWORD:
        return {"ready": False, "domain": "gmail_inbox",
                "reason": "GMAIL_IMAP_USER / GMAIL_IMAP_APP_PASSWORD are not configured"}
    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
    except Exception as exc:
        return {"ready": False, "domain": "gmail_inbox", "reason": f"Gmail IMAP connect failed: {exc}"}
    try:
        conn.login(user, _cfg_module.GMAIL_IMAP_APP_PASSWORD)
        conn.select("INBOX")
        return {"ready": True, "domain": "gmail_inbox", "status": "verified",
                "receiving": "enabled", "reason": None}
    except Exception as exc:
        return {"ready": False, "domain": "gmail_inbox", "reason": f"Gmail IMAP login failed: {exc}"}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _gmail_message_record(msg, num: bytes) -> dict:
    """Convert one parsed IMAP message into the received-listing shape.

    The Auto-Submitted / X-Autoreply headers are classification inputs the
    reply classifier needs (owner evidence 2026-08-11) — Gmail's subject-only
    listing could not distinguish a human reply from an autoresponder.
    """
    msg_id = str(msg.get("Message-ID") or "").strip() or f"gmail-{num.decode()}"
    sender = parseaddr(str(msg.get("From") or ""))[1].strip().lower()
    return {
        "id": f"gmail-{msg_id}",
        "from": sender or str(msg.get("From") or ""),
        "subject": _decode_mime_header(str(msg.get("Subject") or "")),
        "message_id": msg_id,
        "created_at": _parse_email_date(str(msg.get("Date") or "")),
        "text": _gmail_body_text(msg),
        "to": str(msg.get("To") or ""),
        "in_reply_to": str(msg.get("In-Reply-To") or ""),
        "auto_submitted": str(msg.get("Auto-Submitted") or ""),
        "x_autoreply": str(msg.get("X-Autoreply") or ""),
    }


def _list_gmail_imap() -> dict:
    """Poll the founder Gmail inbox for replies. Data shape matches the
    Resend receiving API: {"data": [{"id", "from", "subject", "message_id",
    "created_at", "text", "to", "in_reply_to", "auto_submitted",
    "x_autoreply"}]}."""
    user = _cfg_module.GMAIL_IMAP_USER
    if not user or not _cfg_module.GMAIL_IMAP_APP_PASSWORD:
        return {"error": True, "status": 0, "message": "GMAIL_IMAP credentials not configured"}
    since = (datetime.now(timezone.utc) - timedelta(hours=_cfg_module.REPLY_LOOKBACK_HOURS)).strftime("%d-%b-%Y")
    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
    except Exception as exc:
        return {"error": True, "status": 0, "message": f"Gmail IMAP connect failed: {exc}"}
    try:
        conn.login(user, _cfg_module.GMAIL_IMAP_APP_PASSWORD)
        conn.select("INBOX")
        typ, data = conn.search(None, f'(SINCE {since})')
        items = []
        for num in (data[0] or b"").split():
            try:
                typ2, msg_data = conn.fetch(num, "(RFC822)")
            except Exception:
                continue
            if typ2 != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            try:
                msg = email.message_from_bytes(raw)
            except Exception:
                continue
            items.append(_gmail_message_record(msg, num))
        return {"data": items, "provider": "gmail_imap"}
    except Exception as exc:
        return {"error": True, "status": 0, "message": f"Gmail IMAP sweep failed: {exc}"}
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _decode_mime_header(value: str) -> str:
    parts = decode_header(value)
    out = []
    for chunk, enc in parts:
        try:
            out.append(chunk.decode(enc or "utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk))
        except Exception:
            out.append(str(chunk))
    return "".join(out).strip()


def _gmail_body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except LookupError:
                        return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", errors="replace") if payload else ""


def _parse_email_date(value: str) -> str:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


# ── Cloudflare DNS helpers ────────────────────────────────────────────────────

import urllib.request as _urllib

def _cf_resolve():
    try:
        ip = [r[4][0] for r in socket.getaddrinfo("api.cloudflare.com", 443, socket.AF_INET)][0]
        return ip
    except Exception:
        try:
            return _dns_fallback("api.cloudflare.com")[0]
        except Exception:
            return None

def _cf_api(method, path, body=None):
    from config import CF_API_TOKEN, CF_ACCOUNT_ID
    if not CF_API_TOKEN or not CF_ACCOUNT_ID:
        return {"error": True, "message": "CF_API_TOKEN or CF_ACCOUNT_ID not set in .env"}
    url = f"https://api.cloudflare.com/client/v4{path}"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    payload = json.dumps(body).encode() if body else None
    return _open(url, method=method, payload=payload, headers=headers)

def cf_get_zone(domain):
    r = _cf_api("GET", f"/zones?name={domain}")
    zones = r.get("result", [])
    return zones[0]["id"] if zones else None

def cf_upsert_cname(zone_id, name, content, proxied=False):
    """Idempotent CNAME upsert: if a record already has the right target and
    proxy state, leave it untouched (delete+recreate makes Resend re-verify
    the tracking domain and flaps its status). Only delete when the record
    actually differs."""
    content = content.rstrip(".")
    existing = _cf_api("GET", f"/zones/{zone_id}/dns_records?name={name}&type=CNAME")
    if existing.get("error"):
        return existing
    for rec in existing.get("result", []):
        if rec.get("content", "").rstrip(".") == content and bool(rec.get("proxied")) == bool(proxied):
            return {"success": True, "ok": True, "record": f"{name} -> {content} (unchanged)"}
    for rec in existing.get("result", []):
        _cf_api("DELETE", f"/zones/{zone_id}/dns_records/{rec['id']}")
    return _cf_api("POST", f"/zones/{zone_id}/dns_records", {
        "type": "CNAME", "name": name, "content": content, "proxied": proxied, "ttl": 1
    })


def cf_upsert_txt(zone_id, name, content):
    """Idempotent TXT upsert (for SPF/DKIM verification records)."""
    existing = _cf_api("GET", f"/zones/{zone_id}/dns_records?name={name}&type=TXT")
    if existing.get("error"):
        return existing
    for rec in existing.get("result", []):
        if rec.get("content", "") == content:
            return {"success": True, "ok": True, "record": f"{name} TXT (unchanged)"}
    for rec in existing.get("result", []):
        _cf_api("DELETE", f"/zones/{zone_id}/dns_records/{rec['id']}")
    return _cf_api("POST", f"/zones/{zone_id}/dns_records", {
        "type": "TXT", "name": name, "content": content, "ttl": 1
    })

def cf_set_tracking(domain, subdomain="links"):
    zone_id = cf_get_zone(domain)
    if not zone_id:
        return {"error": True, "message": f"zone {domain} not found in Cloudflare"}
    r = cf_upsert_cname(zone_id, f"{subdomain}.{domain}", "links1.resend-dns.com", proxied=False)
    if r.get("success"):
        return {"ok": True, "record": f"{subdomain}.{domain} -> links1.resend-dns.com (DNS only)"}
    return {"error": True, "message": str(r.get("errors", r))}
