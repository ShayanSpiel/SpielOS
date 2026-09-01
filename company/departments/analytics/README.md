# Analytics Department

Analytics owns canonical company metrics, the full funnel, attribution,
data-quality checks, scorecards, diagnostics, and bounded CRO experiments.
Other Departments request evidence from Analytics rather than defining rival
metrics. PostHog is a Connection, so the Department survives provider changes.

Analytics accepts only a delivered shared campaign Artifact. Buffer post IDs,
platform metrics, website events, CTA activity, and leads are joined through
`campaign_id`, `batch_id`, `item_id`, `content_id`, and `creative_signature`.
If any of the ten rendition identities is missing or changed, the report is
incomplete and the campaign cannot teach the next batch.

## Full-capture configuration (owner directive 2026-08-18)

The consent gate was removed from `BaseLayout` on 2026-08-18
(goal-analytics-full-capture-v1-20260818): GA4 and PostHog load and initialize
unconditionally for **all visitors** — no banner, no consent gates, no
pre-consent event suppression. This restores measured traffic after the
consent-gated loader (deployed 2026-08-08, rewritten 2026-08-10) collapsed
captured events to near zero because non-clicking visitors and bots never
consented.

Current loader configuration:

- **Session replay stays ON** — `disable_session_recording` is never set.
- **`person_profiles: 'always'`** — anonymous person profiles are created for
  funnel analysis and session replay on unauthenticated traffic (documented
  requirement from the owner directive).
- **`mask_all_inputs: true`** — raw form values are never stored; the funnel
  events still count `lead_form_start` / `lead_form_submit` /
  `lead_form_success` without any form content.
- **Channel attribution via UTM** — PostHog captures `$utm_*` properties on
  `$pageview`; custom events carry `source` / `medium` / `campaign` /
  `content_id` through the loader's sessionStorage content-attribution
  context (`spielos.content-attribution`), which is preserved across
  navigation.
- **Lead-gen funnel events (current loader v4):**
  `lead_form_view`, `lead_form_start` (intent); `lead_form_submit`,
  `lead_form_success` (lead); `lead_form_error` (failure diagnostic);
  `content_landing` (attention), `cta_clicked` (engagement).
  Retired waitlist/agent-brief-era names (`agent_briefing_form_*`,
  `waitlist_form_*`, `click_contact`, `click_install`) are no longer emitted;
  their counts stay labeled `missing`, never zero.

## Content acquisition reporting contract

The daily content scorecard reports only non-PII evidence (full capture for
all visitors since 2026-08-18):

- qualified visits: `content_landing`, segmented by `source`, `campaign`, and
  `content_id`;
- service intent: `cta_clicked` where `cta_type` is `services` or
  `agent_briefing`;
- lead conversion: `lead_form_success` divided by `content_landing`;
- daily leads: `lead_form_success`, attributed to the last content UTM context
  in the same browser session.

Threads and YouTube Shorts must use `utm_source=threads|youtube`,
`utm_medium=social`, one campaign name, and a unique `utm_content` creative
identifier. Analytics events never include form fields or contact details.

The content scorecard joins each platform package's `creative_signature` with
Buffer's post ID and its later views/engagement metrics, then compares those
records with full-capture `content_landing`, service CTA, and lead events by
UTM.
CTR is defined as tracked website visits divided by the platform's reported
views; the 5% website lead-conversion rate is `lead_form_success / content_landing`.
Missing, delayed, or incomparable platform metrics are labelled incomplete and
never treated as business learning.

## Batch-learning loop

The operating cadence is ten batches of five paired Threads/YouTube ideas per
day. For each completed batch, Analytics records `batch_number`, `batch_item`,
`hook_id`, `narrative_type`, CTA, and creative signature alongside platform
views/engagement and full-capture website activity. It evaluates only
comparable, complete evidence: view rate, click-through rate, content
landings, service intent, and lead conversion. The next batch changes one documented variable by
default. It may change two or three only when a declared A/B, factorial, or
funnel design has complete control/variant cells and the analysis supports
every independent effect or a specific interaction. Otherwise Analytics
narrows the next test to one variable and marks simultaneous uncategorized
changes contaminated.

The `measured` handoff records the evidence window and canonical funnel math.
The `evaluated` handoff names one to three supported variables, the test type,
scope, evidence window, and next-batch hypothesis. Cross-channel creative and
website CRO remain distinct; website mutation always needs its own approval.
This closes the loop into the next Content strategy Artifact without Analytics
rewriting creative or authorizing delivery.

## Template dimension (funnel evidence schema v1.4.0)

Since analytics department 3.3.0 (change `change-e69f419da9`), the funnel
consumption step (`consume_batch_evidence` in `posthog.py`) carries a
`template_breakdown` block alongside the batch-level funnel:

- `_rendition_lines` takes `template_id` from each manifest item's design
  order; `_join_buffer_refresh` spreads it into the joined per-post rows.
- `template_breakdown.per_template` lists **per-template platform views**
  computed from those joined rows: for each registered archetype of the
  platform's kind (Registry order from the Design README) it reports
  `posts` (joined per-post rows) and `views` (sum) when every row measured
  views, or a **labeled missing entry** otherwise.
- Honesty rules are identical to the rest of the funnel: missing stays
  missing, never zero. A registered archetype with no per-post row in the
  batch still appears as a labeled missing entry, and rows whose
  `template_id` is not a registered archetype of the platform kind are
  labeled missing rather than dropped. When the manifest design orders are
  absent (receipts-only reads), the whole dimension is one labeled missing —
  never an invented zero.
- **Website events stay batch-level only.** `content_landing`, `cta_clicked`,
  and leads are not attributed per template because the loader has no
  per-post website tracking; the breakdown states this instead of inventing
  per-template attribution.
- `campaign_funnel_report` forwards the `template_breakdown` from the report
  unchanged into the typed analytics handoff (passthrough; the canonical
  funnel math is untouched).

The breakdown is `technical_only` delivery evidence like the rest of
`buffer_refresh`; it becomes business learning only through the complete
full-capture `funnel_report` handoff (see the Analytics skill).
