"""``company init`` — scaffold a self-contained SpielOS harness home.

Creates a vendored copy of the harness spine plus the private state tree in
a target directory (default: cwd), so the resulting repository has zero
runtime dependency on the installed package:

    .agents/company/**     runtime spine + example departments
    .agents/skills/**      skills/company + skills/website namespaces
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
3. a vendored repository checkout this package was imported from.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .paths import package_vendored_root


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
    vendored = package_vendored_root()
    if vendored is not None and (vendored / ".agents" / "company").is_dir():
        staged = vendored / ".agents" / "company" / "init_templates"
        if staged.is_dir():
            return staged
    raise FileNotFoundError(
        "No init templates found. Set SPIELOS_TEMPLATE_DIR to a directory "
        "containing agents/, opencode/, codex/, dot-env-example.")


_template_root = template_root  # backward-compatible alias


def available_departments() -> list[str]:
    """Department ids vendorable with ``init --minimal --department ID``."""
    root = template_root() / "agents" / "company" / "departments"
    if not root.is_dir():
        return []
    return sorted(entry.name for entry in root.iterdir()
                  if entry.is_dir() and not entry.name.startswith(("_", ".")))


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
             minimal: bool = False, departments: list[str] | None = None,
             on_phase=None) -> dict:
    """Materialize a complete harness home. Returns a receipt dict.

    ``minimal=True`` ships the spine with an EMPTY departments/ folder and
    no website skills — a single-department appliance. Pass
    ``departments=["id", ...]`` to also vendor those from the templates.
    ``on_phase(label)`` is called before each materialization chunk so an
    interactive driver can show progress; it is optional plumbing and
    never changes what gets written.
    """
    root = (target or Path.cwd()).resolve()
    templates = template_root()
    written: list[str] = []
    notify = on_phase or (lambda label: None)

    agents_dst = root / ".agents"
    if (agents_dst / "company" / "runtime").exists() and not force:
        raise FileExistsError(
            "this folder already has a SpielOS home (.agents/company); "
            "re-run with --force to overwrite")

    notify("Vendoring harness spine")
    if minimal:
        # Shared cross-department modules are spine, not lego — always kept.
        spine_dept_files = {"company/departments/__init__.py",
                            "company/departments/_evidence.py",
                            "company/departments/campaign_contract.py"}
        written += _copy_tree(templates / "agents", root / ".agents",
                              overwrite=force,
                              skip=lambda rel: (
                                  rel.startswith("company/departments/")
                                  and rel not in spine_dept_files)
                              or rel.startswith("skills/website/"))
        # Keep the departments package importable even without its files.
        dept_pkg = root / ".agents" / "company" / "departments"
        dept_pkg.mkdir(parents=True, exist_ok=True)
        (dept_pkg / "__init__.py").touch()
        written.append(str(dept_pkg / "__init__.py"))
        for dept_id in departments or []:
            src = templates / "agents" / "company" / "departments" / dept_id
            if not src.is_dir():
                raise ValueError(f"template has no department '{dept_id}'")
            written += _copy_tree(src, root / ".agents" / "company"
                                  / "departments" / dept_id, overwrite=force)
    else:
        written += _copy_tree(templates / "agents", root / ".agents",
                              overwrite=force)
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
            "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company status",
            "Make it yours: edit .agents/company/strategy/ (ICP, voice) and departments.",
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
record; Departments supply business behavior only.

Authority and full documentation: `.agents/company/README.md`.

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
- The Director and Department executors never edit repository files;
  `system-improvement` is the only editing agent, bounded by its goal.
- Strategy authority lives in `.agents/company/strategy/`; never restate it.
"""
