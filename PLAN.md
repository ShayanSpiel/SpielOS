# SpielOS Dashboard + Wizard — Plan & Status

**Last updated:** end of this session (2026-06-29)
**Goal:** Redesign the install wizard + post-install dashboard to match the Mintlify visual style. Fully functional, zero-hardcoded, data-driven, light and lean design system.

---

## What was done in this session

### Wizard (index.html + steps.js)

- [x] **Full design rewrite** — Mintlify-matching dark style: `rgb(5 6 6)` base, `rgb(24 23 22)` raised surfaces, `rgb(71 151 82)` green accent. Consistent tokens with dashboard.
- [x] **Step eyebrow pill** — Centered pill with green dot + "Step N of 6" label, matches Mintlify onboarding style.
- [x] **Typography** — `--text-4xl` for step titles, `--weight-extrabold` (800), `-0.03em` letter-spacing. Matches Mintlify heading hierarchy.
- [x] **Sidebar polish** — `260px` width, green radial-gradient logo, 12px border-radius on step items, active state with white border + green tint + glow (same as dashboard).
- [x] **Form fields** — `border-radius: var(--radius-xl)` (1rem) on inputs/textareas, proper focus ring with green box-shadow.
- [x] **Color pickers** — 36px swatches, 5-column grid, proper labels.
- [x] **Banner preview** — 1200x630 canvas with proper background icon watermark, silver gradient toggle.
- [x] **Done page** — Green check circle, closer-takeaway + closer-echo, done-list with file names, "What's next" command card.
- [x] **Auto-redirect** — After `finish()` succeeds, `setTimeout(() => window.location.href = '/dashboard', 2000)` automatically navigates to dashboard.
- [x] **Responsive** — Sidebar collapses to 56px on mobile, hides on <600px. Color grid adapts.

### Dashboard (dashboard.html)

- [x] **Full design rewrite** — Unified token set matching Mintlify palette exactly.
- [x] **Sidebar active state** — `color: var(--accent-glow)` (rgb(93 235 129)), `background: rgb(2 8 4 / 0.3)`, white border with inner glow. Matches Mintlify active sidebar item.
- [x] **Sidebar collapsed** — 64px width, icons centered, labels hidden. First-letter avatar shows in logo.
- [x] **Topbar "Complete your setup"** — Green dot pill button on left, matches Mintlify positioning.
- [x] **Hero preview frame** — 16:9 aspect ratio, `8px solid rgb(34 33 31)` ring, `22px` border-radius, box-shadow.
- [x] **Pipeline steps** — Data-driven via `pipelineSteps` array, not inline template literal.
- [x] **Activity table** — 22px border-radius, proper column headers (Update/Status/When), chevron per row.
- [x] **Stats cards** — `--text-2xl` bold values, proper labels and subtitles.
- [x] **Config/Brand** — Color fields with swatches + hex inputs, banner live preview, proper section headers.
- [x] **Editor defaults to `team/post.md`** — Changed from `team/strategist.md`.
- [x] **Editor handles `exists: false`** — Sets `activeContent = ''` instead of showing error.
- [x] **Search derives from data** — `searchResults()` builds file list from `fileGroups` array, not a static `fileItems` array. Zero hardcoded file paths.
- [x] **Config categories data-driven** — `configCategories` array renders the Settings secondary nav.
- [x] **File groups data-driven** — `fileGroups` array renders the Editor file tree, with `post.md` listed first in Team.
- [x] **All pages use `x-show` + `x-cloak`** — No `display:none` inline styles.
- [x] **No innerHTML injection** — breadcrumb, topbar-actions, search results all use Alpine template bindings.
- [x] **`navTo(page)` is pure state** — No DOM manipulation.

---

## Key design tokens (canonical)

```css
/* Surface */
--bg: rgb(5 6 6);
--bg-raised: rgb(24 23 22);
--bg-overlay: rgb(36 35 33);

/* Borders */
--border: rgb(47 45 43);
--border-subtle: rgb(33 32 30);

/* Text */
--fg: rgb(238 241 239);
--fg-muted: rgb(176 172 168);
--fg-faint: rgb(126 122 118);

/* Accent */
--accent: rgb(71 151 82);
--accent-glow: rgb(93 235 129);

/* Layout */
--sidebar-w: 260px;
--sidebar-collapsed-w: 64px;
--topbar-h: 72px;
--panel-w: 280px;
```

---

## Files modified

```
install/wizard/index.html    — Full design rewrite: Mintlify dark style, step eyebrow pills, polished sidebar/form/banner/done pages.
install/wizard/dashboard.html — Full design rewrite: unified tokens, data-driven pipeline/search, editor fixes, zero-hardcoding.
install/wizard/steps.js      — Added auto-redirect to /dashboard after finish() (2s delay).
install/wizard/serve.py      — No changes needed.
```

---

## What still needs verification

1. **Open browser and visually verify** — Run `python3 install/wizard/serve.py --port 7331 --target /tmp/spielos-test-vault` and screenshot every page.
2. **Icon audit** — Check each `fa-regular` icon renders (especially `fa-pen-to-square`, `fa-microphone`, `fa-shield-halved`, `fa-angles-left/right`, `fa-circle-xmark`). If any show as empty squares, swap to known-free alternatives.
3. **Test wizard flow** — Click through all 6 steps, verify banner preview updates, Finish writes files, auto-redirects to /dashboard.
4. **Test dashboard** — Click each sidebar item, verify page swap, editor loads team/post.md, Config saves, Connect env vars persist.

---

## How to test

```bash
mkdir -p /tmp/spielos-test-vault/{system,team,strategy,content/{drafts,posted,rejected,ready,runs,sessions},tools/bin,assets/icons,adapters,tests,archive/{roles,skills},install/wizard/skeletons,templates,plugins/spielos}
touch /tmp/spielos-test-vault/team/{strategist,writer,editor,publisher,post}.md
cat > /tmp/spielos-test-vault/system/brand.json <<'EOF'
{"name":"SpielOS","handle":"@spielos","tagline":"Test brand","role":"Founder, builder","colors":{"background":"#000000","title":"#ffffff","subtitle":"#8a8a8a","handle":"#505050","accent":"#5f8b4c"},"brand":{"name":"SpielOS","handle":"@spielos","primary_bg":"#000000","primary_fg":"#ffffff","subtitle_color":"#8a8a8a","handle_color":"#505050","accent":"#5f8b4c","tagline":"Test brand","creator_self":"Founder, builder"},"banner":{"template":"default","title_gradient":false,"dimensions":{"width":1200,"height":630},"tokens":{"text_title_color":"#ffffff","text_subtitle_color":"#8a8a8a","text_handle_color":"#505050","text_subtitle_max_chars":180,"bg":"#000000"}}}
EOF
cat > /tmp/spielos-test-vault/content/.state.json <<'EOF'
{"run_id":"2026-06-29-test","step":"draft","status":"active","drafts":["content/drafts/x.md","content/drafts/li.md"],"ready":["content/ready/x.md"]}
EOF
python3 install/wizard/serve.py --port 7331 --target /tmp/spielos-test-vault &
open http://127.0.0.1:7331/
open http://127.0.0.1:7331/dashboard
```
