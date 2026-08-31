---
name: analytics
description: Implement, review, and preserve SpielOS analytics: GA4, PostHog, Search Console, full-capture configuration (no consent gate), event taxonomy, attribution, privacy, loader implementation, and analytics verification. Use for any analytics implementation, tag change, event tracking, full-capture configuration, or analytics debugging. Do NOT use for SEO metadata or structured data — use the seo skill instead.
---

# SpielOS Analytics

SpielOS is a static Astro site (SSG) served at `https://spielos.xyz` with a Persian (`fa`, RTL) mirror under `/fa/`. Analytics captures for **all visitors** (owner directive 2026-08-18: no consent gate, full GA4+PostHog capture, session replay ON), never blocks rendering, and produces accurate buyer and lead-conversion data across both locales.

## Scope

This skill owns:

- GA4 (Google Analytics 4) implementation and configuration
- PostHog implementation and configuration
- Search Console verification meta tag (presence check; SEO owns the implementation)
- Full-capture configuration (no consent gate; owner directive 2026-08-18)
- Event taxonomy and naming
- Attribution (UTM, referrer)
- Privacy-sensitive configuration
- Loader implementation (gtag.js, PostHog JS SDK)
- Analytics verification (DebugView, live events, production checks)

This skill does NOT own:

- SEO metadata, structured data, canonicalization, hreflang, sitemap, robots, redirects, or internal linking (see `.agents/company/skills/seo/SKILL.md`)
- Editorial voice or copy style (see copywriting skills)

## Before editing analytics

Read these files:

1. `AGENTS.md` — routes, protected scope, i18n rules
2. `src/config.ts` — `SITE`, `ANALYTICS`, `SOCIAL`
3. `src/layouts/BaseLayout.astro` — global head: analytics loaders, event taxonomy
4. `.agents/company/skills/seo/SKILL.md` — SEO invariants (analytics presence check, not implementation)

### Authoritative files

Treat `src/config.ts` and `BaseLayout.astro` as authoritative. Never hardcode analytics IDs, keys, or hosts in page components.

## Configuration

Single source of truth: `src/config.ts` → `ANALYTICS`:

- `googleAnalyticsId` — GA4 property ID (read the live value from `src/config.ts`; never copy it into prose or page components — it rotates)
- `googleSearchConsoleVerification` — Search Console meta token
- `posthogApiKey`, `posthogApiHost` — PostHog instance on `https://t.spielos.xyz`

Never duplicate analytics IDs in page components. All analytics lives in BaseLayout (global) or the analytics skill's shared utilities.

### Server-side read credentials

The live PostHog read channel is the **read-only PostHog MCP** (`opencode.json`
→ `mcp.servers.posthog`, `type: remote`, `https://mcp.posthog.com/mcp`,
`oauth: false`) sending `Authorization: Bearer {env:POSTHOG_PERSONAL_API_KEY}`
plus `x-posthog-read-only: true`. The personal API key (`phx_...`) lives only
in the gitignored `.spielos/.env` as `POSTHOG_PERSONAL_API_KEY`; it is never
hardcoded in code, config, or docs. Agents call read-only HogQL through the
`posthog_*` MCP tools.

The deterministic server-side read channel (unit-tested, same personal key) is
the **EU region project-scoped Query API**:
`POST https://eu.posthog.com/api/projects/92369/query/` with
`Authorization: Bearer <POSTHOG_PERSONAL_API_KEY>` (project id `92369`,
"Default project"), implemented by `PostHogClient` in posthog.py.
`POSTHOG_PROJECT_TOKEN` in `.spielos/.env` is the `phc_` client-side project
key: it is NOT accepted by the MCP or the server-side Query API, and the old
`us.posthog.com/api/warehouse/query/` route 404s/401s for this project (region
and credential mismatch), so neither is a live read channel.

## Loading model

BaseLayout loads analytics in this order (full capture, no consent gate):

1. The GA4 command queue (`window.dataLayer` + `gtag`) is defined inline in `<head>`.
2. Deferred (requestIdleCallback, fallback `setTimeout`): gtag.js is injected, `gtag('js', new Date())` and `gtag('config', ...)` run with `send_page_view: true`, `cookie_flags: 'SameSite=None;Secure'`, `debug_mode: false`, and `posthog.init` runs with `person_profiles: 'always'` and `mask_all_inputs: true`. Deferral only preserves performance — it never gates analytics on user interaction.

### Configuration rules

- `debug_mode` must be `false` in production. Only enable for local development or explicit debugging sessions.
- `person_profiles: 'always'` is the documented requirement (owner directive 2026-08-18): anonymous person profiles enable funnel analysis and session replay on unauthenticated traffic. Do not change it back to `'identified_only'`.
- Session recording is enabled (do not set `disable_session_recording`). Do not set `autocapture` or `capture_pageview` to false — pageviews, autocapture, and session replay must stay on.
- `mask_all_inputs: true` — PostHog never stores raw form values; the funnel events still count starts/submits/successes.
- No consent gates: events are captured for ALL visitors from first pageview; there is no banner, no consent-check, and no `gtag('consent', ...)` call.

### Loader integrity

- Do not add a second loader for GA4 or PostHog.
- If a GTM container is ever added, keep `gtmId` in config and load the GTM snippet instead of the direct gtag loader — never run both.
- Document whether direct gtag or GTM owns Google tracking. Never load both.
- No duplicate GA4, GTM, or PostHog loaders.

## PostHog warehouse reads (read-only)

The website-sided funnel is read back only through read-only channels — never
by scraping the browser and never by writing to the warehouse.

### Read surfaces (owner directive 2026-08-17, verified live 2026-08-17)

1. **Read-only PostHog MCP (the agent-facing live read channel)**: `opencode.json`
   registers the server under `mcp.servers.posthog` (`type: remote`,
   `https://mcp.posthog.com/mcp`, `oauth: false`) and sends
   `Authorization: Bearer {env:POSTHOG_PERSONAL_API_KEY}` with
   `x-posthog-read-only: true`. The personal API key (`phx_...`) is read from
   the gitignored `.spielos/.env`; the `posthog_*` tools are read-only HogQL.
   No project token and no browser OAuth flow are involved.
2. **Deterministic HogQL helpers** (unit-tested, live with the same personal
   key): `.agents/company/departments/analytics/posthog.py` —
   `PostHogClient.query / .rows / .event_counts` (read-only) hit
   `POST https://eu.posthog.com/api/projects/92369/query/` with the Bearer key,
   plus `consume_batch_evidence(...)`, which joins refreshed Buffer per-post
   metrics and PostHog event counts per batch on the campaign join keys.
   The `phc_` project key and the old `us.posthog.com/api/warehouse/query/`
   route are rejected (region and credential mismatch). Use these helpers
   instead of hand-rolled requests; never inline credentials.

### Funnel events consumed per batch

The canonical stage events live in
`.agents/company/departments/analytics/funnel.json` (company truth). The
per-batch funnel consumption uses the REAL deployed loader events (loader v4,
full capture 2026-08-18): `content_landing` (attention), `cta_clicked`
(engagement), `lead_form_view` / `lead_form_start` (intent), and
`lead_form_submit` / `lead_form_success` (lead), with `lead_form_error` as the
failure diagnostic. The retired loader names
`agent_briefing_form_start/submit/success`, `waitlist_form_submit/success`,
`click_contact`, and `click_install` are NO LONGER emitted by the loader:
their counts are labeled `missing`, never zero, because an absent event means
it was not captured, not that zero people behaved that way. The live
lead-success event consumed as the funnel's `leads` stage is
`lead_form_success`. The full stage set for segmentation and diagnosis
(`missing` = not captured on this site):

| Stage | Events | Live on this site (loader v4, 2026-08-18) |
|---|---|---|
| attention | `$pageview`, `content_landing` | `$pageview` (autocaptured by PostHog); `content_landing` on threads/youtube source |
| engagement | `cta_clicked` | emitted by the loader |
| intent | `lead_form_view`, `lead_form_start` | emitted by the loader (modal + inline forms) |
| lead | `lead_form_submit`, `lead_form_success` | emitted by the loader (modal + inline forms) |
| qualified | `qualified_lead` | defined; not yet captured — missing, never zero |
| conversation | `booked_call` | defined; not yet captured — missing, never zero |
| revenue | `sale` | defined; not yet captured — missing, never zero |

Retired support-CTA events (no longer emitted by the loader):
`click_contact`, `click_install` — labeled missing, never zero.

Campaign attribution reads must preserve funnel.json `required_properties`:
`locale`, `page_path`, `landing_path`, `source`, `medium`, `campaign`,
`campaign_id`, `batch_id`, `item_id`, `content_id`, `platform`,
`creative_signature`, `batch_number`, `batch_item`, `hook_id`,
`narrative_type`. Filter counts by the lowercase UTM properties
(`utm_campaign`, `utm_content`, ...) with the same values the campaign
destinations carry.

### Honesty rules

- **Missing counts are labeled `missing`, never zero.** An event absent from a
  warehouse group-by means it was not captured, not that zero people acted;
  an engagement metric Buffer has not exposed is missing, not zero.
- Only non-PII events are read or counted; no form fields or contact details
  are stored — PostHog runs with `mask_all_inputs: true`, and the funnel
  events only count starts/submits/successes.
- Refreshed Buffer per-post metrics and warehouse event counts are
  `technical_only` delivery evidence. Business learning (the measured handoff
  and next-batch hypothesis) requires complete comparing evidence; incomplete
  batches stay labeled incomplete and never convert machinery evidence into a
  market or positioning conclusion.
- `debug_mode` and the MCP server are tooling; they never change what the site
  captures without a separate, documented configuration change.

### Verification

Run the live read-only proof through the analytics Department client
(`PostHogClient`, which uses `POSTHOG_PERSONAL_API_KEY` from `.spielos/.env`
against `POST https://eu.posthog.com/api/projects/92369/query/`):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -c "from company.departments.analytics.posthog import PostHogClient; import json; print(json.dumps(PostHogClient().rows('select event, count() as c from events group by event order by c desc limit 10'), indent=2))"
```

The response lists the actual event names and counts in the project. Record
them as `technical_only` evidence; never fabricate event names or counts if the
read fails. The retired `us.posthog.com/api/warehouse/query/` probe with the
`X-Project-API-Key` header 404s/401s for this project (region and credential
mismatch) and is not a read channel.

## Full-capture architecture (owner directive 2026-08-18)

The consent gate was removed on 2026-08-18: GA4 and PostHog initialize
unconditionally for **all visitors** — there is no banner, no consent gate,
and no event suppression before "acceptance". This is a deliberate owner
directive: the previous consent-gated loader (2026-08-08–2026-08-10)
collapsed measured traffic to near zero because non-clicking visitors and
bots never consented.

### Behavior

- **All visitors captured**: gtag.js and `posthog.init` load and run on every
  page; events fire from first pageview without any interaction.
- **Session replay ON**: `disable_session_recording` is never set.
- **`person_profiles: 'always'`**: anonymous person profiles for funnel
  analysis + session replay on unauthenticated traffic.
- **`mask_all_inputs: true`**: raw form values are never captured; the funnel
  events still count `lead_form_start` / `lead_form_submit` /
  `lead_form_success`.
- **Channel attribution**: PostHog captures `$utm_*` on `$pageview`; custom
  events carry `source` / `medium` / `campaign` / `content_id` from the
  loader's sessionStorage content-attribution context
  (`spielos.content-attribution`), preserved across navigation.

### Verification

- Verify GA4 and PostHog both receive events without any banner interaction.
- Verify no `gtag('consent', ...)` calls and no consent tokens exist in
  `src/` (see `scripts/check-analytics-full-capture.mjs`).
- Verify PostHog session replays are recorded on unauthenticated traffic.

## Event taxonomy

Events fire to both gtag and PostHog via a single `track()` helper defined in BaseLayout. Do not add a second event system.

### Defined events

Events fire to both gtag and PostHog via a single `track()` helper defined in BaseLayout. Do not add a second event system. The "Status" column is the loader v4 taxonomy (full capture, 2026-08-18); names the loader no longer emits are labeled missing, never zero, and are not invented into tables. Warehouse counts must be re-verified by re-running the live read after deploy — never copy counts from a different loader version.

| Event | Parameters | Description | Status (loader v4, 2026-08-18) |
|---|---|---|---|
| `$pageview` | — | Pageview (PostHog autocapture) | emitted |
| `content_landing` | `page`, `device`, `locale` | Content landing impression (threads/youtube source) | emitted |
| `cta_clicked` | `cta_type`, `page_path`, `location` | CTA button/link clicked | emitted |
| `lead_form_view` | `form_type`, `page`, `device`, `locale`, `location` | Lead form shown (modal open / inline page) | emitted |
| `lead_form_start` | `form_type`, `page`, `device`, `locale`, `location` | First input on a lead form | emitted |
| `lead_form_submit` | `form_type`, `page`, `device`, `locale`, `location` | Lead form submitted | emitted |
| `lead_form_success` | `form_type`, `page`, `device`, `locale`, `location` | Lead form submission succeeded | emitted |
| `lead_form_error` | `form_type`, `page`, `device`, `locale`, `location` | Lead form submission failed | emitted |
| `social_clicked` | `platform` | Social link clicked | emitted |
| `outbound_link` | `url`, `link_text` | Outbound link clicked | emitted |
| `scroll_depth` | `depth`: 25 \| 50 \| 75 \| 100 | Scroll milestone reached | emitted |
| `theme_toggled` | `theme` | Theme changed | emitted |
| `agent_briefing_form_start` / `..._submit` / `..._success` | `form_type` | RETIRED loader names — no longer emitted | missing, never zero |
| `waitlist_form_submit` / `waitlist_form_success` | `form_type` | RETIRED loader names — no longer emitted | missing, never zero |
| `click_contact` / `click_install` | `page_path`, `device`, `locale` | RETIRED support CTA names — no longer emitted | missing, never zero |

PostHog also autocaptures `$web_vitals`, `$pageleave`, `$autocapture`,
`$exception`, and related events; they are read only, never re-labeled.

### Event rules

- Event names must be snake_case.
- Parameters must be lowercase.
- Do not send personally identifiable information (PII) in events: no email, name, phone, IP, or address. PostHog `mask_all_inputs: true` prevents raw form-value capture.
- Event deduplication: do not fire the same event twice for a single user action (the loader's lead-form events come from the form components themselves; the global waitlist-era handlers that double-fired them were removed).
- UTM and referrer data must be preserved across navigation where applicable.

## Privacy

- No PII in events, properties, or custom dimensions.
- No tracking pixels or fingerprinting beyond standard analytics.
- PostHog must not capture raw inputs from form fields (`mask_all_inputs: true`); funnel events count starts/submits/successes only.
- IP anonymization is the default for GA4; do not override.
- Privacy-page consistency: analytics behavior must match what the privacy page describes.

## Production versus development

- `debug_mode` must be `false` in production GA4 config.
- PostHog `debug` option must be `false` in production.
- Development environments may enable debug features but must not send production events.
- Environment validation: verify analytics config matches the deployment environment.

## Failed-network behavior

Analytics loaders must degrade gracefully:

- If GA4 script fails to load, queued `gtag` commands silently fail.
- If PostHog script fails to load, PostHog calls silently fail.
- No user-visible errors from analytics failures.
- Analytics failures must not block page rendering or interactivity.

## Verification

### Automated

After analytics changes, run:

```bash
npm run typecheck
npm run build
npm run seo:check
```

`seo:check` validates that analytics loaders are present. For analytics-specific verification, use manual checks.

### Manual

- GA4 DebugView: enable debug mode locally, verify events appear in real-time in GA4 DebugView.
- PostHog live events: verify events appear in PostHog's live events panel.
- Production check: after deploy, verify GA4 Realtime report shows pageviews, PostHog shows events.
- Full-capture test: in production, verify pageviews and lead events appear without any banner interaction (no consent gate exists).
- Browser DevTools: verify no duplicate GA4 or PostHog network requests.
- Cookie audit: GA4 cookies are set on first pageview for all visitors (no consent gate).

### Search Console

- Verify `google-site-verification` meta tag is present in page source (presence only — SEO owns the implementation).
- Verify Search Console property is verified and receiving data.

## Protected scope

Do not edit `src/components/showcase/*` (retired but protected). The legacy
waitlist route no longer exists — never add tracking for it; conversion events
belong to the Apply funnel (`/apply/`, `apply_cta_clicked` / `apply_submitted`).
Showcase analytics comes from BaseLayout (global) — do not add inline analytics
inside showcase components.

## Report

After analytics work, report:

- Files changed
- Loader changes (if any)
- Event taxonomy changes (if any)
- Capture-configuration changes (if any)
- Configuration changes
- Verification results (automated and manual)
- Any warnings or issues discovered
