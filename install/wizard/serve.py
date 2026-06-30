#!/usr/bin/env python3
"""install/wizard/serve.py — Local setup wizard server (lean 6-step).

Self-contained stdlib http.server. No Flask, no FastAPI. Serves the
6-step HTML form and writes the 4 strategy files + brand tokens + .env
to the target vault on submit.

CLI:
    python3 install/wizard/serve.py --port 7331 --target /path/to/vault

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
import threading
import urllib.error
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
    return Path.cwd().resolve()


VAULT = None  # set in main()
SKELETON_DIR = Path(__file__).resolve().parent / "skeletons"
FINISH_LOCK = threading.Lock()

EDITABLE_FILES = {
    "strategy/audience.md",
    "strategy/offer.md",
    "strategy/voice.md",
    "strategy/examples.md",
    "system/brand.md",
    "system/brand.json",
    "system/rules.yaml",
    ".env",
    "team/strategist.md",
    "team/writer.md",
    "team/editor.md",
    "team/publisher.md",
    "team/post.md",
}

# ─── Helpers ────────────────────────────────────────────────────────────

def atomic_write_text(path: Path, text: str) -> None:
    """Write text with a same-directory temp file + atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_text_area(rel_path: str, content: str | None) -> list[str]:
    """Write a file from textarea content. Skip if content is empty."""
    if not content or not content.strip():
        return []
    atomic_write_text(VAULT / rel_path, content)
    return [rel_path]


def load_skeleton(name: str) -> str:
    """Load a skeleton file, or return empty string."""
    decoded = urllib.parse.unquote(name)
    if decoded != Path(decoded).name or "/" in decoded or "\\" in decoded:
        return ""
    path = (SKELETON_DIR / decoded).resolve()
    if not str(path).startswith(str(SKELETON_DIR.resolve())):
        return ""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def safe_edit_path(rel_path: str) -> Path:
    rel = rel_path.strip().lstrip("/")
    if rel not in EDITABLE_FILES:
        raise ValueError(f"file is not editable from dashboard: {rel_path}")
    path = (VAULT / rel).resolve()
    if not str(path).startswith(str(VAULT.resolve())):
        raise ValueError("path escapes vault")
    return path


def read_editable_file(rel_path: str) -> dict:
    """Read a file that's in EDITABLE_FILES, returning its content and metadata."""
    path = safe_edit_path(rel_path)
    return {
        "path": rel_path,
        "exists": path.exists(),
        "content": path.read_text(encoding="utf-8") if path.exists() else "",
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else None,
    }


def read_env_vars() -> dict[str, str]:
    """Parse .env into a dict of key-value pairs. Returns {} if file missing."""
    env_path = VAULT / ".env"
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'\"")
        if key:
            result[key] = val
    return result


def write_env_var(key: str, value: str) -> None:
    """Add or update a single env var in .env, preserving comments and order."""
    env_path = VAULT / ".env"
    existing = read_env_vars()
    existing[key] = value
    lines: list[str] = []
    if env_path.exists():
        seen_key = False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                lines.append(line)
                continue
            k = stripped.partition("=")[0].strip()
            if k == key:
                lines.append(f"{key}={value}")
                seen_key = True
            else:
                lines.append(line)
        if not seen_key:
            lines.append(f"{key}={value}")
    else:
        lines.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(env_path, "\n".join(lines) + "\n")


def remove_env_var(key: str) -> None:
    """Remove a single env var from .env."""
    env_path = VAULT / ".env"
    if not env_path.exists():
        return
    lines = [
        line for line in env_path.read_text(encoding="utf-8").splitlines()
        if not (line.strip() and "=" in line.strip() and line.strip().partition("=")[0].strip() == key)
    ]
    atomic_write_text(env_path, "\n".join(lines) + "\n")


def fetch_buffer_profiles(token: str) -> list[dict]:
    """Fetch the user's Buffer profiles (channels) using their access token.

    Uses the legacy REST endpoint at api.bufferapp.com which still works with
    a Bearer token. Returns a list of {"id", "service", "name"} dicts.
    """
    if not token or not token.strip():
        raise ValueError("Buffer token is empty")
    req = urllib.request.Request(
        "https://api.bufferapp.com/1/profiles.json?access_token=" + urllib.parse.quote(token.strip()),
        headers={"Accept": "application/json", "User-Agent": "SpielOS-Installer/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    profiles: list[dict] = []
    for p in data if isinstance(data, list) else []:
        profiles.append({
            "id": p.get("id") or "",
            "service": (p.get("service") or "").strip().title() or "Channel",
            "name": (p.get("formatted_username") or p.get("service_username") or p.get("default_text") or p.get("id") or "Channel").strip(),
        })
    return [p for p in profiles if p["id"]]


def list_runs(limit: int = 20) -> list[dict]:
    runs_dir = VAULT / "content" / "runs"
    if not runs_dir.is_dir():
        return []
    runs = []
    for run in sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True)[:limit]:
        events_path = run / "events.jsonl"
        events = []
        if events_path.is_file():
            for line in events_path.read_text(encoding="utf-8").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        runs.append({
            "run_id": run.name,
            "events": events,
            "event_count": len(events),
            "updated_at": datetime.fromtimestamp(run.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return runs


def runtime_snapshot() -> dict:
    state_path = VAULT / "content" / ".state.json"
    current_path = VAULT / "content" / "current.md"
    state = None
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"error": "invalid content/.state.json"}

    guard = {"ok": True, "issues": []}
    try:
        sys.path.insert(0, str(VAULT / "tools"))
        from guard import check as guard_check  # type: ignore
        guard = guard_check(VAULT)
    except Exception as e:
        guard = {"ok": False, "issues": [{"code": "guard_error", "message": str(e), "severity": "warning"}]}

    def count_files(d: Path) -> list[str]:
        if not d.is_dir():
            return []
        return sorted(str(p.relative_to(VAULT)) for p in d.iterdir()
                       if p.is_file() and p.name != ".gitkeep" and not p.name.startswith("."))

    drafts_files = count_files(VAULT / "content" / "drafts")
    ready_files = count_files(VAULT / "content" / "ready")
    posted_files = count_files(VAULT / "content" / "posted")
    rejected_files = count_files(VAULT / "content" / "rejected")

    state_drafts = state.get("drafts", []) if isinstance(state, dict) else []
    state_ready = state.get("ready", []) if isinstance(state, dict) else []
    merged_drafts = sorted(set(drafts_files) | set(f for f in state_drafts if (VAULT / f).is_file()))
    merged_ready = sorted(set(ready_files) | set(f for f in state_ready if (VAULT / f).is_file()))

    return {
        "state": {
            **(state if isinstance(state, dict) else {}),
            "drafts": merged_drafts,
            "ready": merged_ready,
        } if state else None,
        "current": current_path.read_text(encoding="utf-8") if current_path.is_file() else "",
        "runs": list_runs(),
        "guard": guard,
        "counts": {
            "drafts": len(merged_drafts),
            "ready": len(merged_ready),
            "posted": len(posted_files),
            "rejected": len(rejected_files),
            "errors": sum(1 for i in (guard.get("issues") or []) if i.get("severity") == "error"),
            "warnings": sum(1 for i in (guard.get("issues") or []) if i.get("severity") == "warning"),
        },
        "drafts_files": merged_drafts,
        "ready_files": merged_ready,
        "posted_files": posted_files,
        "rejected_files": rejected_files,
    }


def load_brand_config() -> dict:
    """Read the brand fields from system/brand.json or system/brand.md.

    Returns a dict of UI-friendly keys (primary_bg, primary_fg, accent, etc.)
    that the dashboard can bind to its color pickers.
    """
    defaults = {
        "brand_name": "YourBrand",
        "handle": "@your_handle",
        "role": "Founder, builder",
        "tagline": "",
        "primary_bg": "#000000",
        "primary_fg": "#ffffff",
        "subtitle_color": "#8a8a8a",
        "handle_color": "#505050",
        "accent": "#5f8b4c",
        "title_gradient": False,
    }
    brand_json = VAULT / "system" / "brand.json"
    if brand_json.is_file():
        try:
            data = json.loads(brand_json.read_text(encoding="utf-8"))
            brand = data.get("brand", {}) if isinstance(data.get("brand"), dict) else {}
            colors = data.get("colors", {}) if isinstance(data.get("colors"), dict) else {}
            banner = data.get("banner", {}) if isinstance(data.get("banner"), dict) else {}
            tokens = banner.get("tokens", {}) if isinstance(banner.get("tokens"), dict) else {}
            return {
                **defaults,
                "brand_name": data.get("name") or brand.get("name") or defaults["brand_name"],
                "handle": data.get("handle") or brand.get("handle") or defaults["handle"],
                "role": data.get("role") or brand.get("creator_self") or defaults["role"],
                "tagline": data.get("tagline") or brand.get("tagline") or defaults["tagline"],
                "primary_bg": colors.get("background") or brand.get("primary_bg") or tokens.get("bg") or defaults["primary_bg"],
                "primary_fg": colors.get("title") or brand.get("primary_fg") or tokens.get("text_title_color") or defaults["primary_fg"],
                "subtitle_color": colors.get("subtitle") or brand.get("subtitle_color") or tokens.get("text_subtitle_color") or defaults["subtitle_color"],
                "handle_color": colors.get("handle") or brand.get("handle_color") or tokens.get("text_handle_color") or defaults["handle_color"],
                "accent": colors.get("accent") or brand.get("accent") or defaults["accent"],
                "title_gradient": bool(banner.get("title_gradient", defaults["title_gradient"])),
            }
        except (json.JSONDecodeError, OSError):
            pass
    brand_md = VAULT / "system" / "brand.md"
    if brand_md.is_file():
        try:
            text = brand_md.read_text(encoding="utf-8")
            for line in text.splitlines():
                m = re.match(r"\s*-\s*\*\*(.+?)\*\*:\s*(.+?)\s*$", line)
                if not m:
                    continue
                key, value = m.group(1).strip().lower(), m.group(2).strip()
                if key == "name":
                    defaults["brand_name"] = value
                elif key == "handle":
                    defaults["handle"] = value
                elif key == "tagline":
                    defaults["tagline"] = value
                elif key == "background":
                    defaults["primary_bg"] = value
                elif key == "title":
                    defaults["primary_fg"] = value
                elif key == "subtitle":
                    defaults["subtitle_color"] = value
                elif key == "handle color":
                    defaults["handle_color"] = value
                elif key == "accent":
                    defaults["accent"] = value
        except OSError:
            pass
    return defaults


def save_brand_config(payload: dict) -> None:
    """Persist dashboard edits back to system/brand.json + system/brand.md."""
    brand_json = VAULT / "system" / "brand.json"
    data = {}
    if brand_json.is_file():
        try:
            data = json.loads(brand_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data["name"] = payload.get("brand_name", data.get("name", "YourBrand"))
    data["handle"] = payload.get("handle", data.get("handle", "@your_handle"))
    data["role"] = payload.get("role", data.get("role", "Founder, builder"))
    data["tagline"] = payload.get("tagline", data.get("tagline", ""))
    data["colors"] = {
        "background": payload.get("primary_bg", data.get("colors", {}).get("background", "#000000")),
        "title": payload.get("primary_fg", data.get("colors", {}).get("title", "#ffffff")),
        "subtitle": payload.get("subtitle_color", data.get("colors", {}).get("subtitle", "#8a8a8a")),
        "handle": payload.get("handle_color", data.get("colors", {}).get("handle", "#505050")),
        "accent": payload.get("accent", data.get("colors", {}).get("accent", "#5f8b4c")),
    }
    data["brand"] = {
        "name": data["name"],
        "handle": data["handle"],
        "primary_bg": data["colors"]["background"],
        "primary_fg": data["colors"]["title"],
        "subtitle_color": data["colors"]["subtitle"],
        "handle_color": data["colors"]["handle"],
        "accent": data["colors"]["accent"],
        "tagline": data["tagline"],
        "creator_self": data["role"],
    }
    data.setdefault("banner", {})["title_gradient"] = bool(payload.get("title_gradient", data.get("banner", {}).get("title_gradient", False)))
    brand_json.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(brand_json, json.dumps(data, indent=2) + "\n")


def trigger_post_run(payload: dict) -> dict:
    """Run a /post in the vault. Returns ok + run_id or an error."""
    source = (payload.get("source") or "").strip()
    cmd = ["bash", str(VAULT / "bin" / "spiel"), "post", "--mode", "topic"]
    if source:
        cmd.append(source)
    try:
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(VAULT))
        if result.returncode == 0:
            return {"ok": True, "stdout": result.stdout[-500:]}
        return {"ok": False, "error": result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"}
    except FileNotFoundError:
        return {"ok": False, "error": "spiel binary not found. Run `spiel init` first."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Post run timed out (>60s)"}


def write_brand(form: dict) -> list[str]:
    """Write system/brand.md and system/brand.json from the wizard form."""
    primary_bg = form.get("primary_bg", "#000000")
    primary_fg = form.get("primary_fg", "#ffffff")
    subtitle_color = form.get("subtitle_color", "#8a8a8a")
    handle_color = form.get("handle_color", "#505050")
    accent = form.get("accent", "#ff6a00")
    title_gradient = bool(form.get("title_gradient", False))

    md = f"""# Brand

The brand identity for your content. Banner rendering is dormant (Designer role is archived), but the tokens stay here so the wizard has a single home for visual identity and the machine-readable mirror is at `system/brand.json`.

The wizard writes both files from your inputs in step 2 (Brand). Keep them in sync by re-running the wizard with `spiel init`.

---

## Required fields

```yaml
brand:
  name: {form.get('brand_name', 'YourBrand')}
  handle: {form.get('handle', '@your_handle')}
  primary_bg: {primary_bg}
  primary_fg: {primary_fg}
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
| `primary_fg` | Title | `#ffffff` |
| `subtitle_color` | Subtitle (Merriweather) | `#8a8a8a` |
| `handle_color` | Handle (JetBrains Mono, bottom) | `#505050` |
| `accent` | Reserved for highlights / interactive | `#ff6a00` |

## Banner styles

- **Title gradient**: `{"true — silver gradient white→#888" if title_gradient else "false — solid color (default)"}`
- Banner template: `default`. Dimensions: 1200x630.
- Fonts: Inter (heading), Merriweather (subtitle), JetBrains Mono (handle).
"""
    atomic_write_text(VAULT / "system" / "brand.md", md)
    brand_json = {
        "brand": {
            "name": form.get("brand_name", "YourBrand"),
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
    atomic_write_text(VAULT / "system" / "brand.json", json.dumps(brand_json, indent=2) + "\n")
    return ["system/brand.md", "system/brand.json"]


def write_env(form: dict) -> list[str]:
    """Write .env with the API tokens, preserving existing vars not in the form."""

    env_path = VAULT / ".env"
    existing_lines: list[str] = []
    existing_vars: dict[str, int] = {}
    if env_path.exists():
        for i, line in enumerate(env_path.read_text(encoding="utf-8").splitlines()):
            existing_lines.append(line)
            stripped = line.strip()
            if stripped and "=" in stripped and not stripped.startswith("#"):
                k = stripped.partition("=")[0].strip()
                existing_vars[k] = i

    form_to_env = {
        "buffer_token": "BUFFER_ACCESS_TOKEN",
        "x_api_key": "X_API_KEY",
        "x_api_secret": "X_API_SECRET",
        "x_access_token": "X_ACCESS_TOKEN",
        "x_access_secret": "X_ACCESS_SECRET",
        "linkedin_access_token": "LINKEDIN_ACCESS_TOKEN",
        "linkedin_person_urn": "LINKEDIN_PERSON_URN",
        "wp_url": "WP_URL",
        "wp_username": "WP_USERNAME",
        "wp_app_password": "WP_APP_PASSWORD",
        "devto_api_key": "DEVTO_API_KEY",
        "hashnode_api_key": "HASHNODE_API_KEY",
        "hashnode_publication_id": "HASHNODE_PUBLICATION_ID",
        "custom_blog_api_url": "CUSTOM_BLOG_API_URL",
        "custom_blog_api_method": "CUSTOM_BLOG_API_METHOD",
        "custom_blog_api_auth_header": "CUSTOM_BLOG_API_AUTH_HEADER",
        "custom_blog_api_body_template": "CUSTOM_BLOG_API_BODY_TEMPLATE",
        "custom_blog_mcp_server": "CUSTOM_BLOG_MCP_SERVER",
        "blog_repo": "BLOG_REPO",
        "blog_token": "BLOG_TOKEN",
    }

    overrides: dict[str, str] = {env_key: form[form_key] for form_key, env_key in form_to_env.items() if form.get(form_key)}
    buffer_channels = form.get("buffer_channels")
    if isinstance(buffer_channels, list):
        selected = [str(v).strip() for v in buffer_channels if str(v).strip()]
        if selected:
            overrides["BUFFER_CHANNEL_IDS"] = ",".join(selected)
    elif isinstance(buffer_channels, str) and buffer_channels.strip():
        overrides["BUFFER_CHANNEL_IDS"] = buffer_channels.strip()
    overrides["VAULT_DIR"] = str(VAULT)

    for env_key, value in overrides.items():
        if env_key in existing_vars:
            idx = existing_vars[env_key]
            existing_lines[idx] = f"{env_key}={value}"
        else:
            existing_lines.append(f"{env_key}={value}")
            existing_vars[env_key] = len(existing_lines) - 1

    if not existing_lines:
        existing_lines.append("")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(env_path, "\n".join(existing_lines) + "\n")
    return [".env"]


def write_install_marker() -> list[str]:
    """Write .install-state.json so re-running the wizard can resume / merge."""
    state = {
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "vault": str(VAULT),
        "version": "2.0.0",
    }
    atomic_write_text(VAULT / ".install-state.json", json.dumps(state, indent=2) + "\n")
    return [".install-state.json"]


def run_post_install(source_vault: Path | None = None) -> dict:
    """After /api/finish: install the shim, sync IDE adapters, and report what was installed.

    `source_vault` is the path of the canonical SpielOS repo the wizard copied from.
    It's used to invoke sync_adapters.py, because the copy in the target VAULT
    would compute its own path as VAULT (which is the new install) and bake the
    wrong vault_root into the installed adapters. In production the source and
    target are the same directory, so this matters only in dev / smoke-test mode.

    Safety: refuses to install adapters if VAULT looks like a temp directory,
    or if VAULT is not a valid SpielOS vault. This prevents the smoke test
    (and accidental production runs against /tmp paths) from contaminating
    the user's live IDE configs.
    """
    import shutil
    import subprocess

    # Safety: refuse to install adapters if VAULT is in /tmp or not a valid vault
    vault_str = str(VAULT)
    if vault_str.startswith("/tmp/") or vault_str.startswith("/private/var/folders/") or vault_str.startswith("/var/folders/"):
        return {
            "shim_installed": None,
            "shim_path": None,
            "shim_already_present": False,
            "adapters_generated": 0,
            "adapters_installed": 0,
            "adapters_targets": [],
            "errors": [f"refused: VAULT ({VAULT}) looks like a temp directory; not installing to live IDEs"],
        }
    if not (VAULT / "team" / "strategist.md").is_file():
        return {
            "shim_installed": None,
            "shim_path": None,
            "shim_already_present": False,
            "adapters_generated": 0,
            "adapters_installed": 0,
            "adapters_targets": [],
            "errors": [f"refused: VAULT ({VAULT}) is not a valid SpielOS vault (no team/strategist.md)"],
        }

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

    # 2. Write vault pointer file + global config
    try:
        atomic_write_text(VAULT / ".spiel-vault", f"VAULT_DIR={VAULT}\n")
        # Only write global config + .env if VAULT is not a temp directory
        vault_str = str(VAULT)
        if not (vault_str.startswith("/tmp/") or vault_str.startswith("/private/var/folders/") or vault_str.startswith("/var/folders/")):
            spielos_cfg = Path.home() / ".config" / "spielos" / "config"
            spielos_cfg.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(spielos_cfg, f"VAULT_DIR={VAULT}\n")
            env_file = VAULT / ".env"
            if env_file.exists():
                text = env_file.read_text(encoding="utf-8")
                lines = text.splitlines()
                found = False
                for i, line in enumerate(lines):
                    if line.startswith("VAULT_DIR="):
                        lines[i] = f"VAULT_DIR={VAULT}"
                        found = True
                        break
                if found:
                    atomic_write_text(env_file, "\n".join(lines) + "\n")
        else:
            result["errors"].append(f"vault pointer: skipped global config write (VAULT is a temp dir: {VAULT})")
    except Exception as e:
        result["errors"].append(f"vault pointer: {e}")

    # 3+4. Generate + install adapters. Use the SOURCE sync_adapters.py so the
    # installed adapter files have the correct vault_root baked in. In
    # production install (source == target), this is a no-op distinction.
    # VAULT_ROOT env var tells sync_adapters which absolute path to bake into
    # the templated adapter files — must be the install target, not the source.
    sync_script = None
    if source_vault and (source_vault / "tools" / "sync_adapters.py").exists():
        sync_script = source_vault / "tools" / "sync_adapters.py"
    elif (VAULT / "tools" / "sync_adapters.py").exists():
        sync_script = VAULT / "tools" / "sync_adapters.py"

    adapter_env = os.environ.copy()
    adapter_env["VAULT_ROOT"] = str(VAULT)

    if sync_script:
        try:
            r = subprocess.run(
                [sys.executable, str(sync_script)],
                capture_output=True, text=True,
                env=adapter_env,
                timeout=30,
            )
            if r.returncode == 0:
                for sub in ("adapters/opencode/agents", "adapters/claude/agents",
                            "adapters/cursor/commands"):
                    p = VAULT / sub
                    if p.exists():
                        result["adapters_generated"] += sum(1 for _ in p.glob("*.md"))
            else:
                result["errors"].append(f"sync generate: {r.stderr}")
        except Exception as e:
            result["errors"].append(f"sync generate: {e}")

        try:
            r = subprocess.run(
                [sys.executable, str(sync_script), "--install"],
                capture_output=True, text=True,
                env=adapter_env,
                timeout=30,
            )
            if r.returncode == 0:
                ide_dirs = [
                    (Path.home() / ".config" / "opencode", ["agents", "skill", "commands"]),
                    (Path.home() / ".cursor" / "skills", []),
                    (Path.home() / ".claude", ["agents", "skills"]),
                    (Path.home() / ".codex", ["agents"]),
                ]
                for ide_dir, subs in ide_dirs:
                    if not ide_dir.exists():
                        continue
                    if subs:
                        for sub in subs:
                            d = ide_dir / sub
                            if d.exists():
                                n = sum(1 for f in d.iterdir() if f.name not in (".", ".."))
                                result["adapters_installed"] += n
                    else:
                        n = sum(1 for f in ide_dir.iterdir() if f.name not in (".", ".."))
                        result["adapters_installed"] += n
                    result["adapters_targets"].append(str(ide_dir))
            else:
                result["errors"].append(f"sync install: {r.stderr}")
        except Exception as e:
            result["errors"].append(f"sync install: {e}")

    # 5. Migration: delete stale codex `commands/post.toml` from older installs.
    # Earlier versions of sync_adapters wrote a markdown-with-YAML-frontmatter
    # file at ~/.codex/commands/post.toml, which is not valid TOML and breaks
    # Codex's adapter loader. Codex now uses agents/ only (no commands/), so
    # this file is fully stale. Remove it and the empty commands/ dir if both
    # are present. Silent on success; reported in `errors` if it fails.
    try:
        stale_post = Path.home() / ".codex" / "commands" / "post.toml"
        if stale_post.exists():
            stale_post.unlink()
        stale_cmds_dir = Path.home() / ".codex" / "commands"
        if stale_cmds_dir.exists() and not any(stale_cmds_dir.iterdir()):
            stale_cmds_dir.rmdir()
    except Exception as e:
        result["errors"].append(f"codex migration: {e}")

    return result


# ─── HTTP handler ────────────────────────────────────────────────────────

WIZARD_DIR = Path(__file__).resolve().parent


VAULT = None
SOURCE_VAULT = None  # the canonical SpielOS repo (for sync_adapters invocation)
EXIT_ON_FINISH = False


def _detect_source_vault() -> Path:
    """Best-effort detection of the canonical repo this wizard was launched from.

    In production, the installer downloaded the repo and the wizard's target
    IS the source (same directory). In dev / smoke-test mode the wizard is
    launched against a temp target while the source remains the dev repo.
    """
    if SOURCE_VAULT is not None:
        return SOURCE_VAULT
    # Wizard lives at <repo>/install/wizard/serve.py
    return WIZARD_DIR.parent.parent


def _set_source_vault(path: Path | None) -> None:
    global SOURCE_VAULT
    if path:
        SOURCE_VAULT = path.expanduser().resolve()
    else:
        SOURCE_VAULT = _detect_source_vault()


class WizardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[wizard] {self.address_string()} - {fmt % args}\n")

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        try:
            parsed = urllib.parse.urlparse(origin)
        except Exception:
            return False
        if parsed.scheme not in ("http", "https"):
            return False
        return parsed.netloc == host and parsed.hostname in ("localhost", "127.0.0.1", "::1")

    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        return origin if origin and self._origin_allowed() else None

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        cors_origin = self._cors_origin()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Vary", "Origin")
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
        if path == "/dashboard" or path == "/dashboard.html":
            return self._send_file(WIZARD_DIR / "dashboard.html", "text/html; charset=utf-8")
        if path == "/design-system.css":
            return self._send_file(WIZARD_DIR / "design-system.css", "text/css; charset=utf-8")
        if path == "/steps.js":
            return self._send_file(WIZARD_DIR / "steps.js", "application/javascript; charset=utf-8")
        if path == "/icons.js":
            return self._send_file(WIZARD_DIR / "icons.js", "application/javascript; charset=utf-8")
        if path == "/api/config":
            return self._send_json(200, {
                "target": str(VAULT),
                "existing": {"summary": {}},
                "installed": (VAULT / ".install-state.json").is_file(),
            })
        if path == "/api/dashboard":
            return self._send_json(200, {
                "target": str(VAULT),
                "installed": (VAULT / ".install-state.json").is_file(),
                "editable": sorted(EDITABLE_FILES),
                "runtime": runtime_snapshot(),
                "config": load_brand_config(),
            })
        if path == "/api/runtime":
            return self._send_json(200, runtime_snapshot())
        if path == "/api/file":
            query = urllib.parse.parse_qs(parsed.query)
            rel_path = (query.get("path") or [""])[0]
            try:
                return self._send_json(200, read_editable_file(rel_path))
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
        if path == "/api/env":
            try:
                return self._send_json(200, {"vars": read_env_vars()})
            except Exception as e:
                return self._send_json(500, {"error": str(e)})
        if path == "/api/skeletons":
            skeletons = sorted(f.name for f in SKELETON_DIR.iterdir() if f.is_file())
            return self._send_json(200, {"skeletons": skeletons})
        if path.startswith("/api/skeleton/"):
            name = path[len("/api/skeleton/"):]
            content = load_skeleton(name)
            if not content:
                return self._send_json(404, {"error": f"skeleton not found: {name}"})
            return self._send_json(200, {"name": name, "content": content})
        if path == "/api/health":
            return self._send_json(200, {"ok": True, "vault": str(VAULT)})
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        if not self._origin_allowed():
            return self._send_json(403, {"ok": False, "error": "cross-origin POST rejected"})
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body_raw = self.rfile.read(length) if length else b""
            data = json.loads(body_raw) if body_raw else {}
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})

        if path == "/api/config":
            try:
                save_brand_config(data)
                return self._send_json(200, {"ok": True, "config": load_brand_config()})
            except Exception as e:
                return self._send_json(500, {"ok": False, "error": str(e)})

        if path == "/api/post":
            try:
                result = trigger_post_run(data)
                return self._send_json(200 if result.get("ok") else 500, result)
            except Exception as e:
                return self._send_json(500, {"ok": False, "error": str(e)})

        if path == "/api/buffer/channels":
            token = (data.get("token") or "").strip()
            if not token:
                return self._send_json(400, {"ok": False, "error": "token required"})
            try:
                channels = fetch_buffer_profiles(token)
                return self._send_json(200, {"ok": True, "channels": channels})
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:200]
                return self._send_json(e.code, {"ok": False, "error": f"Buffer returned {e.code}: {body or e.reason}"})
            except urllib.error.URLError as e:
                return self._send_json(502, {"ok": False, "error": f"Could not reach Buffer: {e.reason}"})
            except Exception as e:
                return self._send_json(500, {"ok": False, "error": f"Buffer lookup failed: {e}"})

        if path == "/api/env/set":
            key = (data.get("key") or "").strip()
            value = (data.get("value") or "").strip()
            if not key:
                return self._send_json(400, {"error": "key required"})
            try:
                write_env_var(key, value)
                return self._send_json(200, {"ok": True, "key": key})
            except Exception as e:
                return self._send_json(500, {"error": str(e)})

        if path == "/api/env/unset":
            key = (data.get("key") or "").strip()
            if not key:
                return self._send_json(400, {"error": "key required"})
            try:
                remove_env_var(key)
                return self._send_json(200, {"ok": True, "key": key})
            except Exception as e:
                return self._send_json(500, {"error": str(e)})

        if path == "/api/file":
            rel_path = data.get("path") or ""
            content = data.get("content")
            if not isinstance(content, str):
                return self._send_json(400, {"error": "content must be a string"})
            try:
                file_path = safe_edit_path(rel_path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(file_path, content)
                return self._send_json(200, {"ok": True, "path": rel_path, "bytes": len(content.encode("utf-8"))})
            except Exception as e:
                return self._send_json(400, {"error": str(e)})

        if path == "/api/finish":
            if not FINISH_LOCK.acquire(blocking=False):
                return self._send_json(409, {"ok": False, "error": "finish already in progress"})
            try:
                written: list[str] = []
                # Brand (always)
                written += write_brand(data)
                # 4 strategy textareas
                written += write_text_area("strategy/audience.md", data.get("audience_content"))
                written += write_text_area("strategy/offer.md", data.get("offer_content"))
                written += write_text_area("strategy/voice.md", data.get("voice_content"))
                written += write_text_area("strategy/examples.md", data.get("examples_content"))
                # .env
                written += write_env(data)
                # Install marker
                written += write_install_marker()
                # Auto-install: shim + IDE adapters
                install_result = run_post_install(source_vault=SOURCE_VAULT)
                if EXIT_ON_FINISH:
                    # Installer mode waits for .install-state.json and should continue.
                    # Dashboard mode stays alive so runtime logs remain visible.
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
            finally:
                FINISH_LOCK.release()

        if path == "/api/shutdown":
            def _do_shutdown():
                self.server.shutdown()
            threading.Timer(0.5, _do_shutdown).start()
            return self._send_json(200, {"ok": True, "message": "shutting down"})

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        cors_origin = self._cors_origin()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Vary", "Origin")
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
    """Copy canonical source files into the target vault on first install.

    Bridge between "user ran install.sh" and "wizard has a complete vault
    to write into". Does not overwrite user data (strategy/, content/, .env,
    system/brand.*, team/).
    """
    import shutil

    if source and source.resolve() == target.resolve():
        return

    if source is None:
        source = WIZARD_DIR.parent.parent  # install/wizard → install → repo root

    must_exist = [
        "team", "system", "strategy", "templates",
        "tools", "tools/publisher", "assets", "assets/icons",
        "adapters", "tests", "bin",
        "content", "content/sessions", "content/drafts", "content/ready",
        "content/posted", "content/rejected",
        "content/runs",
        "archive", "archive/roles", "archive/skills",
        "install", "install/wizard", "install/wizard/skeletons",
    ]
    for sub in must_exist:
        (target / sub).mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        # Roles
        "team/strategist.md", "team/writer.md",
        "team/editor.md", "team/publisher.md", "team/post.md", "team/README.md",
        # System
        "system/pipeline.md", "system/draft-schema.md", "system/run-state.md", "system/session-schema.md", "system/rules.yaml",
        "system/brand.md", "system/brand.json",
        # Strategy skeletons (user will edit via wizard)
        "strategy/audience.md", "strategy/offer.md",
        "strategy/voice.md", "strategy/examples.md",
        # Templates
        "templates/x-post.md", "templates/linkedin-post.md", "templates/blog-post.md",
        # Tools (full set — must be present for `spiel` shim and the Codex hook to work)
        "tools/editor.py", "tools/designer.py", "tools/sync_adapters.py",
        "tools/post.py", "tools/advance.py", "tools/capture-session.py", "tools/doctor.py",
        "tools/codex_hook.py", "tools/next.py",
        "tools/guard.py", "tools/hook_log.py",
        "tools/_vault.py",
        "tools/publisher/_common.py", "tools/publisher/buffer.py",
        "tools/publisher/twitter.py", "tools/publisher/linkedin.py",
        "tools/publisher/blog.sh",
        "tools/banner-templates/default.html", "tools/banner-templates/notes.html",
        # Wizard
        "install/wizard/index.html",
        "install/wizard/design-system.css",
        "install/wizard/steps.js",
        "install/wizard/icons.js",
        "install/wizard/serve.py",
        "install/install.sh",
        "install/uninstall.sh",
        "install/brew/spiel.rb",
        # Codex plugin (mirrored to the plugin cache by `spiel sync` / `--install`)
        "plugins/spielos/.codex-plugin/plugin.json",
        "plugins/spielos/hooks.json",
        "plugins/spielos/scripts/post-hook.sh",
        "plugins/spielos/assets/icon.png",
        "plugins/spielos/assets/logo.png",
        "plugins/spielos/assets/logo-dark.png",
        # Marketplace (Codex)
        ".agents/plugins/marketplace.json",
        # Tests
        "tests/smoke.py",
        # Root
        "AGENTS.md", "README.md", "package.json", ".gitignore",
    ]

    for rel in files_to_copy:
        src = source / rel
        dst = target / rel
        if not src.exists():
            continue
        if dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if rel.endswith(".sh") or rel == "bin/spiel":
                dst.chmod(0o755)
        except Exception as e:
            sys.stderr.write(f"[wizard] could not copy {rel}: {e}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="SpielOS setup wizard")
    parser.add_argument("--port", type=int, default=7331, help="Port to serve on (default 7331)")
    parser.add_argument("--target", help="Target vault directory (default: VAULT_DIR or cwd)")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open browser")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    parser.add_argument("--source", help="Source repo to copy from (default: this serve.py's repo)")
    parser.add_argument("--exit-on-finish", action="store_true", help="Exit after /api/finish for curl installer mode")
    args = parser.parse_args()

    global VAULT, EXIT_ON_FINISH
    VAULT = resolve_vault(args.target)
    EXIT_ON_FINISH = bool(args.exit_on_finish)
    VAULT.mkdir(parents=True, exist_ok=True)
    source = Path(args.source) if args.source else None
    bootstrap_vault(VAULT, source=source)
    _set_source_vault(source)

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
        threading.Timer(0.5, open_browser, args=[url]).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[wizard] shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
