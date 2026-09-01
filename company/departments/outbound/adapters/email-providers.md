# Outbound email provider registry

Every provider credential lives in `.spielos/.env` (gitignored —
never committed). This file is the receipt: which env var holds which key,
and the live status. If `.env` is ever lost, re-paste the values into these
variables.

| Provider | Env var(s) | Status (2026-08-08) | What it's for |
|---|---|---|---|
| Resend | `RESEND_API_KEY` | ✅ LIVE — sending | Transactional + status reads |
| Mailgun | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` (mg.spielos.xyz) | ✅ LIVE — sending | Transactional + status reads |
| Brevo | `BREVO_API_KEY` | ✅ LIVE — sending | Transactional + status reads (IP allowlist must keep this server's IP) |
| Postmark | `POSTMARK_API_TOKEN` (server), `POSTMARK_ACCOUNT_TOKEN` (account), `POSTMARK_DOMAIN` (pm.spielos.xyz) | ⏸ Account PENDING APPROVAL; token situation unresolved — see notes below | Transactional + status reads |
| EmailOctopus | `EMAILOCTOPUS_API_KEY` | ⚠ Key valid — **not usable for this workflow**: marketing ESP, campaign/list-based, NO transactional send API | Broadcast campaigns only |
| SendGrid | `SENDGRID_API_KEY` (missing) | 🔴 No key | — |
| SMTP/Gmail | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` | 🔴 Not configured; would break the metrics loop (no status reads) | Last-resort only |

Sending rotation (`../workflows/email/providers.py`) picks the enabled
provider with the most daily headroom; the order comes from `SEND_PROVIDERS`
in `.env`. Providers with 2+ transport failures today are skipped until the
next UTC day. Per-provider daily caps: `PROVIDER_DAILY_CAPS` in `.env`
(resend 100 · mailgun 100 · brevo 300 · postmark 100 · sendgrid 100 · smtp 200).

## Postmark notes (2026-08-08)
- User-provided "server token" `a84154f2…` is answered by the API as an
  ACCOUNT token ("Server token is not allowed, please use a valid Account
  token") — it cannot send.
- User-provided "account token" `f16b9bc8…` fails as a server token and the
  account endpoint is unreachable from this server (HTML 404 / transport
  failures — network path to postmark edges is flaky from this box).
- Account itself is PENDING APPROVAL: sends to non-`pm.spielos.xyz`
  recipients return 412 until approved.
- Needed: the real **Server API Token** from the Postmark dashboard
  (Servers → "My First Server" → API Tokens) + account approval.

## How to replace a key
1. Edit `.spielos/.env` (never `.env.example`, never commit).
2. Verify the Department catalog and persisted goal with `company catalog`
   and `company status GOAL_ID` through the repository runtime command.
3. There is no channel daemon to restart; each company-runtime step reloads
   the provider configuration.

## Deliverability hardening (2026-08-16)

Director audit + owner-approved change task `change-0893155801` (goal-0db6b0a1b4).
Main-zone `spielos.xyz` DNS updated in Cloudflare (zone `e64f6a563bf4f3b6a07dbb82b4b96543`):

- **SPF** now: `v=spf1 include:_spf.mx.cloudflare.net include:relay.resend.net include:spf.brevo.com include:mailgun.org ~all`
  (added `include:mailgun.org` — Mailgun is an active sender From `shayan@spielos.xyz`)
- **DMARC** hardened at `_dmarc.spielos.xyz`:
  `v=DMARC1; p=quarantine; sp=quarantine; pct=100; fo=1; rf=afrf; ri=86400; rua=mailto:shayan@spielos.xyz`
- **TLS-RPT** added at `_smtp._tls.spielos.xyz`:
  `v=TLSRPTv1; rua=mailto:shayan@spielos.xyz`
- **MTA-STS** added: TXT `_mta-sts.spielos.xyz` `v=STSv1; id=20260816`, CNAME
  `mta-sts.spielos.xyz -> spielos.xyz` (proxied), policy served at
  `https://mta-sts.spielos.xyz/.well-known/mta-sts.txt` from
  `public/.well-known/mta-sts.txt` (mode enforce, mx route1/2/3.mx.cloudflare.net,
  max_age 86400). GitHub Pages CNAME file extended to serve the `mta-sts` host.

DKIM by provider: Resend (`resend._domainkey`) ✅ · Brevo (`brevo1/brevo2` CNAMEs
to brevosend) ✅ · Mailgun on `mg.spielos.xyz` (`krs._domainkey` + SPF include:mailgun.org) ✅.
