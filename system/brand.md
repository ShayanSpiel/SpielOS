# Brand

The brand identity for your content. Banner rendering is dormant (Designer role is archived), but the tokens stay here so the wizard has a single home for visual identity and the machine-readable mirror is at `system/brand.json`.

The wizard writes both files from your inputs in step 2 (Brand). Keep them in sync by re-running the wizard with `spiel init`.

---

## Required fields

```yaml
brand:
  name: <your project / company name>
  handle: <@your_handle>
  primary_bg: <hex>            # default #000000 (banner background)
  primary_fg: <hex>            # default #ffffff (banner title color)
  accent: <hex>                # default #ff6a00 (accents, links)
  text_dark: <hex>             # default #202020
  text_mid: <hex>              # default #5a5959
  tagline: <one line, max 80 chars>
  creator_self: <one line that introduces the writer, e.g. "I am a builder.">

fonts:
  heading: <font name>         # default Inter
  subtitle: <font name>        # default Merriweather
  mono: <font name>            # default JetBrains Mono (for @handle)
  use_google_fonts: true|false

banner:
  template: <default|notes>    # see tools/designer.py (dormant)
  width: 1200
  height: 630
  device_scale_factor: 2
```

## Optional tokens (advanced)

These map to the dormant designer's `:root` CSS variables. Defaults are listed; override only if you know what you want.

```yaml
banner_tokens:
  text_title_size: "120px"
  text_title_size_min: 56
  text_title_weight: 900
  text_title_lh: 1.02
  text_title_letterspacing: "-0.05em"
  text_subtitle_size: "30px"
  text_subtitle_color: "#8a8a8a"
  text_subtitle_weight: 400
  text_subtitle_lh: 1.6
  text_subtitle_max_chars: 180
  text_handle_color: "#505050"
  text_handle_size: "16px"
  text_handle_bottom: "40px"
  icon_color: "#2a2a2a"
  icon_opacity: 0.55
  icon_size: "660px"
  content_padding: "60px 80px 100px"
  text_align: "center"
```

## Validation

The wizard validates the brand step on submit. Reject empty values. Default to the values above if the user types nothing.
