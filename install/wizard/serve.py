#!/usr/bin/env python3
"""install/wizard/serve.py — Local setup wizard server.

Self-contained stdlib http.server. No Flask, no FastAPI. Serves the
multi-step HTML form and writes the 8 strategy files + brand tokens +
.env to the target vault on submit.

CLI:
    python3 install/wizard/serve.py --port 7331 --target /path/to/vault
    python3 install/wizard/serve.py --port 7331 --target ~/.spiel

On first hit at `/`, the wizard loads. On `POST /api/finish`, the
wizard writes the files and returns a JSON report of what was written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


# ─── Vault resolution ────────────────────────────────────────────────────

def resolve_vault(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    env = os.environ.get("VAULT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".spiel").resolve()


VAULT = None  # set in main()

# ─── File writers ───────────────────────────────────────────────────────

def yaml_quote(s: str) -> str:
    """Quote a string for YAML if it contains special chars."""
    if not s:
        return '""'
    if re.match(r"^[a-zA-Z0-9_\-./@]+$", s):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_brand(form: dict) -> list[str]:
    """Write system/brand.md and system/brand.json."""
    primary_bg = form.get("primary_bg", "#000000")
    primary_fg = form.get("primary_fg", "#ffffff")
    subtitle_color = form.get("subtitle_color", "#8a8a8a")
    handle_color = form.get("handle_color", "#505050")
    accent = form.get("accent", "#ff6a00")
    title_gradient = bool(form.get("title_gradient", False))

    md = f"""---
title: Brand
type: spec
tags: [brand, design]
status: living
audience: designer
sources: [wizard]
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
---

# Brand

The brand identity. The Designer reads this when picking banner tokens.

## Required fields

```yaml
brand:
  name: {form.get('brand_name', 'SpielOS')}
  handle: {form.get('handle', '@your_handle')}
  primary_bg: {primary_bg}
  primary_fg: {primary_fg}
  subtitle_color: {subtitle_color}
  handle_color: {handle_color}
  accent: {accent}
  text_dark: #202020
  text_mid: #5a5959
  tagline: "{form.get('tagline', '')}"
  creator_self: "{form.get('creator_self', '')}"
```

## Banner colors

| Token | Purpose | Default |
|---|---|---|
| `primary_bg` | Background | `#000000` |
| `primary_fg` | Title (also: handle icon) | `#ffffff` |
| `subtitle_color` | Subtitle (Merriweather) | `#8a8a8a` |
| `handle_color` | Handle (JetBrains Mono, bottom) | `#505050` |
| `accent` | Reserved for highlights / interactive | `#ff6a00` |

## Banner styles

- **Title gradient**: `{"true — silver gradient white→#888" if title_gradient else "false — solid color (default)"}`
- Banner template: `default`. Dimensions: 1200x630.
- Fonts: Inter (heading), Merriweather (subtitle), JetBrains Mono (handle).

## Banners

The `tools/designer.py` banner renderer reads these tokens and injects them into `tools/banner-templates/default.html`. To customize the layout beyond colors, edit the HTML template directly.
"""
    (VAULT / "system" / "brand.md").write_text(md, encoding="utf-8")
    brand_json = {
        "brand": {
            "name": form.get("brand_name", "SpielOS"),
            "handle": form.get("handle", "@your_handle"),
            "primary_bg": primary_bg,
            "primary_fg": primary_fg,
            "subtitle_color": subtitle_color,
            "handle_color": handle_color,
            "accent": accent,
            "tagline": form.get("tagline", ""),
            "creator_self": form.get("creator_self", ""),
        },
        "fonts": {
            "heading": "Inter",
            "subtitle": "Merriweather",
            "mono": "JetBrains Mono",
            "use_google_fonts": True,
        },
        "banner": {
            "template": "default",
            "title_gradient": title_gradient,
            "dimensions": {"width": 1200, "height": 630},
            "render": {"device_scale_factor": 2, "chrome_path": None},
            "tokens": {
                "text_title_color": primary_fg,
                "text_subtitle_color": subtitle_color,
                "text_handle_color": handle_color,
                "text_subtitle_max_chars": 180,
                "bg": primary_bg,
            },
        },
    }
    (VAULT / "system" / "brand.json").write_text(json.dumps(brand_json, indent=2), encoding="utf-8")
    return ["system/brand.md", "system/brand.json"]


def write_icp(form: dict) -> list[str]:
    md = f"""---
title: ICP — {form.get('icp_who', 'target audience')[:60]}
type: concept
tags: [strategy, icp, audience]
status: living
audience: strategist, copywriter
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# ICP — {form.get('icp_who', 'target audience')}

## Demographics

| Attribute | Value |
|---|---|
| Age | {form.get('icp_age', '—')} |
| Role | {form.get('icp_who', '—')} |
| Revenue / stage | {form.get('icp_revenue', '—')} |

## Goal

{form.get('icp_goal', '—')}

## Fear

{form.get('icp_fear', '—')}

## Internal monologue

{form.get('icp_questions', '—')}

## How this ICP buys

When a follower has read ≥3 posts AND clicked bio AND DMed with a specific question → treat as a buying signal.

**The buying signal:** "tell me more" or "how does it work" — not "how much."

**The objection:** "Can I do this myself?" → "You could, but it'll take 3 months and every mistake I already made. Or you can get it in 14 days."

## See also

- [[positioning]] — your one-line market position
- [[offer]] — what you sell to this audience
- [[funnel]] — the path from unaware to buying
"""
    (VAULT / "strategy" / "icp.md").write_text(md, encoding="utf-8")
    return ["strategy/icp.md"]


def write_positioning(form: dict) -> list[str]:
    md = f"""---
title: Positioning
type: concept
tags: [strategy, positioning]
status: living
audience: strategist
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Positioning

**Category:** {form.get('category', '—')}

**One line:** {form.get('positioning', '—')}

**Core insight:** {form.get('core_insight', '—')}

## The transformation

**Before:** Build → stop → think → write → post (rare, inconsistent)

**After:** Build → session captured → content generated → publish (continuous, invisible overhead)

## See also

- [[icp]] — the audience this serves
- [[offer]] — what you sell
- [[funnel]] — the path the ICP walks
"""
    (VAULT / "strategy" / "positioning.md").write_text(md, encoding="utf-8")
    return ["strategy/positioning.md"]


def write_offer(form: dict) -> list[str]:
    md = f"""---
title: Offer — {form.get('offer_name', 'your offer')[:60]}
type: concept
tags: [strategy, offer, conversion]
status: living
audience: strategist
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Offer — {form.get('offer_name', '—')}

**Price:** {form.get('offer_price', '—')}

## The stack

{form.get('offer_stack', '—')}

## The guarantee

{form.get('offer_guarantee', '—')}

## The pitch

> "We [deliver] so you can [outcome] without [sacrifice]."

## See also

- [[positioning]] — the one-liner this offer delivers on
- [[icp]] — the buyer profile
- [[funnel]] — the BOFU routing
"""
    (VAULT / "strategy" / "offer.md").write_text(md, encoding="utf-8")
    return ["strategy/offer.md"]


def write_funnel(form: dict) -> list[str]:
    md = f"""---
title: Funnel
type: concept
tags: [strategy, funnel, routing]
status: living
audience: strategist
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Funnel

The pipeline that walks the ICP from "I don't know this exists" to "I want it."

```
Awareness (TOFU) → Consideration (MOFU) → Conversion (BOFU) → Post-Purchase
```

## Distribution

| Stage | % of content | Offer presence |
|---|---|---|
| Awareness (TOFU) | {form.get('funnel_tofu', 40)}% | None |
| Consideration (MOFU) | {form.get('funnel_mofu', 40)}% | Soft CTA |
| Conversion (BOFU) | {form.get('funnel_bofu', 15)}% | Direct pitch |

## Archetypes

{', '.join(form.get('archetypes', []))}

## The 1-in-5 rule

Of all drafts in a 30-day rolling window, exactly 1/5 may carry an offer reference. Of those, exactly 1/2 are direct pitches.

## See also

- [[icp]] — the audience this funnel walks through
- [[offer]] — the offer this funnel feeds toward
- [[positioning]] — the one-liner
"""
    (VAULT / "strategy" / "funnel.md").write_text(md, encoding="utf-8")
    return ["strategy/funnel.md"]


def write_voice(form: dict) -> list[str]:
    md = f"""---
title: Voice
type: concept
tags: [strategy, voice, writing]
status: living
audience: copywriter
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Voice

How your posts read. The Copywriter matches this register.

## Default voice register

**{form.get('voice_register', 'confessional-teaching')}**

## Always-on style rules

{chr(10).join('- ' + r for r in form.get('voice_rules', []))}

## Banned opener patterns

```
{form.get('banned_openers', '')}
```

## Voice modes

- **Session mode** — peer builder is reading. Casual, lowercase OK, self-deprecating, voice-corpus register.
- **Topic mode** — stranger is scrolling. Professional, confident, stop-the-scroll energy.

## Character limits (hard gates)

- X: ≤ 280 chars
- LinkedIn casual: ≤ 1500 chars
- LinkedIn polished: ≤ 3000 chars
- Blog pillar: ≤ 2500 words

## See also

- [[icp]] — who you're writing for
- [[funnel]] — which stage each post targets
- `corpus.md` — 8 canonical voice examples (read before drafting)
"""
    (VAULT / "strategy" / "voice.md").write_text(md, encoding="utf-8")
    return ["strategy/voice.md"]


def write_methodology(form: dict) -> list[str]:
    md = f"""---
title: Methodology — {form.get('methodology_name', 'Session as Content')}
type: concept
tags: [strategy, methodology, runtime]
status: living
audience: researcher
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Methodology — {form.get('methodology_name', 'Session as Content')}

> Coined by {form.get('brand_name', 'you')}, {datetime.now().strftime("%Y")}.

## What it is

{form.get('methodology_desc', 'Your content methodology. The Researcher uses this to find the source for every /post run.')}

## Source kinds

{chr(10).join('- ' + s for s in form.get('methodology_sources', []))}

## Platforms

{', '.join(form.get('platforms', []))}

## Pipeline

```
{form.get('methodology_name', 'Source')} → Researcher (classify) → Strategist (compile + select)
       → Copywriter (draft) → Designer (banner) → Editor (gates) → Publisher (dispatch) → Analyst (engage)
```
"""
    (VAULT / "strategy" / "methodology.md").write_text(md, encoding="utf-8")
    return ["strategy/methodology.md"]


def write_archetypes(form: dict) -> list[str]:
    """Write strategy/archetypes.md from the wizard's archetype picks.

    The 10 default archetypes have fixed S1–S10 codes. User-added custom
    archetypes get S11+ codes.
    """
    archetype_table = {
        "System Build": ("S1", "Building a system, architecture, or workflow"),
        "Ship": ("S2", "Shipping a feature, product, or release"),
        "Decision": ("S3", "Choosing X over Y, documented trade-offs"),
        "Lesson": ("S4", "Something learned, abstracted into insight"),
        "Failure": ("S5", "Something broke, went wrong, got fixed"),
        "Client Work": ("S6", "Work done for/with someone else"),
        "Research": ("S7", "Learning, reading, analyzing"),
        "Tooling": ("S8", "Building tools, scripts, automations"),
        "Strategy": ("S9", "Planning, positioning, thinking"),
        "Meta": ("S10", "Working on the system itself"),
    }
    selected = form.get("archetypes", [])
    custom = form.get("customArchetypes", [])

    rows = []
    next_code = 11
    for name in selected:
        if name in archetype_table:
            code, desc = archetype_table[name]
            rows.append(f"| {code} | {name} | {desc} |")
        elif name in custom:
            code = f"S{next_code}"
            next_code += 1
            rows.append(f"| {code} | {name} | Custom archetype |")

    table = "\n".join(rows) if rows else "| (none selected) | | |"

    md = f"""---
title: Session Archetypes
type: concept
tags: [strategy, archetypes, classification]
status: living
audience: researcher, strategist
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Session Archetypes

The 10 default archetypes + your custom archetypes. The Researcher uses this to classify sessions. **Banned in public posts** (`system/prompts/leak-guard.md`).

| # | Archetype | Description |
|---|---|---|
{table}

## How the Researcher classifies

For each session log, the Researcher:
1. Reads the body sections (Patterns, Decisions, What we did, Shipped, Numbers, Lesson).
2. Matches against archetype keyword indexes in `system/rules.yaml §strategy.archetypes`.
3. Picks the highest-scoring archetype.
4. Defaults to S10 (Meta) if the session is about the system itself.

## Custom archetypes

{("Your custom archetypes: " + ", ".join(custom) + ".") if custom else "No custom archetypes."}

## See also

- [[funnel]] — funnel stage routing per archetype
- [[voice]] — voice register per archetype
"""
    (VAULT / "strategy" / "archetypes.md").write_text(md, encoding="utf-8")
    return ["strategy/archetypes.md"]


def write_corpus(form: dict) -> list[str]:
    """Write a starter corpus with one example per the chosen voice register."""
    register = form.get("voice_register", "confessional-teaching")
    md = f"""---
title: Voice Corpus — Starter
type: concept
tags: [voice, reference, corpus]
status: starter
audience: copywriter
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
sources: [wizard]
---

# Voice Corpus — Starter

This page collects canonical examples of your voice. The Copywriter reads this before drafting.

> **Starter state.** The wizard wrote this on install. Add 3-5 of your own real posts as examples. Until you do, the Copywriter will write in the closest-matching register to "{register}".

## Register: {register}

### How to use this corpus

Before drafting, the Copywriter picks the closest example and matches the *voice register* (tone, rhythm, opening pattern) — not the structure.

## Add your own

Drop a `## <label>` section per post:

```markdown
## 1. <post name>

**Hook (2 lines):**
> <first 2 lines from the post>

**Close (1-2 lines):**
> <last 1-2 lines>

**Signature moves:**
- <pattern 1>
- <pattern 2>
```
"""
    (VAULT / "strategy" / "corpus.md").write_text(md, encoding="utf-8")
    return ["strategy/corpus.md"]


def write_env(form: dict) -> list[str]:
    """Write .env with the API tokens."""
    lines = [f"VAULT_DIR={VAULT}", ""]
    if form.get("buffer_token"):
        lines.append(f"BUFFER_ACCESS_TOKEN={form['buffer_token']}")
    if form.get("buffer_channels"):
        lines.append(f"BUFFER_CHANNEL_IDS={','.join(form['buffer_channels'])}")
    if form.get("x_api_key"):
        lines.append(f"X_API_KEY={form['x_api_key']}")
    if form.get("x_api_secret"):
        lines.append(f"X_API_SECRET={form['x_api_secret']}")
    if form.get("x_access_token"):
        lines.append(f"X_ACCESS_TOKEN={form['x_access_token']}")
    if form.get("x_access_secret"):
        lines.append(f"X_ACCESS_SECRET={form['x_access_secret']}")
    if form.get("linkedin_access_token"):
        lines.append(f"LINKEDIN_ACCESS_TOKEN={form['linkedin_access_token']}")
    if form.get("linkedin_person_urn"):
        lines.append(f"LINKEDIN_PERSON_URN={form['linkedin_person_urn']}")
    if form.get("blog_repo"):
        lines.append(f"BLOG_REPO={form['blog_repo']}")
    if form.get("blog_token"):
        lines.append(f"BLOG_TOKEN={form['blog_token']}")
    if not lines[-1]:
        lines.pop()
    (VAULT / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [".env"]


def write_rules_update(form: dict) -> list[str]:
    """Update system/rules.yaml with the banned_openers + custom archetypes from the wizard."""
    rules_path = VAULT / "system" / "rules.yaml"
    if not rules_path.exists():
        return []
    try:
        import yaml
        text = rules_path.read_text(encoding="utf-8")
        rules = yaml.safe_load(text) or {}
    except Exception:
        return []

    # Parse banned_openers from the form (one per line)
    banned_raw = form.get("banned_openers", "")
    if banned_raw:
        patterns = [p.strip() for p in banned_raw.splitlines() if p.strip()]
        rules.setdefault("banned_openers", [])
        for p in patterns:
            if p not in rules["banned_openers"]:
                rules["banned_openers"].append(p)

    # Add custom archetypes as new archetype keys (S11+)
    custom_archetypes = form.get("customArchetypes", [])
    if custom_archetypes:
        archetypes = rules.setdefault("strategy", {}).setdefault("archetypes", {})
        for name in custom_archetypes:
            key = f"S11_{name.lower().replace(' ', '_').replace('-', '_')}"
            if key not in archetypes:
                # Default keyword: the lowercased name itself (catches obvious matches)
                archetypes[key] = [name.lower(), name.lower().replace(" ", "")]

    rules_path.write_text(yaml.safe_dump(rules, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return ["system/rules.yaml"]


def write_install_marker() -> list[str]:
    """Write a .install-state.json so re-running the wizard can resume / merge."""
    state = {
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "vault": str(VAULT),
        "version": "1.0.0",
    }
    (VAULT / ".install-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return [".install-state.json"]


def run_post_install() -> dict:
    """After /api/finish: install the shim, sync IDE adapters, and report what was installed.

    This is the bridge between "wizard finished" and "user can /post from any IDE".
    The user doesn't have to run a single command after the wizard.
    """
    import shutil
    import subprocess

    result = {
        "shim_installed": None,
        "shim_path": None,
        "shim_already_present": False,
        "adapters_generated": 0,
        "adapters_installed": 0,
        "adapters_targets": [],
        "errors": [],
    }

    # 1. Install the shim to ~/.local/bin/spiel
    shim_path = Path.home() / ".local" / "bin" / "spiel"
    vault_shim = VAULT / "bin" / "spiel"
    if vault_shim.exists():
        try:
            shim_path.parent.mkdir(parents=True, exist_ok=True)
            # Remove existing (symlink, file, etc.) so we don't hit IsADirectoryError or FileExistsError
            if shim_path.is_symlink() or shim_path.exists():
                shim_path.unlink()
            shutil.copy(vault_shim, shim_path)
            shim_path.chmod(0o755)
            result["shim_installed"] = str(shim_path)
            result["shim_path"] = str(shim_path)
        except Exception as e:
            result["errors"].append(f"shim install: {e}")
    else:
        result["shim_already_present"] = shim_path.exists()

    # 2. Create ~/.spiel symlink for shim resolution (if needed)
    home_symlink = Path.home() / ".spiel"
    try:
        if home_symlink.is_symlink():
            home_symlink.unlink()
        if not home_symlink.exists() and VAULT.resolve() != home_symlink.resolve():
            home_symlink.symlink_to(VAULT)
    except Exception as e:
        result["errors"].append(f"home symlink: {e}")

    # 3. Generate adapters
    sync_script = VAULT / "tools" / "sync_adapters.py"
    if sync_script.exists():
        try:
            r = subprocess.run(
                [sys.executable, str(sync_script)],
                capture_output=True, text=True,
                cwd=str(VAULT),
                timeout=30,
            )
            if r.returncode == 0:
                # Count files
                for sub in ("adapters/opencode/agents", "adapters/claude/agents",
                            "adapters/cursor/commands"):
                    p = VAULT / sub
                    if p.exists():
                        result["adapters_generated"] += sum(1 for _ in p.glob("*.md"))
            else:
                result["errors"].append(f"sync generate: {r.stderr}")
        except Exception as e:
            result["errors"].append(f"sync generate: {e}")

    # 4. Install adapters to ~/.config/opencode (live IDE)
    if sync_script.exists():
        try:
            r = subprocess.run(
                [sys.executable, str(sync_script), "--install"],
                capture_output=True, text=True,
                cwd=str(VAULT),
                timeout=30,
            )
            if r.returncode == 0:
                # Count installed files
                oc = Path.home() / ".config" / "opencode"
                if oc.exists():
                    for sub in ("agents", "skill"):
                        d = oc / sub
                        if d.exists():
                            result["adapters_installed"] += sum(1 for _ in d.iterdir()
                                                                  if _.name not in (".", ".."))
                    result["adapters_targets"].append(str(oc))
            else:
                result["errors"].append(f"sync install: {r.stderr}")
        except Exception as e:
            result["errors"].append(f"sync install: {e}")

    return result


def fetch_buffer_channels(token: str) -> list[dict]:
    """Fetch Buffer channels for the wizard's channel picker."""
    query = """
    query { account { organizations { id name channels { id service name } } } }
    """
    payload = json.dumps({"query": query, "variables": {}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.buffer.com",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")[:300] if hasattr(e, 'read') else ""
        raise RuntimeError(f"Buffer API HTTP {e.code}: {err}") from e
    except Exception as e:
        raise RuntimeError(f"Buffer API error: {e}") from e
    out = []
    for org in ((data.get("data") or {}).get("account") or {}).get("organizations", []) or []:
        for ch in org.get("channels", []) or []:
            out.append({"id": ch.get("id"), "service": ch.get("service"), "name": ch.get("name")})
    return out


# ─── HTTP handler ────────────────────────────────────────────────────────

WIZARD_DIR = Path(__file__).resolve().parent


class WizardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[wizard] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        try:
            data = path.read_bytes()
        except OSError:
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path or "/"
        if path == "/" or path == "/index.html":
            return self._send_file(WIZARD_DIR / "index.html", "text/html; charset=utf-8")
        if path == "/design-system.css":
            return self._send_file(WIZARD_DIR / "design-system.css", "text/css; charset=utf-8")
        if path == "/steps.js":
            return self._send_file(WIZARD_DIR / "steps.js", "application/javascript; charset=utf-8")
        if path == "/api/config":
            return self._send_json(200, {
                "target": str(VAULT),
                "existing": {"summary": {}},
            })
        if path == "/api/health":
            return self._send_json(200, {"ok": True, "vault": str(VAULT)})
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body_raw = self.rfile.read(length) if length else b""
            data = json.loads(body_raw) if body_raw else {}
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})

        if path == "/api/buffer-channels":
            token = (data.get("token") or "").strip()
            if not token:
                return self._send_json(400, {"error": "token required"})
            try:
                channels = fetch_buffer_channels(token)
            except Exception as e:
                return self._send_json(500, {"error": str(e)})
            return self._send_json(200, {"channels": channels})

        if path == "/api/finish":
            try:
                written: list[str] = []
                written += write_brand(data)
                written += write_icp(data)
                written += write_positioning(data)
                written += write_offer(data)
                written += write_funnel(data)
                written += write_voice(data)
                written += write_archetypes(data)
                written += write_methodology(data)
                written += write_corpus(data)
                written += write_rules_update(data)
                written += write_env(data)
                written += write_install_marker()
                # Auto-install: shim + IDE adapters
                install_result = run_post_install()
                # Schedule server shutdown in 3 seconds (so the JS can show the success)
                import threading
                threading.Timer(3.0, lambda: os._exit(0)).start()
                return self._send_json(200, {
                    "ok": True,
                    "vault": str(VAULT),
                    "written": written,
                    "install": install_result,
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                return self._send_json(500, {"error": str(e)})

        if path == "/api/shutdown":
            # Allow manual shutdown (used by the JS in some flows)
            import threading
            def _do_shutdown():
                self.server.shutdown()
            threading.Timer(0.5, _do_shutdown).start()
            return self._send_json(200, {"ok": True, "message": "shutting down"})

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ─── Entrypoint ─────────────────────────────────────────────────────────

def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception as e:
        sys.stderr.write(f"[wizard] could not open browser: {e}\n")


def bootstrap_vault(target: Path, source: Path | None = None) -> None:
    """Copy the canonical source files into the target vault.

    This is the bridge between "user ran install.sh" and "the wizard
    has a complete vault to write into". The wizard's `target` directory
    might be empty (fresh install) or have old data (re-install).

    The strategy: copy any of the 7 deterministic tool files + the
    8 role files + the 4 system files + bin/spiel that are missing.
    Don't touch user data (content/, .env, strategy/).
    """
    import shutil

    # If target is the source itself (e.g. local dev), no copy needed
    if source and source.resolve() == target.resolve():
        return

    # Determine the source. Default: the repo this serve.py lives in.
    # serve.py is at <repo>/install/wizard/serve.py, so source = <repo>.
    if source is None:
        source = WIZARD_DIR.parent.parent  # install/wizard → install → repo root

    # Files/dirs that must exist in the vault
    must_exist = [
        "team", "system", "system/prompts", "strategy", "templates", "templates/registry",
        "tools", "tools/publisher", "assets", "assets/banners", "assets/icons",
        "adapters", "skills", "tests", "bin", "logs",
        "content", "content/sessions", "content/queue", "content/posted", "content/rejected",
    ]
    for sub in must_exist:
        target_dir = target / sub
        target_dir.mkdir(parents=True, exist_ok=True)

    # Files to copy (if missing in target)
    files_to_copy = [
        # Role prompts
        "team/md.md", "team/strategist.md", "team/researcher.md", "team/copywriter.md",
        "team/editor.md", "team/designer.md", "team/publisher.md", "team/analyst.md",
        "team/README.md",
        # System
        "system/state-machine.md", "system/brief-schema.md", "system/pipeline.md",
        "system/brand.json", "system/gates.md", "system/rules.yaml",
        "system/prompts/identity.md", "system/prompts/compiler.md",
        "system/prompts/leak-guard.md", "system/prompts/wizards.md",
        # Templates
        "templates/x-post.md", "templates/linkedin-post.md", "templates/blog-post.md",
        "templates/session-log.md", "templates/types.md",
        "templates/registry/viral-templates.yaml",
        # Tools
        "tools/editor.py", "tools/designer.py", "tools/researcher.py", "tools/analyst.py",
        "tools/sync_adapters.py",
        "tools/publisher/_common.py", "tools/publisher/buffer.py",
        "tools/publisher/twitter.py", "tools/publisher/linkedin.py",
        "tools/publisher/blog.sh",
        # Bin
        "bin/spiel",
        # Tests
        "tests/smoke.py", "tests/test_state_machine.py", "tests/conftest.py",
        # Root
        "AGENTS.md", "README.md", "package.json", ".gitignore",
    ]

    for rel in files_to_copy:
        src = source / rel
        dst = target / rel
        if not src.exists():
            continue
        if dst.exists():
            continue  # don't overwrite user-edited files
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            # Preserve executable bit for sh + bin scripts
            if rel.endswith(".sh") or rel == "bin/spiel":
                dst.chmod(0o755)
        except Exception as e:
            sys.stderr.write(f"[wizard] could not copy {rel}: {e}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="SpielOS setup wizard")
    parser.add_argument("--port", type=int, default=7331, help="Port to serve on (default 7331)")
    parser.add_argument("--target", help="Target vault directory (default: VAULT_DIR or ~/.spiel)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    parser.add_argument("--source", help="Source repo to copy from (default: this serve.py's repo)")
    args = parser.parse_args()

    global VAULT
    VAULT = resolve_vault(args.target)
    VAULT.mkdir(parents=True, exist_ok=True)
    # Make sure key subdirs exist + copy the source files into the vault
    bootstrap_vault(VAULT, source=Path(args.source) if args.source else None)

    port = args.port
    if not is_port_free(port):
        sys.stderr.write(f"[wizard] port {port} busy, trying {port + 1}\n")
        port += 1

    server = ThreadingHTTPServer((args.host, port), WizardHandler)
    url = f"http://{args.host}:{port}/"
    print(f"")
    print(f"  SpielOS Setup Wizard")
    print(f"  ────────────────────")
    print(f"  Target:  {VAULT}")
    print(f"  URL:     {url}")
    print(f"")
    print(f"  Press Ctrl+C to quit.")
    print(f"")

    if not args.no_open:
        import threading
        threading.Timer(0.5, open_browser, args=[url]).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[wizard] shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
