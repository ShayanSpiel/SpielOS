# Brand

The brand identity for your content. Banner rendering is dormant (Designer role is archived), but the tokens stay here so the wizard has a single home for visual identity and the machine-readable mirror is at `system/brand.json`.

The wizard writes both files from your inputs in step 2 (Brand). Keep them in sync by re-running the wizard with `spiel init`.

---

## Required fields

```yaml
brand:
  name: YourBrand
  handle: @your_handle
  primary_bg: #000000
  primary_fg: #ffffff
  accent: #ff6a00
  text_dark: #202020
  text_mid: #5a5959
  tagline: ""
  creator_self: ""
```

## Banner colors

| Token | Purpose | Default |
|---|---|---|
| `primary_bg` | Background | `#000000` |
| `primary_fg` | Title | `#ffffff` |
| `subtitle_color` | Subtitle (Merriweather) | `#8a8a8a` |
| `handle_color` | Handle (JetBrains Mono, bottom) | `#505050` |
| `accent` | Reserved for highlights / interactive | `#ff6a00` |

## Banner styles

- **Title gradient**: `false — solid color (default)`
- Banner template: `default`. Dimensions: 1200x630.
- Fonts: Inter (heading), Merriweather (subtitle), JetBrains Mono (handle).
