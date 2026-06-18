# banner_tool

Self-contained Python module + CLI for generating banner images (X / LinkedIn / blog OG cards).

- **One entry point** for the engine, the post subagent, the CLI, and tests.
- **CSS-variable-driven templates** — every visual knob is a `--token` you can restyle.
- **Plug-and-play templates** — drop a new `.html` file in `scripts/banner-templates/`, refresh the browser, see it.
- **Live preview** — `python3 -m banner_tool preview --open` writes a real HTML file and opens it.
- **Playwright + system Chrome** — no Node, no Puppeteer, no shell-out dance.
- **Snapshot regression test** — render once, check the PNG in, fail on >2% pixel drift.

---

## Quick start

```bash
# 1. Install (uses your existing Python 3.11+ venv)
pip install playwright
playwright install chromium    # one-time, ~200MB

# 2. Generate a banner for one queue draft
python3 -m banner_tool generate-draft --file content/queue/2026-06-17-x.md

# 3. Generate banners for every draft in the queue
python3 -m banner_tool generate-queue

# 4. Render a manual banner (great for one-offs)
python3 -m banner_tool render \
    --template default \
    --title "Build a content engine" \
    --subtitle "The 30-min pipeline from session to post" \
    --out assets/banners/my-banner.png

# 5. Open a live HTML preview in your browser (edit + refresh)
python3 -m banner_tool preview --template default --open

# 6. Run the snapshot regression test
python3 -m banner_tool test
```

The engine calls `banner_tool.generate_for_queue(VAULT)` automatically inside its `BANNER` state — you don't need to invoke the CLI for the normal pipeline.

---

## How it works

```
┌────────────────────────────────────────────────────────────────┐
│  Callers:  engine.py  •  post subagent  •  CLI  •  pytest     │
└─────────────────────────┬──────────────────────────────────────┘
                          │ (one entry point)
                          ▼
                 ┌──────────────────┐
                 │  banner_tool.py  │
                 └─────────┬────────┘
                           │
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
   load_tokens()     load_template()    render_png()
   brand-config.json banner-templates/  Playwright + Chrome
       ↓                 ↓
   banner.tokens    default.html
                    (CSS :root block)
                           ↓
                 build_html()  ← only rewrites :root + 4 content placeholders
                           ↓
                 render_png()  ← HTML → PNG via system Chrome
```

**The single source of truth principle** — each concern lives in exactly one place:

| Concern               | Lives in                                       |
|-----------------------|------------------------------------------------|
| Colors, sizes, fonts  | `assets/brand-config.json → banner.tokens`     |
| Layout, CSS rules     | `scripts/banner-templates/*.html` (CSS)        |
| Render settings       | `assets/brand-config.json → banner.render`     |
| Icon → keyword rules  | `assets/brand-config.json → banner.icon_mapping` |
| Icon SVG files        | `assets/icons/*.svg`                           |
| Output dimensions     | `assets/brand-config.json → banner.dimensions` |
| Template name         | `assets/brand-config.json → banner.template`   |

The tool reads tokens from JSON, injects them into a single CSS `:root` block in the template, and renders. **No token-replace soup. No layout duplication.**

---

## The CSS contract

Every template must have a `:root` block at the top of its `<style>`. The tool rewrites ONLY this block at render time. Here is the full public contract — every variable the tool writes:

```css
:root {
  /* Dimensions */
  --width:  1200px;   /* From banner.dimensions.width  */
  --height:  630px;    /* From banner.dimensions.height */

  /* Background */
  --bg:                #e8e8e8;

  /* Fonts */
  --font-heading:      'Inter', -apple-system, sans-serif;
  --font-subtitle:     'Merriweather', Georgia, serif;

  /* Title (big orange text) */
  --text-title-color:         #ff6a00;
  --text-title-size:          96px;     /* auto-scaled down for long titles */
  --text-title-weight:        900;
  --text-title-lh:            1.1;
  --text-title-letterspacing: -0.03em;

  /* Subtitle (yellow-highlighted one-liner) */
  --text-subtitle-color:      #202020;
  --text-subtitle-size:       32px;
  --text-subtitle-weight:     400;
  --text-subtitle-lh:         1.4;
  --text-subtitle-letterspacing: 0.02em;
  --text-subtitle-highlight:  rgba(255, 228, 77, 0.3);

  /* Handle (small text at bottom) */
  --text-handle:              #5a5959;
  --text-handle-size:         22px;
  --text-handle-weight:       400;
  --text-handle-letterspacing: 0.04em;
  --text-handle-align:        center;   /* center | left | right */
  --text-handle-bottom:       32px;

  /* Icon (background watermark) */
  --icon-color:       #444444;
  --icon-opacity:     0.30;
  --icon-size:        120%;    /* % of body width */
  --icon-rotate:      30deg;
  --icon-position-x:  right;   /* right | left | center | top | bottom */
  --icon-position-y:  center;
  --icon-offset-x:    -10%;
  --icon-offset-y:    -50%;

  /* Content area */
  --content-padding:  60px 80px 80px;   /* CSS shorthand */
  --content-width:    85%;
  --text-align:       left;              /* left | center | right */
}
```

You can use any subset — if a variable isn't in your `:root`, the tool just won't overwrite it. But for consistency, the default template uses all of them.

---

## Token unit rules

CSS is strict about units. The tool passes values from `banner.tokens` straight into CSS, so every numeric value **must include its unit** in `brand-config.json`:

| Token                         | Example value     | Why                        |
|-------------------------------|-------------------|----------------------------|
| `text_title_size`             | `"96px"`          | Length needs a unit        |
| `text_title_size_min`         | `56`              | Number only (auto-scale)   |
| `text_title_weight`           | `900`             | Unitless (CSS font-weight) |
| `text_title_lh`               | `1.1`             | Unitless (CSS line-height) |
| `text_subtitle_max_chars`     | `80`              | Number only (truncation)   |
| `text_handle_bottom`          | `"32px"`          | Length needs a unit        |
| `icon_opacity`                | `0.30`            | Unitless (CSS opacity)     |
| `icon_size`                   | `"120%"`          | Percentage                 |
| `icon_rotate`                 | `"30deg"`         | Angle                      |
| `icon_offset_x` / `_y`        | `"-10%"` / `"-50%"` | Percentage                |
| `content_padding`             | `"60px 80px 80px"` | CSS shorthand             |

The tool uses `_strip_unit()` to safely parse these for internal math (auto-scaling, padding calc).

---

## Adding a new template

1. **Copy** `scripts/banner-templates/default.html` to `scripts/banner-templates/{name}.html`.
2. **Restyle** the `:root` block + any CSS rules. Layout, color, font — whatever you want.
3. **Open** `default.html` in your browser to see the showcase. To see your new template, run:
   ```bash
   python3 -m banner_tool preview --template {name} --open
   ```
4. **Edit + refresh** the browser. The preview HTML is regenerated each time.
5. **Test** that the tool can render it:
   ```bash
   python3 -m banner_tool render --template {name} --title "Test" --out /tmp/test.png
   ```
6. **Activate** it by editing `assets/brand-config.json`:
   ```json
   {
     "banner": {
       "template": "{name}",
       ...
     }
   }
   ```

That's it. No Python code to write. The tool reads the template, injects the brand tokens, renders to PNG. Same pipeline for every template.

---

## Live preview workflow

```bash
# 1. Write preview HTML to assets/banners/.preview/{template}.html and open it
python3 -m banner_tool preview --template default --open

# 2. Edit the template
$EDITOR scripts/banner-templates/default.html

# 3. Re-run preview (regenerates the HTML, but doesn't re-open)
python3 -m banner_tool preview --template default

# 4. Refresh the browser tab (or re-run with --open)
```

The preview HTML is what the tool will render to PNG. **What you see in the browser is what you ship.** No more "render → check PNG → re-render" feedback loop.

The preview directory (`assets/banners/.preview/`) is gitignored.

---

## Python API

```python
from pathlib import Path
from banner_tool import (
    load_tokens, load_template, build_html, render_png,
    generate, preview, generate_for_draft, generate_for_queue,
    find_chrome, test_snapshot,
)

# Low-level: assemble tokens + template + content into HTML
tokens = load_tokens(Path("/path/to/vault"))
tmpl   = load_template(Path("/path/to/vault"), "default")
html   = build_html(tmpl, tokens, "Title", "Subtitle", "@handle", Path("/path/to/vault"))

# Render to PNG
ok = render_png(html, Path("out.png"), width=1200, height=630, scale=2)

# High-level: end-to-end for one title
out = generate(
    vault=Path("/path/to/vault"),
    template="default",
    title="My Title",
    subtitle="My Subtitle",
    out_path=Path("assets/banners/my.png"),
)

# Generate for a queue draft (reads frontmatter, writes banner: back)
out = generate_for_draft(Path("/path/to/vault"), Path("content/queue/x.md"))

# Generate for every draft in content/queue/
outs = generate_for_queue(Path("/path/to/vault"))

# Write a preview HTML (no PNG)
preview(Path("/path/to/vault"), "default", open_browser=True)

# Run the snapshot regression test
test_snapshot(Path("/path/to/vault"))
```

The `vault` argument defaults to the `VAULT_DIR` env var, falling back to the parent of `scripts/`.

---

## CLI reference

```
python3 -m banner_tool render --template <name> --title "..." [--subtitle "..."] --out <file>
    Render one banner to a PNG file.

python3 -m banner_tool preview --template <name> [--title "..."] [--subtitle "..."] [--open]
    Write a preview HTML to assets/banners/.preview/{name}.html.
    With --open, launch the system browser at the file.

python3 -m banner_tool generate-queue
    Walk content/queue/*.md, render a banner for each, write
    `banner: assets/banners/{stem}.png` back into the frontmatter.

python3 -m banner_tool generate-draft --file <path>
    Render a banner for one draft and update its frontmatter.

python3 -m banner_tool test
    Render the snapshot test. First run creates tests/snapshots/default.png;
    subsequent runs fail on >2% pixel drift.
```

---

## Single source of truth (the design)

The old banner tool (`scripts/banner.py`, deleted) had:

- 30+ `__TOKEN__` placeholders in the HTML template, 30+ matching `.replace("__TOKEN__", ...)` calls in Python. Adding a style knob required editing both. ❌
- Layout config in `brand-config.json` AND in the CSS template. Drift. ❌
- Three fallback sources for the background color. No precedence guarantee. ❌
- Two duplicated engine call sites (`cmd_content_banner` and `_step_banner`). Bug fixes went stale in one. ❌
- Node + Puppeteer shell-out, with Puppeteer not actually in the repo. Worked by accident via `~/.npm/_npx`. ❌
- No live preview. Render → check PNG → re-render. ❌

This tool:

- **One** place for visual knobs: the CSS `:root` block in the template (overwritten by brand tokens at render time). ✅
- **One** source of truth per concern (table above). ✅
- **One** entry point (`banner_tool.py`) used by engine, subagent, CLI, and tests. ✅
- **One** render path (Playwright + system Chrome). ✅
- **One** preview command — `banner_tool preview --open`. ✅

---

## Troubleshooting

### "no Chrome binary found"

The tool searches these locations (in order):

1. `$BANNER_CHROME_PATH` env var
2. `assets/brand-config.json → banner.render.chrome_path`
3. `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` (macOS default)
4. `/usr/bin/google-chrome` (Linux)
5. `/usr/bin/chromium` / `/usr/bin/chromium-browser`
6. Windows Chrome paths

If none of these exist, install Chrome (macOS: `brew install --cask google-chrome`).

### "icon file not found"

The tool falls back to an empty icon (no watermark) and prints a warning. To fix, either:
- Add the missing icon to `assets/icons/{name}.svg`, or
- Change `banner.icon_mapping.rules[*].icon` to point to an existing icon, or
- Set `banner.icon_mapping.default` to a different icon.

### "no :root CSS block"

Templates must have a `:root { ... }` block at the top of `<style>`. The tool validates this on load. If you copy a template from elsewhere, make sure the `:root` block is there.

### Snapshot test fails on a non-meaningful change

If you've intentionally changed the design (e.g. updated colors), regenerate the snapshot:
```bash
rm tests/snapshots/default.png
python3 -m banner_tool test
```

Then commit the new snapshot.

### "Page never finishes loading" / Playwright hangs

Make sure you're not behind a network that blocks the Google Fonts CDN. The tool has a 2-second `load` timeout and falls back to system fonts. If you're fully offline, edit the template to remove the `@import url(...)` for Google Fonts — system fonts (`-apple-system, sans-serif`) will be used.

---

## Tests

```bash
# Run all banner tool tests
python3 -m pytest tests/test_banner_tool.py -v

# Run just the snapshot regression
python3 -m pytest tests/test_banner_tool.py::test_snapshot_default -v
```

15 tests cover:

- Token loading + required-key validation
- Template loading + `:root` contract enforcement
- Icon keyword matching + fallback
- Title splitting (1-3 lines)
- Title auto-scaling (clamps to min, fits width + height)
- HTML builder (CSS vars injected, placeholders replaced, icon position class, subtitle truncation)
- End-to-end PNG generation
- `generate_for_draft` (PNG + frontmatter write)
- Snapshot regression (pixel diff < 2%)

---

## Files

```
scripts/
  banner_tool.py                      ← the tool
  banner-tool.README.md               ← this file
  banner-templates/
    default.html                      ← default template
    {name}.html                       ← your custom templates

assets/
  brand-config.json                   ← banner.tokens, banner.render, banner.icon_mapping
  icons/                              ← SVG icons
  banners/                            ← generated PNGs (gitignored)
  banners/.preview/                   ← preview HTMLs (gitignored)

tests/
  test_banner_tool.py                 ← 14 unit + 1 snapshot
  snapshots/
    default.png                       ← reference render (checked in)
```

---

## Related

- `AGENTS.md` — `### Banner Tool` section with the canonical contract.
- `assets/brand-config.json` — `banner` section is the canonical config.
- `scripts/engine.py` — calls `banner_tool.generate_for_queue(VAULT)` in the `BANNER` state.
- `PORTING.md` — porting notes for the sibling `TheSpielEngine` repo.
