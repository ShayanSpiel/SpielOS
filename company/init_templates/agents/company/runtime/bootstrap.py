"""``company init`` — scaffold a self-contained SpielOS harness home.

Creates a vendored copy of the harness spine plus the private state tree in
a target directory (default: cwd), so the resulting repository has zero
runtime dependency on the installed package:

    .agents/company/**     runtime spine + optional Departments
    .spielos/state|data|artifacts/
    .spielos/.env.example  credential contract
    .opencode/**           host adapter (plugin, commands, agents)
    .codex/agents/**       Codex adapter
    opencode.json          host config (generic; no provider keys)
    AGENTS.md              harness operating doc

Template source resolution order:
1. ``SPIELOS_TEMPLATE_DIR`` (a directory containing ``agents/``,
   ``opencode/``, ``codex/``, ``dot-env-example``);
2. the bundled ``company/init_templates/`` package data;
3. the installed ``spielos`` distribution (pipx/uv) when this code runs
   vendored inside a home — refresh reads the newest release from there;
4. a vendored repository checkout this package was imported from.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import package_vendored_root, validate_home_destination


def _spielos_launcher_venv() -> Path | None:
    """Virtualenv backing the ``spielos`` launcher on PATH, if resolvable."""
    import shutil

    exe = shutil.which("spielos")
    if not exe:
        return None
    try:
        with open(exe, encoding="utf-8", errors="replace") as handle:
            first = handle.readline().strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    import shlex

    parts = shlex.split(first[2:])
    if parts and Path(parts[0]).name == "env":
        parts = parts[1:]
        while parts and parts[0].startswith("-"):
            parts = parts[1:]
    if not parts:
        return None
    python = Path(parts[0]).expanduser()
    if not python.exists() or not python.name.startswith("python"):
        return None
    venv = python.resolve().parents[1]
    return None if venv == venv.parent else venv


def _installed_distribution_templates() -> Path | None:
    """init_templates shipped inside the installed ``spielos`` distribution.

    A vendored home has no bundled templates of its own, yet its runtime
    must be able to refresh from the newest release. The installing tool's
    environment (pipx, uv) is not on this interpreter's ``sys.path``, so
    look for it directly: other ``sys.path`` entries first, then the
    ``spielos`` launcher's virtualenv, then conventional install homes.
    """
    import os
    import sys

    here = Path(__file__).resolve()
    bases: list[Path] = []

    # 1. Other sys.path entries (works when templates are merely shadowed).
    for entry in list(sys.path):
        if entry:
            bases.append(Path(entry).expanduser())

    # 2. The virtualenv behind the spielos launcher.
    launcher_venv = _spielos_launcher_venv()
    if launcher_venv is not None:
        bases.append(launcher_venv)

    # 3. Conventional pipx / uv tool locations.
    home = Path.home()
    pipx_home = os.environ.get("PIPX_HOME", "").strip()
    pipx_roots = [Path(pipx_home)] if pipx_home else []
    pipx_roots += [home / ".local" / "pipx",
                   home / "Library" / "Application Support" / "pipx",
                   home / ".local" / "share" / "pipx"]
    for root in pipx_roots:
        bases.append(root / "venvs" / "spielos")
    uv_tools = os.environ.get("UV_TOOL_DIR", "").strip()
    uv_roots = [Path(uv_tools)] if uv_tools else []
    uv_roots.append(home / ".local" / "share" / "uv" / "tools")
    for root in uv_roots:
        bases.append(root / "spielos")

    seen: set[Path] = set()
    for base in bases:
        try:
            base = base.expanduser().resolve()
        except OSError:
            continue
        if base in seen or not base.is_dir():
            continue
        seen.add(base)
        if here.is_relative_to(base):
            continue  # the tree we are running from (e.g. <home>/.agents)
        candidates = [base]
        for pattern in ("lib/python*/site-packages", "Lib/site-packages"):
            candidates.extend(sorted(base.glob(pattern)))
        for site_packages in candidates:
            packaged = site_packages / "company" / "init_templates"
            if ((packaged / "agents").is_dir()
                    and (packaged / "hosts").is_dir()):
                return packaged
    return None


def template_root() -> Path:
    """Template source resolution (see module docstring)."""
    import os

    env_value = os.environ.get("SPIELOS_TEMPLATE_DIR", "").strip()
    if env_value:
        env = Path(env_value).expanduser()
        if env.is_dir():
            return env
        raise FileNotFoundError(f"SPIELOS_TEMPLATE_DIR is not a directory: {env}")
    bundled = Path(__file__).resolve().parents[1] / "init_templates"
    if bundled.is_dir():
        return bundled
    installed = _installed_distribution_templates()
    if installed is not None:
        return installed
    vendored = package_vendored_root()
    if vendored is not None and (vendored / ".agents" / "company").is_dir():
        staged = vendored / ".agents" / "company" / "init_templates"
        if staged.is_dir():
            return staged
    raise FileNotFoundError(
        "No init templates found. Set SPIELOS_TEMPLATE_DIR to a directory "
        "containing agents/, opencode/, codex/, dot-env-example.")


_template_root = template_root  # backward-compatible alias


def _copy_tree(src: Path, dst: Path, overwrite: bool = False,
               skip=None) -> list[str]:
    written: list[str] = []
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(src).as_posix()
        if skip is not None and skip(rel):
            continue
        target = dst / rel
        if target.exists() and not overwrite:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        written.append(str(target))
    return written


def scaffold(target: Path | None = None, *, force: bool = False,
             on_phase=None) -> dict:
    """Materialize a complete harness home. Returns a receipt dict.

    ``on_phase(label)`` is called before each materialization chunk so an
    interactive driver can show progress; it is optional plumbing and
    never changes what gets written.
    """
    root = validate_home_destination(target or Path.cwd())
    templates = template_root()
    written: list[str] = []
    notify = on_phase or (lambda label: None)

    agents_dst = root / ".agents"
    existing_home = (agents_dst / "company" / "runtime").exists()
    if existing_home and not force:
        raise FileExistsError(
            "this folder already has a SpielOS home (.agents/company); "
            "re-run with --force to overwrite")

    preserved_user_prefixes = (
        "company/departments/",
        "company/agents/installed/",
    ) if existing_home else ()

    def preserve_user_layer(rel: str) -> bool:
        return any(rel.startswith(prefix) for prefix in preserved_user_prefixes)

    notify("Vendoring harness spine")
    written += _copy_tree(templates / "agents", root / ".agents",
                          overwrite=force, skip=preserve_user_layer)
    notify("Installing host adapters (OpenCode, Codex)")
    # Host adapters.
    for name in ("opencode", "codex"):
        src = templates / "hosts" / name
        if src.is_dir():
            written += _copy_tree(src, root / ("." + name), overwrite=force)

    # Private state/data/artifact trees (empty on purpose).
    notify("Creating private state tree (.spielos)")
    for rel in (".spielos/state", ".spielos/data", ".spielos/artifacts"):
        (root / rel).mkdir(parents=True, exist_ok=True)

    # Credential contract example.
    notify("Writing credential contract")
    env_example = templates / "dot-env-example"
    if env_example.is_file():
        dest = root / ".spielos" / ".env.example"
        if force or not dest.exists():
            shutil.copy2(env_example, dest)
            written.append(str(dest))

    # Host config: generic, no analytics/provider keys baked in.
    notify("Writing host config (opencode.json)")
    opencode_json = root / "opencode.json"
    if force or not opencode_json.exists():
        opencode_json.write_text(json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "default_agent": "director",
            "plugin": ["./.opencode/plugins/spielos-notifications.ts"],
        }, indent=2) + "\n")
        written.append(str(opencode_json))

    # Harness operating doc for hosts (AGENTS.md), website-agnostic.
    notify("Writing operating doc (AGENTS.md)")
    agents_md = root / "AGENTS.md"
    if force or not agents_md.exists():
        agents_md.write_text(_AGENTS_MD)
        written.append(str(agents_md))

    gitignore = root / ".gitignore"
    ignore_block = _GITIGNORE.strip() + "\n"
    if gitignore.exists():
        current = gitignore.read_text()
        missing = [line for line in ignore_block.splitlines()
                   if line and line not in current]
        if missing:
            gitignore.write_text(current.rstrip("\n") + "\n\n" + "\n".join(missing) + "\n")
            written.append(str(gitignore))
    else:
        gitignore.write_text(ignore_block)
        written.append(str(gitignore))

    return {
        "root": str(root),
        "template_source": str(templates),
        "files_written": len(written),
        "next_steps": [
            "cd " + str(root),
            "opencode",
            "Select the Director agent before chatting (not Build).",
            "Create a clean Department only when its Workflow contract is ready.",
            "Set credentials in .spielos/.env (see .spielos/.env.example).",
        ],
    }


_GITIGNORE = """
# Company runtime: credentials, private inputs, state, generated work
.spielos/.env
.spielos/.env.*
.spielos/data/
.spielos/state/
.spielos/artifacts/
.spielos/*.sqlite
.spielos/*.sqlite-*
.spielos/*.db
.spielos/*.db-*
.agents/*.db
.agents/*.sqlite
**/__pycache__/
*.pyc
*.pid
*.log
node_modules/
"""

_AGENTS_MD = """# Agent operating rules — harness section

This repository runs on the SpielOS company harness: one durable loop
(GOAL -> OBSERVE -> DECIDE -> ACT -> EVALUATE) persisted in SQLite under
`.spielos/state/`. The runtime owns every Goal, approval, run, and evidence
record; Departments supply Agent-owned behavior only.

Authority and full documentation: `.agents/company/README.md`.

Open OpenCode or Codex and select the Director agent before chatting. The host
injects fresh company state automatically; do not begin with a manual status
probe.

## OpenCode commands

| Command | Meaning |
|---|---|
| `/start [request or goal]` | Create, resume, or continue one Goal |
| `/stop [goal]` | Persistently stop automation |
| `/status [goal]` | Compact Company Snapshot or one Goal |
| `/approve <goal>` | Approve exactly one displayed parked action |
| `/help` | Explain the vocabulary and command surface |

## Rules

- Live external actions always park for explicit approval.
- Departments are declarations; Agents execute only claimed WorkOrders.
- Owner, workflow, and strategy Memory must retain its required lineage.
"""
