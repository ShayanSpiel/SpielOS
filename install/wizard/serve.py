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

# ─── Helpers ────────────────────────────────────────────────────────────

def write_text_area(rel_path: str, content: str | None) -> list[str]:
    """Write a file from textarea content. Skip if content is empty."""
    if not content or not content.strip():
        return []
    (VAULT / rel_path).write_text(content, encoding="utf-8")
    return [rel_path]


def load_skeleton(name: str) -> str:
    """Load a skeleton file, or return empty string."""
    path = SKELETON_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


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
    (VAULT / "system" / "brand.md").write_text(md, encoding="utf-8")
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
    (VAULT / "system" / "brand.json").write_text(json.dumps(brand_json, indent=2), encoding="utf-8")
    return ["system/brand.md", "system/brand.json"]


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


def write_install_marker() -> list[str]:
    """Write .install-state.json so re-running the wizard can resume / merge."""
    state = {
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "vault": str(VAULT),
        "version": "2.0.0",
    }
    (VAULT / ".install-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return [".install-state.json"]


def run_post_install(source_vault: Path | None = None) -> dict:
    """After /api/finish: install the shim, sync IDE adapters, and report what was installed.

    `source_vault` is the path of the canonical SpielOS repo the wizard copied from.
    It's used to invoke sync_adapters.py, because the copy in the target VAULT
    would compute its own path as VAULT (which is the new install) and bake the
    wrong vault_root into the installed adapters. In production the source and
    target are the same directory, so this matters only in dev / smoke-test mode.
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
        (VAULT / ".spiel-vault").write_text(f"VAULT_DIR={VAULT}\n", encoding="utf-8")
        spielos_cfg = Path.home() / ".config" / "spielos" / "config"
        spielos_cfg.parent.mkdir(parents=True, exist_ok=True)
        spielos_cfg.write_text(f"VAULT_DIR={VAULT}\n", encoding="utf-8")
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
                env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
                    (Path.home() / ".codex", ["agents", "commands"]),
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


VAULT = None
SOURCE_VAULT = None  # the canonical SpielOS repo (for sync_adapters invocation)


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
                # Schedule server shutdown in 3 seconds
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
        "adapters", "skills", "tests", "bin",
        "content", "content/inbox", "content/drafts", "content/ready",
        "content/posted", "content/rejected",
        "archive", "archive/roles", "archive/skills",
        "install", "install/wizard", "install/wizard/skeletons",
    ]
    for sub in must_exist:
        (target / sub).mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        # Roles
        "team/director.md", "team/strategist.md", "team/writer.md",
        "team/editor.md", "team/publisher.md", "team/post.md", "team/README.md",
        # System
        "system/pipeline.md", "system/draft-schema.md", "system/rules.yaml",
        "system/brand.md", "system/brand.json",
        # Strategy skeletons (user will edit via wizard)
        "strategy/audience.md", "strategy/offer.md",
        "strategy/voice.md", "strategy/examples.md",
        # Templates
        "templates/x-post.md", "templates/linkedin-post.md", "templates/blog-post.md",
        # Tools
        "tools/editor.py", "tools/designer.py", "tools/sync_adapters.py",
        "tools/_vault.py",
        "tools/publisher/_common.py", "tools/publisher/buffer.py",
        "tools/publisher/twitter.py", "tools/publisher/linkedin.py",
        "tools/publisher/blog.sh",
        "tools/banner-templates/default.html", "tools/banner-templates/notes.html",
        # Skills
        "skills/format_wizard/SKILL.md",
        "skills/publish_wizard/SKILL.md",
        "skills/voice_match/SKILL.md",
        # Wizard
        "install/wizard/index.html",
        "install/wizard/design-system.css",
        "install/wizard/steps.js",
        "install/wizard/serve.py",
        "install/install.sh",
        "install/uninstall.sh",
        "install/brew/spiel.rb",
        # Archive (read-only references for the IDE adapters + restore later)
        "archive/roles/README.md",
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
    args = parser.parse_args()

    global VAULT
    VAULT = resolve_vault(args.target)
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
