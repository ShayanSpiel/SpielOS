---
name: seo
description: Set, review, and preserve SpielOS crawlability, indexability, canonicalization, hreflang, metadata, structured data, sitemap, robots, redirects, internal linking, image SEO, on-page semantic structure, and search-intent mapping. Use for any SEO implementation, review, audit, structured-data work, schema change, meta-tag work, or SEO validation after builds. Do NOT use for analytics implementation — use analytics skill instead.
---

# SpielOS SEO

SpielOS is a static Astro site (SSG) served at `https://spielos.xyz` with a Persian (`fa`, RTL) mirror under `/fa/`. Every indexable page must carry complete metadata, structured data, and internal linking. Preserve the existing architecture; move repeated concerns into shared owners (`BaseLayout`, layouts, `src/config.ts`).

## Scope

This skill owns:

- Crawlability and indexability
- Canonicalization and self-canonicalization
- Hreflang language alternates
- Page metadata (title, description, robots)
- XML sitemap and robots.txt
- Redirects and URL preservation
- Status-code integrity
- Internal linking and orphan-page detection
- Structured data (JSON-LD)
- Search Console verification
- Image SEO and alt text
- On-page semantic structure (headings)
- Search intent and page mapping
- SEO validation after builds

This skill does NOT own:

- Complete analytics implementation (see `.agents/skills/website/analytics/SKILL.md`)
- Editorial voice, readability rules, or copy style (see copywriting skills)
- Consent behavior, event taxonomy, attribution, or privacy configuration

## Before editing SEO

### For content-related SEO work, read:

1. `AGENTS.md` — routes, protected scope, i18n rules, icon rules
2. `src/config.ts` — `SITE`, `AUTHOR`, `FOUNDER`, `SEO`, `SOCIAL`, `ANALYTICS`
3. `src/layouts/BaseLayout.astro` — global head: meta, OG, hreflang, canonical, Search Console, Organization schema
4. `src/i18n/translations.ts` — all user-facing strings via `t(locale, key)`
5. `../../../company/strategy/icp.md` — canonical Ideal Customer Profile
6. `.agents/skills/website/copywriting-en/SKILL.md` — English copy quality
7. `.agents/skills/website/copywriting-fa/SKILL.md` — Persian copy quality
8. `.agents/skills/website/translation-fa/SKILL.md` — Persian translation quality
9. `persian-glossary.md` — Persian terminology

### Before analytics changes, read:

10. `.agents/skills/website/analytics/SKILL.md`

### Authoritative files

Treat `src/config.ts` and `BaseLayout.astro` as authoritative. Never hardcode site name, URLs, IDs, or metrics in page components.

SEO metadata and page copy must reflect:

- The canonical SpielOS ICP
- Reader awareness level
- Actual search intent
- Real product capabilities
- The page's purpose and its natural CTA

Do not write or optimize content based only on internal product taxonomy.

## Non-negotiable invariants

Every indexable page (`dist/*.html`, excluding 301 redirect stubs, `noindex` pages, and static assets) must contain:

- `<title>` — non-empty, unique across the site
- `meta description` — non-empty, unique across the site
- `canonical` link pointing to a valid, indexable URL
- `robots` meta (`noindex` only where intentional)
- `og:title`, `og:description`, `og:image`, `og:image:alt`, `og:type`, `og:locale`, `twitter:card`, `twitter:image`, `twitter:image:alt`
- Correct `lang` and `dir` attributes on `<html>`
- `google-site-verification` meta (Search Console)

## Metadata validation

### Required (build failures)

- Non-empty unique title
- Non-empty unique meta description
- Accurate page-specific metadata
- No placeholder or duplicated metadata
- Appropriate canonical URL
- Correct robots directive

### Recommended (warnings, not build failures)

- Concise descriptive titles, often around 30–65 characters
- Useful descriptions, often around 120–160 characters

Treat length as an editorial heuristic, not a search-engine requirement. Do not fail a build solely because a title or description falls outside those ranges. Warn when values are unusually short, long, repetitive, or likely to truncate badly.

## Structured data

### Policy

Every indexable page needs complete metadata. Add page-specific structured data only when it accurately represents substantial visible content on the page.

Distinguish:

- Valid schema.org vocabulary
- Structured data that helps entity understanding
- Structured data eligible for a Google rich result

Do not call all JSON-LD "rich snippets." Do not add generic `WebPage`, `AboutPage`, `ContactPage`, or `ItemList` merely to increase schema coverage. Remove `speakable` unless SpielOS deliberately publishes eligible news content. Do not imply that a generic `ItemList` of notes creates a Google carousel.

### Shared entity IDs

Implement stable shared IDs:

- `https://spielos.xyz/#organization` — Organization (emitted globally by BaseLayout)
- `https://spielos.xyz/#person` — Person (Shayan Spiel)
- `https://spielos.xyz/#website` — WebSite (homepage only)
- Page-specific URL IDs where useful

Ensure every referenced entity is defined in the page's JSON-LD graph or included through a shared global graph. Do not reference `#person` from `BlogPosting` when the page does not contain a corresponding Person node. Prefer a shared `@graph` architecture for stable entities and page-specific nodes.

### Per-page schema map

| Page type | Schema | Where |
|---|---|---|
| Homepage `/` | Person, WebSite, SoftwareApplication, BreadcrumbList | `src/pages/index.astro` |
| Founder `/founder/` | Person (enriched: alumniOf, knowsAbout, affiliation, worksFor), BreadcrumbList | `src/pages/founder.astro` |
| Notes index `/notes/` | CollectionPage, BreadcrumbList | `src/pages/notes/index.astro` |
| Note article `/notes/[slug]/` | BlogPosting, BreadcrumbList | `src/pages/notes/[...slug].astro` |
| Contact `/contact/` | BreadcrumbList | `src/pages/contact.astro` |
| Features hub + subpages | BreadcrumbList (auto in FeaturesLayout) | `src/pages/features/**` |
| Use-cases | BreadcrumbList when page is indexable | `src/pages/use-cases` |

### Schema rules

- Add page-specific schema as `<script type="application/ld+json" set:html={JSON.stringify(...)} />` inside the page/layout. Do not put page schemas in BaseLayout (except Organization).
- Breadcrumbs: `item` URLs must be localized with `localizePath(path, locale)` (FA pages point to `/fa/...`). Every ListItem needs an `item` (URL) and correct `position`.
- BlogPosting: include `headline`, `description`, `image`, `datePublished`, `dateModified`, `author` (ref `#person`), `publisher` (ref `#organization`), `mainEntityOfPage`, `keywords` (tags), `inLanguage`.
- SoftwareApplication: only on the product homepage when all marked-up information is visible and accurate.
- Do not invent facts. `alumniOf`, `affiliation`, `knowsAbout`, metrics come from `src/config.ts` (`FOUNDER`). Never fabricate reviews, ratings, or testimonials.
- Do not add FAQPage unless the page genuinely contains an FAQ accordion with matching visible content.
- JSON-LD must parse; all `@id` references must resolve.

### Validation

Validate:

- JSON syntax
- Required fields for Google-supported rich-result types
- Duplicate or conflicting `@id` nodes
- References to undefined nodes
- Visible-content consistency
- Crawlable image URLs
- Localized URLs and `inLanguage`

Use both Google Rich Results Test expectations for supported search features and general schema validation for schema.org correctness.

## Hreflang

Only emit a language alternate when a genuine equivalent page exists.

For each valid language cluster:

- Include a self-reference
- Include all equivalent language versions
- Use absolute URLs
- Keep the alternate set reciprocal and identical across variants
- Self-canonicalize each language version
- Keep canonical URLs in the same language whenever possible
- Use `x-default` only for the actual default or language-neutral destination
- Never point hreflang to a fallback page with materially different content

### Validation

Check for missing, asymmetric, broken, redirected, noindex, or noncanonical hreflang targets. The set must be identical on both sides: if page A references page B, page B must reference page A.

## XML sitemap

Verify:

- `/sitemap.xml` exists and parses
- Sitemap URLs are canonical, indexable, and return 200
- No redirect, 404, blocked, or noindex URL appears in the sitemap
- Every important indexable page appears in the sitemap
- Localized URLs and optional sitemap hreflang references are correct

Exclude noindex pages from the sitemap.

## robots.txt

Verify:

- `robots.txt` exists
- `robots.txt` references the sitemap
- Important assets and pages are not accidentally blocked
- `noindex` pages remain crawlable so crawlers can process the directive

## URL and migration integrity

Validate:

- Redirect map for all preserved Jekyll URLs
- No redirect chains
- No redirect loops
- No internal links to redirects
- No broken internal links
- No accidental staging, localhost, Vercel preview, or old-domain canonical URLs
- Consistent trailing-slash policy
- Canonical URLs return 200
- Redirect stubs are excluded from normal page requirements
- A useful localized 404 page exists and itself returns 404

## Internal linking

Verify:

- Every important indexable page is reachable through crawlable `<a href>` links
- No orphan indexable pages
- Important pages receive contextual internal links
- Anchor text describes the destination naturally
- Notes link to relevant features, use cases, services, and other notes
- Feature and use-case pages link back to relevant notes where useful
- English links stay in English routes and Persian links stay in `/fa/`
- No hardcoded English anchor text appears on Persian pages
- Internal links target canonical URLs directly

Do not add links mechanically. Every link must help the reader continue the current task or understand a related concept.

## Indexation policy

Do not permanently classify all use-case and guide pages as `noindex`. Indexation is determined page by page.

Use `noindex` for:

- Drafts
- Placeholder pages
- Thin pages
- Duplicate pages
- Temporary pre-launch routes
- Internal utility pages

Allow indexing when a use-case or guide page is:

- Complete
- Unique
- Helpful
- Connected to real search intent
- Supported by real product capabilities
- Internally linked
- Included in the sitemap
- Written for the canonical ICP

## Content SEO workflow

Before creating or optimizing a page, determine:

1. ICP segment
2. Awareness level
3. Primary reader problem
4. Search intent
5. Primary query or topic
6. Secondary supporting questions
7. Real SpielOS capability supporting the page
8. Existing page targeting the same intent
9. Appropriate internal links
10. CTA

Do not create a page merely because a keyword exists. A valid page must connect:

> Real search need → useful explanation → real SpielOS capability

Prevent:

- Keyword cannibalization
- Thin category pages
- Invented use cases
- Fake search demand
- Literal Persian keyword translations
- Pages that restate the same product inventory
- Pages generated only to fill a sitemap

## On-page semantics

The SEO checker may warn about:

- Missing or multiple unintended H1s
- Skipped heading levels
- Empty headings
- Extremely long unbroken text
- A long article with no useful subheadings
- Duplicate headings
- Missing descriptive alt text
- Generic link labels
- Unclear page introductions

Do not fail builds merely because:

- A paragraph exceeds four sentences
- A sentence exceeds 25 words
- A heading does not appear within an arbitrary viewport count

English and Persian readability must be evaluated separately through their corresponding copywriting skills.

## Image and social metadata

Verify:

- OG and Twitter images exist and return 200
- URLs are absolute
- Images are appropriate for the page
- Width, height, and MIME type are valid
- Important content images have meaningful alt text
- Decorative images use empty alt text
- Structured-data image URLs are crawlable and indexable
- Localized social copy matches the page language
- Default OG images are not used where a page-specific visual is required
- Every indexable route has a dedicated OG image from the registered archetypes
  (regenerate with `node scripts/generate-og.mjs`; templates in `src/og-templates/`,
  manifest mirrors each route's real `<title>`/description/URL; exact 1200x630)

## Analytics presence (not implementation)

The SEO skill may check that analytics is present (GA4, PostHog, Search Console verification) but must defer all implementation decisions to `.agents/skills/website/analytics/SKILL.md`.

## Verification workflow

After relevant changes, run:

```bash
npm run typecheck
npm run build
npm run seo:check        # runs scripts/seo-check.mjs against dist/
```

Also use commands for:

- Broken-link checking
- Sitemap validation
- Redirect testing
- Optional Lighthouse or performance-budget checks

For deployed SEO changes, include a manual checklist for:

- View-source metadata
- Rich Results Test where applicable
- URL Inspection
- Canonical selected by Google when available
- Hreflang cluster
- Search Console indexing status
- Analytics consent and event behavior (defer to analytics skill)

## seo:check reporting

The checker should report separately:

### Errors (fail deployment)

- Missing metadata
- Duplicate metadata
- Broken canonical
- Non-200 canonical
- Invalid robots directive
- Broken hreflang cluster
- Invalid JSON-LD
- Missing required properties for an intended rich-result type
- Broken internal link
- Orphan indexable page
- Sitemap containing invalid URLs
- Indexable page omitted from the sitemap
- Accidental staging URL
- Noindex page in sitemap
- Redirect chain
- Incorrect language or direction attributes

### Warnings (do not auto-fail unless promoted)

- Unusually long or short titles/descriptions
- Generic descriptions
- Weak anchor text
- Very long text blocks
- Missing optional structured-data fields
- Missing page-specific social image
- Sparse internal linking
- Possible query cannibalization
- Unexplained technical terminology
- Copy that does not clearly match the ICP or search intent

## Protected scope

Do not edit `src/components/showcase/*` (retired but protected). The legacy
waitlist route no longer exists — never reintroduce `waitlist.astro`, a
waitlist form, or `t(locale, "waitlist.*")` keys; conversion intent routes to
the Apply page (`/apply/`). Showcase analytics comes from BaseLayout (global) —
do not add inline analytics or page-specific schema inside showcase components.
Do not add hardcoded English to showcase components.

## Final report

After SEO work, report:

- Pages and page types changed
- ICP and search intent targeted
- Metadata changed
- Schema added, removed, or corrected
- Indexation changes
- Canonical and hreflang changes
- Sitemap and robots changes
- Redirects changed
- Internal links added or fixed
- Checks run and their results
- Warnings intentionally left unresolved
- Analytics or consent changes delegated to the analytics skill
