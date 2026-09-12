"""``company init`` — scaffold a self-contained SpielOS harness home.

Creates a vendored copy of the harness spine plus the private state tree in
a target directory (default: cwd), so the resulting repository has zero
runtime dependency on the installed package:

    .agents/company/**     runtime spine + optional Departments
    .spielos/state|data|artifacts/
    .spielos/.env.example  credential contract
    .opencode/**           host adapter (plugin, commands, agents)
    .codex/agents/**        Codex adapter
    .claude/**             Claude Code adapter (agents, commands, hooks)
    CLAUDE.md              one-line @AGENTS.md bridge for Claude Code
    opencode.json          host config (generic; no provider keys)
    AGENTS.md              harness operating doc

Template source resolution order:
1. ``SPIELOS_TEMPLATE_DIR`` (a directory containing ``agents/``,
   ``hosts/``, ``dot-env-example``);
2. the bundled ``company/init_templates/`` package data;
3. the installed ``spielos`` distribution (pipx/uv) when this code runs
   vendored inside a home — refresh reads the newest release from there;
4. a vendored repository checkout this package was imported from.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config import VERSION
from .paths import package_vendored_root, validate_home_destination

# Owner content that `spielos update` must never touch. Everything the
# release ships is vendored: it is tracked in .spielos/vendored.json,
# refreshed on update, and pruned when a newer release stops shipping it.
# Only proven-vendored paths may ever refresh or prune: manifest-tracked
# paths in a manifest home, and — in a home with no manifest yet (created
# before the manifest era) — exactly the paths the current release itself
# ships. Every other path, in the spine's user layers or anywhere in the
# host trees (.codex/, .opencode/, .claude/), is owner content and is
# preserved; the manifest an update writes resolves precise pruning on the
# next update.

VENDORED_MANIFEST = Path(".spielos") / "vendored.json"


def _template_files(src: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(src.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts \
                and path.suffix != ".pyc":
            files.append(path.relative_to(src).as_posix())
    return files


def _load_manifest(root: Path) -> dict[str, list[str]] | None:
    """Vendored file list written by the previous init/update, if any."""
    manifest = root / VENDORED_MANIFEST
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text())
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, dict):
            return None
        return {str(tree): [str(item) for item in items or []]
                for tree, items in files.items() if isinstance(items, list)}
    except (json.JSONDecodeError, OSError):
        return None


def _write_manifest(root: Path, entries: dict[str, list[str]]) -> None:
    path = root / VENDORED_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": 1, "spielos": VERSION, "files": entries}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _canonical_opencode_json() -> dict:
    # Plugins under .opencode/plugins/ are auto-discovered by the host; the
    # loader rejects file-path entries in the "plugin"/"plugins" keys.
    return {"$schema": "https://opencode.ai/config.json",
            "default_agent": "director"}


# The Claude Code adapter wires its hooks through an append-only merge
# into the owner's .claude/settings.json; the release fragment names the
# hook scripts this merge owns (and nothing else).
CLAUDE_HOOK_SCRIPTS = ("spielos-context.py", "spielos-attention.py")


def _claude_hook_script(command: str) -> str | None:
    """The SpielOS hook script a command string runs, if any.

    Only commands that run this home's shipped scripts under
    ``.claude/hooks/`` are ours — an owner hook that merely mentions the
    same filename elsewhere (a different tree, a different host) is owner
    content and is never touched.
    """
    if ".claude/hooks/" not in command:
        return None
    for name in CLAUDE_HOOK_SCRIPTS:
        if name in command:
            return name
    return None


def _claude_skip(rel: str) -> bool:
    """The Claude template's CLAUDE.md does not ship inside `.claude/`.

    It ships at the home root next to AGENTS.md, so its one-line
    `@AGENTS.md` import resolves in the same folder.
    """
    return rel == "CLAUDE.md"


def _merge_claude_settings(root: Path) -> list[str]:
    """Append-only merge of the Claude Code hook wiring.

    The release ships the hook commands in
    ``.claude/settings-fragment.json``; this merge lands them in the
    owner's ``.claude/settings.json`` without ever disturbing owner
    content: every other key (permissions, env, model, and any hooks the
    owner or other tools registered) is preserved byte-for-byte in
    meaning, each SpielOS hook is added exactly once (a release that
    changes a command replaces only its own earlier wiring), an
    unparseable settings file is left untouched, and
    ``.claude/settings.local.json`` is never written.
    """
    fragment_path = root / ".claude" / "settings-fragment.json"
    try:
        fragment = json.loads(fragment_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    wanted = fragment.get("hooks") if isinstance(fragment, dict) else None
    if not isinstance(wanted, dict):
        return []

    settings_path = root / ".claude" / "settings.json"
    if settings_path.is_file():
        try:
            config = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []  # owner content we cannot parse is never rewritten
        if not isinstance(config, dict):
            return []
    else:
        config = {}

    hooks = config.get("hooks")
    if hooks is None:
        hooks = {}
        config["hooks"] = hooks
    if not isinstance(hooks, dict):
        return []  # owner-shaped hooks key: leave it alone

    changed = False
    for event, groups in wanted.items():
        existing = hooks.get(event)
        if existing is None:
            existing = []
            hooks[event] = existing
        elif not isinstance(existing, list):
            # An owner-shaped event value is owner content: leave the
            # whole merge alone rather than replace it.
            return []
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            target = None
            for candidate in existing:
                if (isinstance(candidate, dict)
                        and candidate.get("matcher", "") == (group.get("matcher") or "")):
                    target = candidate
                    break
            if target is not None and not isinstance(target.get("hooks"), list):
                # The owner's group at this matcher is shaped differently:
                # keep it untouched and add ours as its own group.
                target = None
            if target is None:
                target = ({"matcher": group["matcher"], "hooks": []}
                          if group.get("matcher") else {"hooks": []})
                existing.append(target)
            bucket = target.get("hooks")
            if not isinstance(bucket, list):
                continue  # unreachable by construction; never touch it
            for entry in entries:
                command = (entry.get("command")
                           if isinstance(entry, dict) else None)
                if not isinstance(command, str) or not command:
                    continue
                script = _claude_hook_script(command)
                if script is None:
                    continue
                # Drop only this release's own stale wiring for the script
                # (a release may change the command); never touch any
                # other hook entry the owner or another tool registered.
                kept = [item for item in bucket
                        if not (isinstance(item, dict)
                                and _claude_hook_script(
                                    str(item.get("command") or "")) == script)]
                if len(kept) != len(bucket):
                    bucket[:] = kept
                    changed = True
                if not any(isinstance(item, dict)
                           and item.get("command") == command
                           for item in bucket):
                    bucket.append(dict(entry))
                    changed = True
    if not changed and settings_path.is_file():
        return []
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(config, indent=2) + "\n")
    return [str(settings_path)]


def _merge_opencode_json(path: Path) -> list[str]:
    """Targeted fix-up of owner configuration; never clobber other keys."""
    try:
        config = json.loads(path.read_text())
        if not isinstance(config, dict):
            config = {}
    except (json.JSONDecodeError, OSError):
        config = {}
    changed: list[str] = []
    if "default_agent" not in config:
        config["default_agent"] = "director"
        changed.append("default_agent")
    for key in ("plugin", "plugins"):
        entries = config.get(key)
        if not isinstance(entries, list):
            continue
        kept = [item for item in entries
                if not (isinstance(item, str)
                        and item.strip().replace("./", "", 1)
                        .startswith(".opencode/"))]
        if kept != entries:
            if kept:
                config[key] = kept
            else:
                config.pop(key, None)
            changed.append(key)
    if changed:
        path.write_text(json.dumps(config, indent=2) + "\n")
        return [f"{path} ({', '.join(sorted(set(changed)))})"]
    return []


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
        "No init templates found for this home. Update through the installed "
        "`spielos` command (pipx upgrade spielos, then `spielos update --dir "
        "<home>`), or run from a source checkout, or set SPIELOS_TEMPLATE_DIR "
        "to a directory containing agents/, hosts/, dot-env-example.")


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


def _prune_stale(src: Path, dst: Path, skip=None) -> list[str]:
    """Delete vendored files that the current templates no longer ship.

    An ``update`` must leave the vendored spine exactly like a fresh init:
    files left behind by an older release (for example a removed runtime
    module) are deleted. Bytecode is always cleaned; the preserved owner
    layers are never touched.
    """
    removed: list[str] = []
    keep: set[str] = set()
    for path in src.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts \
                and path.suffix != ".pyc":
            rel = path.relative_to(src).as_posix()
            if skip is None or not skip(rel):
                keep.add(rel)
    if not dst.is_dir():
        return removed
    for path in sorted(dst.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(dst).as_posix()
        if rel in keep:
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            path.unlink(missing_ok=True)
            removed.append(str(path))
            continue
        if skip is not None and skip(rel):
            continue
        if "node_modules" in path.parts:
            continue
        path.unlink(missing_ok=True)
        removed.append(str(path))
    for path in sorted((p for p in dst.rglob("*") if p.is_dir()),
                       reverse=True):
        if "node_modules" in path.parts:
            continue
        try:
            path.rmdir()
        except OSError:
            pass
    return removed


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

    manifest = _load_manifest(root) if existing_home else None

    def vendored_entries() -> dict[str, list[str]]:
        entries = {"agents": _template_files(templates / "agents")}
        for name in ("opencode", "codex", "claude"):
            source = templates / "hosts" / name
            files = _template_files(source) if source.is_dir() else []
            if name == "claude":
                # CLAUDE.md ships at the home root next to AGENTS.md (the
                # one-line @AGENTS.md bridge must resolve in the same
                # folder); the .claude tree carries the rest of the adapter.
                files = [item for item in files if item != "CLAUDE.md"]
            entries[name] = files
        return entries

    def layer_guard(tree: str):
        """True for owner-created files (never vendored, never pruned).

        Manifest knowledge narrows what update may touch below the
        shipped set; it never widens it. In a manifest home only
        manifest-tracked paths are proven vendored — they refresh and,
        when a newer release stops shipping them, prune. In a pre-manifest
        home only the paths the current release itself ships are provably
        vendored. Every other path is owner content and is preserved, in
        the spine's user layers and the host trees alike.
        """
        tracked = set(manifest.get(tree, ())) if manifest is not None else None
        # Rel paths the current release itself ships in this tree — the
        # only paths a home with no manifest can prove vendored.
        shipped = (set(vendored_entries().get(tree, ()))
                   if tracked is None else None)
        vendored = tracked if tracked is not None else shipped

        def is_user(rel: str) -> bool:
            return rel not in vendored

        return is_user

    notify("Vendoring harness spine")
    if existing_home and force:
        # An update removes stale vendored files so the spine matches a
        # fresh init exactly; owner-created files in the user layers are
        # skipped, as is anything the current release still ships.
        removed = _prune_stale(templates / "agents", root / ".agents",
                                skip=layer_guard("agents"))
        written.extend(f"removed {item}" for item in removed)
    written += _copy_tree(templates / "agents", root / ".agents",
                          overwrite=force)
    notify("Installing host adapters (OpenCode, Codex, Claude Code)")
    # Host adapters. The Claude tree skips CLAUDE.md here: that file ships
    # at the home root (below) so its @AGENTS.md import resolves.
    for name in ("opencode", "codex", "claude"):
        src = templates / "hosts" / name
        if not src.is_dir():
            continue
        if existing_home and force:
            written.extend(f"removed {item}" for item in _prune_stale(
                src, root / ("." + name), skip=layer_guard(name)))
        written += _copy_tree(src, root / ("." + name), overwrite=force,
                              skip=(_claude_skip if name == "claude" else None))

    # Claude Code reads CLAUDE.md at the project root; the one-line bridge
    # to AGENTS.md makes all three hosts share one operating doc. It is
    # owner-editable like AGENTS.md: written only when absent, never
    # rewritten on update (owners may add Claude-specific notes below it).
    claude_bridge = templates / "hosts" / "claude" / "CLAUDE.md"
    if claude_bridge.is_file() and not (root / "CLAUDE.md").exists():
        shutil.copy2(claude_bridge, root / "CLAUDE.md")
        written.append(str(root / "CLAUDE.md"))

    # Claude Code hook wiring: append-only merge into the owner's
    # .claude/settings.json (owner permissions and keys untouched, each
    # hook added exactly once, settings.local.json never written).
    if (templates / "hosts" / "claude").is_dir():
        written += _merge_claude_settings(root)

    # Private state/data/artifact trees (empty on purpose).
    notify("Creating private state tree (.spielos)")
    for rel in (".spielos/state", ".spielos/data", ".spielos/artifacts"):
        (root / rel).mkdir(parents=True, exist_ok=True)

    # Record exactly what this release vendored, so the next update can
    # tell owner-created files from stale vendored residue.
    notify("Recording vendored manifest")
    _write_manifest(root, vendored_entries())
    written.append(str(root / VENDORED_MANIFEST))

    # Credential contract example.
    notify("Writing credential contract")
    env_example = templates / "dot-env-example"
    if env_example.is_file():
        dest = root / ".spielos" / ".env.example"
        if force or not dest.exists():
            shutil.copy2(env_example, dest)
            written.append(str(dest))

    # Host config: generic, no analytics/provider keys baked in. Existing
    # owner configuration is fixed up in place, never overwritten.
    notify("Writing host config (opencode.json)")
    opencode_json = root / "opencode.json"
    if opencode_json.exists():
        written += _merge_opencode_json(opencode_json)
    else:
        opencode_json.write_text(
            json.dumps(_canonical_opencode_json(), indent=2) + "\n")
        written.append(str(opencode_json))

    # Harness operating doc for hosts (AGENTS.md), website-agnostic.
    notify("Writing operating doc (AGENTS.md)")
    agents_md = root / "AGENTS.md"
    if agents_md.exists():
        current = agents_md.read_text()
        if _LAYOUT_MARKER not in current:
            agents_md.write_text(
                current.rstrip("\n") + "\n\n" + _LAYOUT_CONTRACT_SECTION)
            written.append(str(agents_md))
    else:
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
            "opencode (run /agents, select the Director agent), "
            "codex (talk to the Director agent), or claude "
            "(run claude --agent director)",
            "The Director already sees your company state; just talk to it.",
            "Create a clean Department only when its Workflow contract is ready.",
            "Set credentials in .spielos/.env (see .spielos/.env.example).",
            "Audit layout any time: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents "
            "python3 -B -m company layout",
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

Open OpenCode (run `/agents`, select the Director agent), Codex (talk to
the Director agent), or Claude Code (run `claude --agent director`) and
just talk to it — it already sees your company state. Claude Code reads
this file through the one-line `CLAUDE.md` bridge. The host injects fresh
company state automatically; do not begin with a
manual status probe. If a request carries no SpielOS projection, host
injection failed: run the read-only `company status` once, tell the owner
that injection is broken, and never guess company state by reading files.

## Host commands

The same slash commands ship for OpenCode, Codex, and Claude Code:

| Command | Meaning |
|---|---|
| `/start [request or goal]` | Create, resume, or continue one Goal |
| `/stop [goal]` | Persistently stop automation |
| `/status [goal]` | Compact Company Snapshot or one Goal |
| `/approve <goal>` | Approve exactly one displayed parked action |
| `/help` | Explain the vocabulary and command surface |

## Company layout contract

<!-- spielos-layout-contract v1 -->

Company content lives in exactly these layers under `.agents/company/`:

| Layer | Contents |
|---|---|
| `departments/<id>/department.py` | one Department declaration per folder |
| `skills/<id>/SKILL.md` | one reusable Skill per folder |
| `capabilities/<id>/` | capability packages |
| `connections/` | connection registry and client modules |
| `strategy/` | canonical strategy documents |
| `agents/installed/` | installed worker Agents |

Never invent folders or files outside these layers (no `_lib/`,
`_strategy/`, `declarations.py`, or a duplicate Director skill — the
Director is the host agent prompt, not a Skill). Department-owned subfolders
inside their package are fine. Audit drift with `company layout` and
resolve every violation before adding new content.

## Rules

- Live external actions always park for explicit approval.
- Departments are declarations; Agents execute only claimed WorkOrders.
- Owner, workflow, and strategy Memory must retain its required lineage.
- Structural changes (Departments, Workflows, or the vendored spine) go
  through one bounded system-improvement Goal with exact allowed files and
  acceptance evidence — never improvise them directly.
"""

_LAYOUT_MARKER = "<!-- spielos-layout-contract v1 -->"

_LAYOUT_CONTRACT_SECTION = """## Company layout contract

<!-- spielos-layout-contract v1 -->

Company content lives in exactly these layers under `.agents/company/`:

| Layer | Contents |
|---|---|
| `departments/<id>/department.py` | one Department declaration per folder |
| `skills/<id>/SKILL.md` | one reusable Skill per folder |
| `capabilities/<id>/` | capability packages |
| `connections/` | connection registry and client modules |
| `strategy/` | canonical strategy documents |
| `agents/installed/` | installed worker Agents |

Never invent folders or files outside these layers (no `_lib/`,
`_strategy/`, `declarations.py`, or a duplicate Director skill — the
Director is the host agent prompt, not a Skill). Department-owned subfolders
inside their package are fine. Audit drift with `company layout` and
resolve every violation before adding new content.
"""
