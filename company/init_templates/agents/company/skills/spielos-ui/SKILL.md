---
name: spielos-ui
description: Preserve and polish the SpielOS interface through its semantic tokens, shared components, interaction contracts, theme mappings, and visual verification workflow. Use for any SpielOS UI implementation, review, refactor, component creation, layout or sidebar change, chat/runtime presentation, form or selection behavior, loading/error/success state, icon or typography adjustment, modal/popover/drawer work, animation, accessibility, theme work, or visual polish request.
---

# SpielOS UI

Polish the existing product without reskinning it. Move repeated decisions upward into tokens and primitives, then verify their consumers and states.

## Source of truth

The design system lives in the companion SpielOS product repo (path is
environment-specific; resolve it from your local checkout — for example via a
`SPIELOS_PRODUCT_REPO` environment variable — it is not inside this website
repository):

1. `packages/design-system/src/tokens/` — raw palettes + semantic mappings (`index.css`, `semantic-*.css`).
2. `packages/design-system/src/tokens/brand.ts` — brand mark geometry and static favicon palette (tile `#282828`, glyph `#ebdbb2`).
3. `packages/design-system/src/components/` — shared primitives (`BrandMark`, `Button`, `Icon`, etc.).
4. `docs/design-system.md` and `docs/interaction-design.md` — composition contracts.

The website mirrors the token files in `src/styles/tokens/` and must stay in sync. When tokens change upstream, copy the `semantic-*.css` and palette files, then re-add the website-only `--panel-deep` extension (the app has no alternating-section surface). The RTL font override in `index.css` keeps IRANSansX (not Vazirmatn) on this site.

## Before editing UI

Read these files:

1. `$SPIELOS_PRODUCT_REPO/docs/design-system.md` — tokens, hierarchy, surfaces, typography, icons, rules
2. `$SPIELOS_PRODUCT_REPO/docs/interaction-design.md` — selection, creation, loading, feedback, motion, accessibility
3. `src/styles/tokens/` — the website's theme mappings (10 themes)
4. `src/styles/base.css`, `src/styles/global.css` — site-level styles and RTL overrides
5. `src/components/SpielOSLogo.astro` — website logo (mirrors `BrandMark`)

Treat `packages/design-system` as authoritative when resolvable. If the product repo is not available in this environment, `src/styles/tokens/` plus the Website polish contract below are authoritative for this site. If code and docs disagree, fix the highest shared owner.

## Token contract

- Structural: radius (`sm` 4px, `md` 6px — **the maximum; there are no `lg`/`xl`/`pill` tokens, no pills, no circles**), motion (`fast/default/slow` + `--ease`), typography, `--bidi-sign` (±1 by direction), `--focus-border`/`--focus-ring`, `--disabled-surface`/`--disabled-border`/`--disabled-foreground`, `--skeleton-bg`, `--overlay-bg`, glass tokens (`--glass-*`), provider brand colors (`--provider-*`).
- Semantic colors (per theme): canvas (`--background`, `--background-deep`), surfaces (`--panel`, `--panel-raised`, `--panel-strong`, `--panel-deep` [website extension], `--input`), interaction (`--hover`, `--selected`, `--border`, `--border-strong`, `--ring`), text (`--foreground`, `--foreground-strong`, `--foreground-muted`, `--muted-foreground`), product (`--primary`, `--primary-foreground`, `--primary-soft`), status (`--success`, `--warning`, `--destructive`, `--info`, `--accent`, `--purple` + soft variants), code (`--code-block`), shadows (`--shadow-panel`, `--shadow-popover`).
- Never hardcode raw hex/rgb in page code. Theme differences come from token mapping, never component branches.
- Dark themes use `--code-block: <palette>_bg0_h`; light themes use `<palette>_bg1`.

## Brand mark

The logo is the official diamond mark (`BRAND_MARK_PATH` geometry) on a rounded tile. In-app and on the website, the tile follows the active theme (`bg-panel-raised`) and the glyph inherits `currentColor` (`text-foreground-strong`). Standalone assets (favicon, OG images) use the static palette from `brand.ts`: tile `#282828`, glyph `#ebdbb2`. Do not restate the shape or colors elsewhere; `SpielOSLogo.astro` and the OG templates `src/og-templates/og-single-fact.html` /
  `src/og-templates/og-pull-quote.html` (inline SVG brand lockup) are the website owners.

## Website polish contract (marketing pages)

These are the signature treatments that make a page look "finished". Every new
page or section must use them — a page without them reads as unstyled. Copy
the recipes verbatim; do not invent alternatives.

**Radius.** `rounded-md` everywhere (max). Never `rounded-full`/`rounded-pill`/`rounded-lg`/`rounded-xl`.

**Polished card** (the standard content card — hairline, lift, border shift):

```astro
<article class="group relative overflow-hidden rounded-md border border-border bg-panel p-6 shadow-panel transition-all hover:-translate-y-1 hover:border-border-strong">
  <div class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-primary via-accent to-transparent opacity-70" aria-hidden="true"></div>
  <!-- icon tile, heading, body -->
</article>
```

**Hairline gradient palette** (rotate by card index; keep `h-px`, `to-transparent`, `opacity-70`–`opacity-80`):
`from-primary via-accent` (default) · `from-accent via-purple` · `from-purple via-warning` · `from-purple via-info` · `from-warning via-primary`.

**Icon tile** (always square-ish `rounded-md`, soft background, boxicon):

```astro
<div class="flex h-10 w-10 items-center justify-center rounded-md bg-primary-soft">
  <i class="bx bx-{name} icon-xl text-primary" aria-hidden="true"></i>
</div>
```

Soft/text color pairs: `primary`, `accent`, `purple`, `success`, `warning`, `info` (e.g. `bg-accent-soft` + `text-accent`).

**Eyebrow / label chip** (mono, uppercase, widest tracking — never a pill):

```astro
<p class="inline-flex w-fit items-center gap-1.5 rounded-md bg-primary-soft px-3 py-1 font-mono text-2xs font-bold uppercase tracking-widest text-primary">
  <i class="bx bx-{name} icon-sm" aria-hidden="true"></i> Label
</p>
```

**Section headers** always come from `SectionHeader` (`label?`, `title`, `description?`, `align?`) — never hand-rolled. Its `label` renders the eyebrow.

**Section rhythm:** `<section class="relative py-24 sm:py-32"><div class="mx-auto max-w-6xl px-6">…</div></section>`; alternating bands add `overflow-hidden` + `<div class="absolute inset-0 bg-panel-deep/50"></div>` behind relative content.

**Glow blobs** (ambient depth behind heroes/sections — use the utilities, never inline radial gradients):

```astro
<div class="absolute left-1/2 top-[42%] h-[34rem] w-[52rem] -translate-x-1/2 -translate-y-1/2 glow-blob opacity-20" aria-hidden="true"></div>
```

Variants: `.glow-blob` (primary), `.glow-blob-accent`, `.glow-blob-purple`. Opacity `10`–`20`; keep them behind `relative` content.

**Buttons:** primary `inline-flex h-11 items-center justify-center rounded-md bg-primary px-6 text-sm font-semibold text-primary-foreground hover:brightness-110 active:brightness-95 transition-all`; secondary swaps to `border border-border bg-panel hover:bg-panel-raised hover:border-border-strong`. Hero/final-CTA tier: `h-12 px-8`.

**Scroll animation:** every section wrapper carries `data-aos="fade-up"` (AOS is initialized globally).

**Icons:** boxicons only (`<i class="bx bx-{name} icon-{xs…4xl}">`) — size utilities, never inline font-size; never `*-circle` variants; pair directional icons with `rtl-flip`.

If a treatment is missing from this list, extract it from an existing polished page (`src/pages/index.astro`, `services.astro`, `pricing.astro`) before inventing one.

## Workflow

### 1. Establish evidence

- Inspect current component, shared primitives, and callers.
- Render existing UI before changing visual behavior.
- Record affected states: resting, hover, active, focus, disabled, loading, success, warning, error, empty, overflow.
- Identify active theme. Include dark, light, and monochrome verification for shared changes.

Do not infer visual quality from class names alone.

### 2. Find the owner

Choose the highest correct layer:

1. Theme palette → raw colors
2. Semantic token → repeated meaning
3. Shared primitive → repeated appearance/behavior
4. Composition component → repeated product pattern
5. Page code → unique layout and content only

Do not patch multiple pages with the same class change. Create or correct the shared owner.

### 3. Preserve product structure

- Keep established architecture, density, and layout unless change is required.
- Avoid broad rewrites, decorative redesign, gradients, oversized type, floating cards.
- Use surface hierarchy, typography, spacing, state feedback before color or borders.
- Keep each change within one named pattern.

### 4. Implement complete states

- Use shared controls and semantic tokens.
- Give every action its full state contract (resting, hover, active, focus, disabled, loading, success, error).
- Preserve drafts and user input on failure.
- Match selection control to intent: radio, checkbox, switch, navigation, attach/detach.
- Use shared icon registry and named icon-button sizes.
- Use shared motion tokens; respect reduced motion.

Runtime messages, reasoning, workflow steps must come from native events. Never fabricate in UI copy.

### 5. Verify

```bash
npm run lint        # astro check + architecture checks
npm run build       # full static build (192 pages) + sitemap postbuild
npm run seo:check   # when metadata/schema changed
```

Run `npm test` when state/behavior changes.

Check for:
- Unexpected layout movement
- Nested or overly bright borders
- Incorrect icon scale
- Weak surface or type hierarchy
- Missing states (hover, focus, disabled, loading, error, success)
- Theme-specific contrast loss
- Stale loading after terminal state
- Keyboard traps and focus loss

### 6. Report

State which contract was fixed, which shared owner changed, which consumers verified, which checks ran.

## Rules

- Do not use raw colors, pixel typography, radius values, shadows, animation timing, or easing in app code.
- Do not import icon libraries outside the design system.
- Do not create page-local copies of shared controls.
- Do not use warning/error color for focus or selection.
- Do not represent navigation as a checkbox.
- Do not add borders where spacing or surface transition already groups.
- Do not update screenshot baselines until human reviews the change.
- **Chips, badges, buttons, cards, tiles, and containers are always `rounded-md` (or `rounded-sm` for tiny tags) — never `rounded-full`/`rounded-pill`/`rounded-lg`/`rounded-xl`.**
- **Exception — designed circles stay circles:** small status/indicator dots, timeline nodes, radar/ping rings, decorative particles, and traffic-light dots keep `rounded-full` (or `border-radius: 9999px`). Never square something that was deliberately circular, and never add circles to the chip/badge/card family.
- Timeline and node icons never get circle wrappers — icons sit directly on their spine or position.
- Ops and log pages may use a tighter section rhythm than the marketing default (`py-24 sm:py-32`), for example `py-16 sm:py-20`; the default stays for marketing sections.
- Do not build live status on a client framework — keep a small committed JSON in `public/` regenerated by a sync script, and poll it client-side every 30s with silent failure.
- Do not use infinite scroll for logs — render the top-N entries inline with one centered show-more button.
