# Dashboard + Wizard Polish Plan — The Last 10%

The design is 90% done (Mintlify replica). The remaining 10% is polish, functionality, data integration, and icons. Goal: solid AAA design.

---

## Current Issues Summary

### Three Competing Design Systems
| File | Accent | Token names | Status |
|---|---|---|---|
| `index.html` (wizard) | `#26bd6c` | `--bg`, `--bg-raised`, `--fg`, `--fg-muted`, `--fg-faint`, `--accent` | Active |
| `dashboard.html` | `#499752` | `--bg`, `--bg-elevated`, `--bg-card`, `--fg`, `--fg-secondary`, `--fg-tertiary`, `--accent`, `--accent-glow` | Active |
| `design-system.css` | `rgb(38 189 108)` | `--bg-1` through `--bg-4`, `--tx` through `--tx-5`, `--bd`, `--ac` | **Orphaned** (1176 lines, never linked) |

### Missing `--warning` Variable (Real Bug)
`index.html:341` uses `color:var(--warning)` for the Buffer error message, but `--warning` is never defined in the wizard's `:root`. The error text renders with no color.

### Icons Not Working Everywhere (Root Causes)
- **CDN-only dependency**: Both HTML files load Font Awesome 6.5.2 from `cdnjs.cloudflare.com`. If the CDN is slow/down/offline, all icons break with no fallback.
- **Invalid `<i>` nesting** (`dashboard.html:417`): injects `<i class="fa-solid fa-file-lines"></i>` as innerHTML of an outer `<i>`, creating invalid nested `<i>` elements.
- **`design-system.css` CSS pseudo-element icons** (line 212-217): `content: '\f00c'; font-family: 'Font Awesome 6 Free'` — if FA hasn't loaded, shows blank squares.

### `design-system.css` Is Dead Code With Bugs
- **Line 92**: `@import url('...fonts...')` is placed AFTER `:root` and `*` rules. CSS spec requires `@import` before all other rules → browsers ignore this import.
- The stepper comment says "all 10 steps" but the wizard has 8 steps (0-7).
- Contains sophisticated components (stepper, sticky nav, toggle chips, funnel, banner preview, closer screen) that were never used.

### Massive Inline Style Hardcoding
73 `x-text`/`x-html` bindings across both files, many with inline `style=""` attributes. No shared utility classes for common patterns.

### No Consistent Scale
| Dimension | Wizard values | Dashboard values | Mintlify |
|---|---|---|---|
| Font sizes | 11, 12, 13, 14, 15, 24px | 11, 12, 13, 14, 15, 16, 22, 24px | systematic |
| Spacing | 4, 8, 10, 12, 16, 20, 32px | 3, 4, 5, 6, 7, 8, 10, 12, 14, 16, 20, 24, 32, 40, 48px | 4, 8, 16, 24, 32px |
| Radius | 6, 8, 10, 12px | 6, 8, 10, 12, 16px | 4, 8, 12, 9999px |

### How Mintlify Actually Designs (The Target)
- **Fonts**: Inter Variable + PaperMono Variable, self-hosted as `.woff2` (no Google Fonts CDN)
- **Icons**: Custom inline SVG, 1.5px stroke, `viewBox="0 0 18 18"` (no Font Awesome)
- **Tokens**: Semantic naming (`--color-background-primary`, `--color-foreground-secondary`, `--color-border-secondary`)
- **Typography**: Systematic classes (`typography-body-m-medium`, `typography-caption-l-regular`)
- **Shadows**: Very subtle (`0 1px 2px hsla(0,0%,0%,0.05)`)
- **Radius**: 4px, 8px, 12px, 9999px only
- **Aesthetic**: Minimal chrome, lots of whitespace, subtle borders, no heavy visual elements
- **Buttons**: `h-10` (40px), `rounded-xl` (12px), `text-sm/[20px]`, `tracking-[-0.1px]`
- **Inputs**: `h-10`, `rounded-xl`, focus ring: `shadow-[0_0_0_2px_var(--border-alpha-8)]`

---

## Phase 1: Critical Bug Fixes

| Bug | File | Fix |
|---|---|---|
| Missing `--warning` var | `index.html:12-19` | Add `--warning: #f59e0b;` to `:root` |
| Duplicate `team/strategist.md` | `serve.py:1058` | Remove the duplicate entry in `files_to_copy` |
| Hardcoded `wizardCompletedStep: 7` | `dashboard.html:1001` | Derive from `installed` state: `this.installed ? 7 : 0` |
| `<i>` inside `<i>` nesting | `dashboard.html:417` | Change outer `<i>` to `<span>`, keep `fileIconHtml` returning `<i>` or switch to SVG |
| `saveEnvCard` `:value` binding | `dashboard.html:877+` | Add `@input` handler to track dirty state, or switch to `x-model` with a temp proxy object |
| `design-system.css` `@import` at line 92 | `design-system.css` | Move `@import` to line 1 (before `:root`), or remove the orphaned file entirely |
| No Alpine.js fallback | both files | Add `<noscript>` message + check `window.Alpine` before `x-init` |

---

## Phase 2: Inline SVG Icon System (Replace Font Awesome)

Both files currently load ~300KB of Font Awesome from CDN. Mintlify uses ~0KB of icon libraries.

1. **Create an `icons.js` file** with a shared `ICONS` map of ~30-40 SVG paths (stroke-based, 1.5px, `viewBox="0 0 18 18"` — matching Mintlify's style). Icons needed:
   - Navigation: house, pen-to-square, gear, plug, key, tag, magnifying-glass
   - Actions: arrow-left, arrow-right, check, xmark, copy, floppy-disk, plus, trash, rocket, arrow-rotate-right, chevron-down, chevron-right, angles-left, angles-right
   - Status: circle-check, circle-exclamation, shield-halved, circle-xmark
   - Content: file-lines, file-code, file, paper-plane, file-circle-plus, file-circle-check
   - Wizard: palette, image, comment-dots, heart, face-smile, link, globe, plug, x-twitter
   - Banner: the SpielOS logo SVG (already inline)

2. **Replace all `<i class="fa-solid fa-*">`** in both HTML files with `<svg>` elements using the icon map. For dynamically-generated icons (file tree, nav, search results), use an Alpine `x-html` with a helper function that returns SVG markup.

3. **Fix `fileIconHtml()`** in dashboard to return inline SVG instead of `<i class="fa-solid">` tags.

4. **Fix `design-system.css`** pseudo-element checkmark (line 212-217) — replace with a CSS-only checkmark or inline SVG.

5. **Remove the Font Awesome CDN `<link>`** from both files.

---

## Phase 3: Design Polish (AAA)

Keeping the structure but making it solid:

1. **Harmonize tokens**: Ensure both `:root` blocks have the same variable names for the same concepts. Add `--warning`, `--danger`, `--warning-bg`, `--warning-fg`, `--success-bg`, `--success-fg`, `--danger-bg`, `--danger-fg` to the wizard's `:root` (dashboard already has them).

2. **Extract repeated inline styles** into utility classes:
   - `.label-sm` → `font-size:13px; font-weight:500; color:var(--fg-faint)`
   - `.label-xs` → `font-size:11px; font-weight:500; color:var(--fg-faint)`
   - `.hint-sm` → `font-size:12px; color:var(--fg-muted)`
   - `.grid-2` → already exists in dashboard, add to wizard
   - `.flex-col` → `display:flex; flex-direction:column; gap:N`

3. **Consistent focus states**: All interactive elements should have `:focus-visible` with `outline: 2px solid var(--accent); outline-offset: 2px` (dashboard has this on `:focus-visible` but wizard doesn't).

4. **Polish transitions**: Ensure all hover/focus transitions use the same `--ease` and duration (150ms for micro-interactions, 200ms for layout).

5. **Fix the wizard step badge**: The back button shows "Step 1 of 7" through "Step 6 of 7" but there are 8 steps (0-7). The badge should say "Step N of 7" where N matches the current step correctly.

6. **Splash screen**: The dashboard has a splash screen but the wizard doesn't. Add a lightweight one for consistency, or remove the dashboard's for leanness.

---

## Phase 4: Dashboard Data Integration

1. **Real wizard progress**: Replace `wizardCompletedStep: 7` with a computed property that checks `.install-state.json` presence and strategy file contents to determine actual progress.

2. **Pipeline state**: The pipeline visualization already reads from `runtime.state.step` — verify it handles all states (idle, capture, strategy, draft, edit, publish, complete, error) correctly and shows the right active step.

3. **Content file previews**: When clicking a draft/ready/posted file in the stat detail panel, load and show a preview of the file content (first 500 chars or frontmatter) instead of just showing the filename.

4. **Run events**: Format run events with proper timestamps, step names, and messages. Add color coding (green=info, amber=warning, red=error) — already partially done.

5. **Guard issues**: Show actionable fix suggestions for each guard issue type.

---

## Phase 5: Dashboard Functionality

1. **Search keyboard nav**: Add `@keydown.down.prevent`, `@keydown.up.prevent`, `@keydown.enter` handlers to cycle through `searchResults()`.

2. **Alpine.js fallback**: Add a `<div x-cloak>` fallback message: "If you see this, JavaScript failed to load. Check your connection."

3. **`runPost()` feedback**: After triggering `/api/post`, show the stdout output in a collapsible log panel, not just a toast.

4. **Editor**: Ensure all file types in `EDITABLE_FILES` are accessible from the file tree, including `system/brand.md`, `system/brand.json`, `system/rules.yaml`, `team/*.md`.

5. **Env var CRUD**: Verify add/update/remove all work and the UI reflects changes immediately.

---

## Phase 6: Verification

1. Run `python3 install/wizard/serve.py --port 7331 --target .` locally
2. Test each wizard step (0-7) in the browser
3. Test the dashboard at `/dashboard`
4. Verify all API endpoints respond correctly
5. Check browser console for errors
6. Verify all icons render (no broken/missing icons)
7. Test on desktop viewport (1440px width)
