# SpielOS Dashboard + Wizard — Plan & Status

**Last updated:** end of session
**Goal:** redesign the install wizard + post-install dashboard in the Mintlify visual style. All icons should be Font Awesome regular weight (line icons). Solid only for status accents.

---

## What's working

- `install/wizard/index.html` — newly written, single self-contained file. Sidebar step list (sticky, 240px) + main content area + sticky bottom footer with Back/Save&quit/Continue. 6 form steps + welcome + done. Inline Mintlify tokens. FA regular icons for everything, solid for status/check only. Bound to existing `wizard()` Alpine component in `steps.js`.
- `install/wizard/dashboard.html` — post-install dashboard, single self-contained file. Sidebar (Home/Editor/Connect/Config) + secondary nav panel (file tree on Editor, settings on Config) + topbar (breadcrumb + Save action) + content pages. All wired to `/api/*` endpoints.
- `install/wizard/serve.py` — adds `/api/dashboard` (with config + runtime.counts), `/api/config` POST (saves brand to `system/brand.json` + `system/brand.md`), `/api/post` (triggers `spiel post`), `/api/buffer/channels` (POST, calls Buffer REST API for profiles). `runtime_snapshot()` returns counts: drafts, ready, posted, rejected, errors, warnings.
- `install/wizard/steps.js` — minimal `wizard()` Alpine component. `current` state, `next/back/go/closeTab`, `finish` POSTs to `/api/finish`, `loadSkeletons` reads from `/api/skeleton/*`, `fetchBufferChannels` POSTs to `/api/buffer/channels`. localStorage persistence.
- `install/wizard/steps.js` form state has all fields: brand_name, handle, tagline, creator_self, role, primary_bg, primary_fg, subtitle_color, handle_color, accent, title_gradient, audience_content, offer_content, voice_content, examples_content, buffer_token, buffer_channels, x_api_key, x_api_secret, x_access_token, x_access_secret, linkedin_access_token, linkedin_person_urn, blog_repo, blog_token (and a few unused: wp_*, devto_*, hashnode_*, custom_blog_*).
- `/api/dashboard` returns: `target`, `installed`, `editable`, `runtime: {state, current, runs, guard, counts}`, `config` (loaded from brand.json/md).
- FA CSS link: `https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css` — confirmed 200.
- Inter font loaded from Google Fonts.

---

## Open issues (user-reported)

### Dashboard
1. **"icons not showing"** — user says icons in sidebar/UI look solid when they should be regular. CSS class names are correct (`fa-regular fa-house` etc.) — likely the user is seeing the *icons rendered by FA*, but the style feels heavy. Possible: `font-size` and `stroke-width` look off. Need to verify in browser.
2. **"pages not clickable"** — `[x-cloak]` CSS rule was missing from `dashboard.html`. **Fixed** during this session by adding `[x-cloak] { display: none !important; }` to the inline CSS. But user still reports this — could be Alpine init error. Need to verify the page is actually rendering with Alpine.
3. **"home numbers show draft paths"** — `runtime.state.drafts` was an array of paths, used as `x-text` which rendered the array as comma-joined string. **Fixed** by adding `runtime.counts.{drafts,ready,posted,rejected,errors,warnings}` to `runtime_snapshot()` in serve.py and switching the home stats to use `runtime.counts.*`.
4. **"Activity needs tabs + per-row buttons"** — fixed: home now has 3 tabs (Runs/Errors/Guards) with count badges, plus per-row `<button class="btn-icon">` for view/copy. Tab content swaps via `x-show` on `activeTab`. `.tab-count` shows counts with `.alert` (red) and `.warn` (amber) variants.
5. **"File editor files can't be selected"** — fixed: file tree is now `template x-for` driven by `fileGroups` array (in Alpine state), each item has `data-page` style `selectFilePath(path)`. `activeFile === f.path` binding for the active state. Replaces the old broken `selectFile(this)` that read `el.textContent` and got just the filename (e.g. "strategist.md") instead of the full path.
6. **"Search ⌘K"** — added. Search overlay with `position: fixed`, `backdrop-filter: blur(8px)`, ESC closes, searches files + env vars + runs. Wired via `openSearch()` triggered by the search button or Cmd+K.
7. **"Sidebar collapse"** — fixed. Toggle button label is now dynamic (`'Expand' | 'Collapse'`), icon is `fa-angles-right` when collapsed and `fa-angles-left` when expanded.
8. **"GitHub Pages / WordPress Configure buttons do nothing"** — fixed: replaced the hardcoded connect-grid with a real Blog card that has a `BLOG_REPO` + `BLOG_TOKEN` field and a `Save all` button. The X/LinkedIn cards now have a `Save all` button too via `saveEnvCard(event)` which reads all `input[data-env-key]` siblings and saves them.
9. **"API Keys / Rules config categories do nothing"** — fixed: 6 config categories now render distinct sections via `x-show="activeConfigCat === 'brand' | 'audience' | ...`. Each config category has its own content. Brand saves via `/api/config`. Audience/Offer/Voice load and save via `/api/file` (strategy/{key}.md). Rules loads and saves via `/api/file` (system/rules.yaml). API Keys redirects to Connect page.
10. **"Hardcoded 'Shayan' / 'S' avatar"** — fixed. Greeting reads `config.handle` (`@spielos` → `spielos`). Avatar shows first letter of handle.

### Wizard
11. **"wizard not changed at all"** — fixed during this session. Wrote a new `install/wizard/index.html` with sidebar + content layout. Self-contained (no external CSS), Mintlify tokens, FA regular icons, 6 form steps + welcome + done. Uses existing `steps.js` `wizard()` function.
12. **"Design not matching"** — wizard now uses the same color tokens, font, FA icons, and layout pattern as the dashboard.

### Wizard ↔ Dashboard wiring
13. The wizard finishes by writing `system/brand.json` and `system/brand.md` (via `serve.py:write_brand()`). The dashboard reads from those same files via `load_brand_config()`. The token names are mapped: form has `primary_bg`, `primary_fg`, `subtitle_color`, `handle_color`, `accent` — and these get saved to `brand.json` under `colors.{background,title,subtitle,handle,accent}`. The loader reverses the mapping. Round-trip should work.

---

## Files modified

```
install/wizard/index.html      — completely rewritten (self-contained, no design-system.css dep)
install/wizard/dashboard.html  — has [x-cloak] fix + tabs + file tree + search + sidebar collapse
install/wizard/steps.js        — wizard() only; dashboard has its own Alpine dashboard() inline
install/wizard/serve.py        — adds /api/dashboard, /api/config POST, /api/post, /api/buffer/channels, runtime.counts
```

`install/wizard/design-system.css` — **unchanged this session** (the wizard now inlines its CSS, doesn't depend on this file).

`install/wizard/steps.js` — restored from git to the version that works with the new wizard.

---

## What still needs to be done

### High priority
- [ ] **Visual verify in browser.** The user is the only one who can see the browser. Open `http://localhost:7331/` (wizard) and `http://localhost:7331/dashboard` (dashboard). Both should render correctly. If not, capture a screenshot or describe what is wrong.
- [ ] **Verify sidebar icons render as FA regular (line) not solid (filled).** If they look heavy, the user can override with CSS `font-weight: 400` or `font-variation-settings: "wght" 300`. FA regular typically has thinner stroke.
- [ ] **Verify all 4 sidebar pages are clickable** (Home/Editor/Connect/Config). If not, check browser console for Alpine errors.

### Medium priority
- [ ] **Add a "Connect" step to the wizard** that matches the dashboard's Connect page (Buffer + X + LinkedIn + Blog). The current wizard has these as form fields but the layout is form-list — could be improved.
- [ ] **Wizard completion** — after `/api/finish`, redirect to `/dashboard` instead of staying on the wizard. The current "Open dashboard" button is a link, but auto-redirect would be smoother.
- [ ] **Dashboard wizard entry** — when user is on `/dashboard` and clicks something, but the vault is not installed, show a CTA to run `spiel init`.

### Low priority
- [ ] **Move shared design tokens** into `install/wizard/design-system.css` and have both `index.html` and `dashboard.html` `<link>` to it. Currently both files inline the same tokens.
- [ ] **Remove `design-system.css` from `install/wizard/`** if no longer needed (depends on above).
- [ ] **Add tests** for the new endpoints: `/api/dashboard`, `/api/config` POST, `/api/post`, `/api/buffer/channels`.

### Cleanup
- [ ] `archive/preview/preview.html` and `archive/preview/mintlify-preview.html` are still there. Can be removed.
- [ ] Old `wizard()` references in the deleted code (anything that called `wizard()` should now be handled by the inlined dashboard's `dashboard()` function — but the dashboard doesn't import `steps.js`, it has its own JS).

---

## Architecture decisions made

- **Two files, not one:** `index.html` is the install wizard, `dashboard.html` is the post-install view. Both are served by the same `serve.py` (mounted at `/` and `/dashboard`).
- **Self-contained per file:** Each HTML file inlines its CSS, JS, and tokens. This means a design system file isn't strictly needed, but it's still in the repo and could be re-introduced.
- **Wizard `wizard()` Alpine component lives in `steps.js`.** Dashboard `dashboard()` Alpine component lives inline in `dashboard.html`. Two separate Alpine roots, two separate JS contexts. They're not aware of each other.
- **No merge of wizard + dashboard into one file** (per user feedback — the user wants them as separate files but visually consistent).
- **API contract:** `runtime_snapshot()` returns counts. `load_brand_config()` returns a flat dict that matches the form. `save_brand_config()` accepts the same flat dict and persists to both `brand.json` and `brand.md`.

---

## How to test

```bash
# Build a test vault
mkdir -p /tmp/spielos-test-vault/{system,team,strategy,content/drafts,content/posted,content/rejected,content/ready,tools,bin}
touch /tmp/spielos-test-vault/team/strategist.md
echo '{"name":"SpielOS","handle":"@spielos","tagline":"Test","colors":{"background":"#000","title":"#fff","subtitle":"#8a8a8a","handle":"#505050","accent":"#5f8b4c"}}' > /tmp/spielos-test-vault/system/brand.json
cat > /tmp/spielos-test-vault/content/.state.json <<EOF
{"run_id":"2026-06-29-test","step":"draft","status":"active","drafts":["content/drafts/x.md","content/drafts/li.md","content/drafts/blog.md"],"ready":["content/ready/x.md"]}
EOF

# Start the server
python3 install/wizard/serve.py --port 7331 --target /tmp/spielos-test-vault &

# Open in browser
open http://127.0.0.1:7331/         # wizard
open http://127.0.0.1:7331/dashboard # dashboard
```

Verify in the browser:
- Wizard: sidebar shows 6 steps, click any step to jump to it, fill brand form, banner preview updates live, click Finish to install.
- Dashboard: home shows stats 3/1/3 (drafts/ready/posted), activity tabs work, click Editor → file tree on left → click any file → content loads.

---

## User pain points captured

- "MAKE sure you check every single button, icon, component, wrapper" — every interactive element should be wired.
- "Icons and collapsed sidebar is bad" — visual design needs more iteration.
- "the numbers on home is not showing numbers but draft paths" — fixed via `runtime.counts`.
- "in activity preview we need small buttons and make it tab for errors/guards, drafts remaining etc" — fixed via tabs + btn-icon.
- "The file editor files cant be selected" — fixed via data-driven file tree.
- "this page is open in browser if you want to check it's design" — user is the visual reviewer, I can't see the browser.
- "wizard also not changed at all" — wizard was rewritten.
- "its open for me on browser" — user can see the browser; I cannot.
- "icons still not working, fontawesome we use and they still are solid, make them no solid" — needs visual verification, may need to swap some `fa-solid` → `fa-regular`.
- "still pages not clickable, probably syntax errors" — `[x-cloak]` was the likely culprit; verify in browser.
- "this is the page we based for wizard design: https://app.mintlify.com/onboarding — just take the design style but put our fcntions" — the user wants Mintlify visual style, not Mintlify code. Used preview.html/dashboard.html as the visual reference instead.
- "let's do something, save the last status on a plan file on root with all issues currently for a new session" — this file.

---

## Key file paths

- `/Users/shayan/Desktop/SpielOS/install/wizard/index.html` — wizard (rewritten, self-contained)
- `/Users/shayan/Desktop/SpielOS/install/wizard/dashboard.html` — dashboard (functional but visual polish needed)
- `/Users/shayan/Desktop/SpielOS/install/wizard/steps.js` — wizard() Alpine component
- `/Users/shayan/Desktop/SpielOS/install/wizard/serve.py` — server with all API endpoints
- `/Users/shayan/Desktop/SpielOS/install/wizard/design-system.css` — legacy wizard CSS, not used by new files
- `/Users/shayan/Desktop/SpielOS/archive/preview/preview.html` — original preview, archived
- `/Users/shayan/Desktop/SpielOS/archive/preview/mintlify-preview.html` — original preview, archived

---

## Next session priority

1. **Open the browser, take a screenshot of the wizard + dashboard, share with me.** I can't see the browser — I need visual feedback to fix visual issues.
2. **If icons are still "solid looking"** — try `font-weight: 300` on the FA `i` elements, or switch to Font Awesome 7 which has a thinner "thin" style. The current CSS has no `font-weight` set, so FA defaults to 400 which is the regular weight, but visually it can still look heavy at small sizes.
3. **If pages are still not clickable** — open browser dev tools, look at the console, share the error.
4. **Once visual is solid** — commit, push, run `spiel update` to test the full flow.
