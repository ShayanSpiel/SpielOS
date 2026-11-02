"""``company init`` — scaffold a self-contained SpielOS harness home.

Creates a vendored copy of the harness spine plus the private state tree in
a target directory (default: cwd), so the resulting repository has zero
runtime dependency on the installed package:

    company/**             editable owner context and workflow definitions
    .spielos/runtime/company/** pinned runtime spine
    .agents/company         runtime compatibility alias
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
import shlex
import sys
from pathlib import Path

from .config import VERSION
from ..platform import hook_command,hook_arguments
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
CLAUDE_HOOK_SCRIPTS = ("spielos-context.py", "spielos-attention.py", "spielos-observe.py")


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


def _merge_owned_hooks(root: Path, host: str, desired: dict, destination: Path) -> list[str]:
    """Replace/retire only this home's known hooks; preserve owner wiring."""
    if destination.exists():
        try:config=json.loads(destination.read_text())
        except (ValueError,OSError):return []
        if not isinstance(config,dict):return []
    else:config={}
    hooks=config.get('hooks',{})
    if not isinstance(hooks,dict):return []
    wanted=desired.get('hooks',{})
    if not isinstance(wanted,dict):return []
    original=json.dumps(config,sort_keys=True)
    def owned(command):
        if not isinstance(command,str):return False
        for name in CLAUDE_HOOK_SCRIPTS:
            suffix=f'.{host}/hooks/{name}'
            forms=(f'python3 {suffix}',f'python3 "{suffix}"',
                   'python3 '+shlex.quote(str(root/suffix)),
                   f'python3 "{root/suffix}"')
            if host=='claude':forms=(*forms,f'python3 "$CLAUDE_PROJECT_DIR/{suffix}"')
            if command in forms:return True
            try:parts=hook_arguments(command)
            except ValueError:continue
            if len(parts) in {3,5} and parts[-2]=='-B' and parts[-1]==str(root/suffix):
                import re
                if Path(parts[0]).is_absolute() and re.fullmatch(r'python(?:3(?:\.\d+)?)?(?:\.exe)?',Path(parts[0]).name):return True
        return False
    merged={}
    for event,groups in hooks.items():
        if not isinstance(groups,list):return []
        retained=[]
        for group in groups:
            if not isinstance(group,dict) or not isinstance(group.get('hooks'),list):
                retained.append(group);continue
            entries=[entry for entry in group['hooks'] if not isinstance(entry,dict) or not owned(entry.get('command'))]
            if entries==group['hooks']:retained.append(group)
            elif entries:retained.append({**group,'hooks':entries})
        if retained:merged[event]=retained
    for event,groups in wanted.items():
        merged.setdefault(event,[]).extend(groups)
    config['hooks']=merged
    if json.dumps(config,sort_keys=True)==original:return []
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(config,indent=2)+'\n')
    return [str(destination)]


def _merge_claude_settings(root: Path) -> list[str]:
    fragment=root/'.claude/settings-fragment.json'
    try:desired=json.loads(fragment.read_text())
    except (OSError,ValueError):return []
    for groups in desired.get('hooks',{}).values():
        for group in groups:
            for hook in group.get('hooks',[]):
                command=hook.get('command')
                for name in CLAUDE_HOOK_SCRIPTS:
                    if command==f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/{name}"':
                        hook['command']=hook_command(sys.executable,root/'.claude/hooks'/name)
    return _merge_owned_hooks(root,'claude',desired,root/'.claude/settings.json')


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


def _prune_stale(src: Path, dst: Path, skip=None, tracked=None) -> list[str]:
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
    # Explicit receipt paths work through the recorded runtime alias. Path.rglob
    # intentionally does not traverse directory symlinks on supported Python.
    candidates=([dst/relative for relative in tracked] if tracked is not None else dst.rglob('*'))
    for path in sorted(candidates):
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
    return removed


def scaffold(target: Path | None = None, *, force: bool = False,
             on_phase=None, keep_stale: bool = False) -> dict:
    """Materialize a complete harness home. Returns a receipt dict.

    ``on_phase(label)`` is called before each materialization chunk so an
    interactive driver can show progress; it is optional plumbing and
    never changes what gets written.
    """
    from ..home import CompanyHome, fingerprint

    # keep_stale disables every pruning operation, including bytecode cleanup.
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
    home = CompanyHome(root)
    lean = home.lean
    if lean and (root / ".agents/company").resolve() != home.runtime.resolve():
        raise ValueError("Runtime compatibility alias changed; inspect the home before updating")

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

    # Refuse newly shipped paths that collide with untracked owner files.
    # This preflight runs before any update write; an update cannot claim
    # ownership of an existing owner file merely by shipping its filename.
    if existing_home:
        for tree, source in [("agents", templates / "agents"), *[
                (name, templates / "hosts" / name) for name in ("opencode", "codex", "claude")]]:
            destination = root / ("." + tree)
            tracked = set(manifest.get(tree, ())) if manifest is not None else set(_template_files(source))
            for relative in _template_files(source):
                if tree == "claude" and _claude_skip(relative): continue
                candidate = destination / relative
                if not candidate.resolve().is_relative_to(root):
                    raise ValueError(f"Installation path escapes the company: {candidate}")
                if candidate.exists() and relative not in tracked:
                    raise FileExistsError(f"New product file collides with owner content: {candidate}")

    notify("Vendoring harness spine")
    if existing_home and force and not keep_stale:
        # An update removes stale vendored files so the spine matches a
        # fresh init exactly; owner-created files in the user layers are
        # skipped, as is anything the current release still ships.
        removed = _prune_stale(templates / "agents", root / ".agents",
                                skip=layer_guard("agents"), tracked=(manifest or {}).get("agents", []))
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
        if existing_home and force and not keep_stale:
            written.extend(f"removed {item}" for item in _prune_stale(
                src, root / ("." + name), skip=layer_guard(name),tracked=(manifest or {}).get(name,[])))
        written += _copy_tree(src, root / ("." + name), overwrite=force,
                              skip=(_claude_skip if name == "claude" else (lambda relative:relative=="hooks.json") if name=="codex" else None))

    codex_source=templates/'hosts/codex/hooks.json'
    if codex_source.is_file():
        written += _merge_owned_hooks(root,'codex',json.loads(codex_source.read_text()),root/'.codex/hooks.json')

    # Resolve owned host commands at installation time. A company home need
    # not be a Git checkout, and hook processes inherit the session cwd.
    for host,relative_config in (('codex','.codex/hooks.json'),):
        codex_hooks = root / relative_config
        if not codex_hooks.is_file():continue
        config = json.loads(codex_hooks.read_text())
        changed = False
        owned = {
            "python3 .codex/hooks/spielos-context.py": "spielos-context.py",
            "python3 .codex/hooks/spielos-attention.py": "spielos-attention.py",
            "python3 .codex/hooks/spielos-observe.py": "spielos-observe.py",
        }
        if host=='claude':
            owned={f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/{name}"':name for name in CLAUDE_HOOK_SCRIPTS}
        for groups in config.get("hooks", {}).values():
            for group in groups:
                for hook in group.get("hooks", []):
                    script = owned.get(hook.get("command"))
                    if script:
                        hook["command"] = hook_command(sys.executable,root / ('.'+host) / 'hooks' / script)
                        changed = True
        if changed:
            codex_hooks.write_text(json.dumps(config, indent=2) + "\n")
            written.append(str(codex_hooks))

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
    entries = vendored_entries()
    if keep_stale and manifest:
        # Retained old vendored files remain known to later updates.
        for tree, paths in manifest.items():
            entries[tree] = sorted(set(entries.get(tree, ())) | set(paths))
    _write_manifest(root, entries)
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
        updated = _merge_operating_doc(current)
        if updated != current:
            agents_md.write_text(updated)
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

    # New homes start lean. Existing legacy homes require the separately
    # reviewed migration; ordinary update never relocates owner content.
    if not existing_home:
        plan = home.migration_plan()
        home.apply_migration(plan, expected_digest=fingerprint(plan))
        lean = True
    elif lean:
        home.initialize_content()
    if lean:
        from ..security import CompanyAuthority
        CompanyAuthority(root).bootstrap()

    return {
        "layout": "lean" if lean else "legacy; explicit migration required",
        "root": str(root),
        "template_source": str(templates),
        "files_written": len(written),
        "next_steps": [
            "cd " + str(root),
            "opencode (run /agents, select the Director agent), "
            "codex (the main chat acts as Director; review company hooks first), or claude "
            "(run claude --agent director)",
            "After reviewing host hooks, the Director receives company context automatically.",
            "Start with company/profile.md, strategy/ and brand/; build a bounded workflow with both harnesses.",
            "Keep credentials private; connecting a provider is a separate explicit action.",
            "Audit layout any time: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents "
            "python3 -B -m company layout",
        ],
    }


_GITIGNORE = """
# Company runtime: credentials, private inputs, state, generated work
.spielos/security/
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

_PRIMARY_DIRECTOR_MARKER = "<!-- spielos-primary-director v2 -->"

_PRIMARY_DIRECTOR_SECTION = """## Primary Director

<!-- spielos-primary-director v2 -->

The main owner chat is the primary Director; no Director subagent is needed.
The Director operates only the explicitly selected company. Authority comes from that home's AGENTS.md, installed host contract and selected runtime. Other workspaces, plugins and preview companies confer no authority: never import their identities, approvals or state. Use the local SpielOS CLI when its optional MCP is unavailable; never select another company implicitly.
Delegated agents keep only their explicitly assigned bounded workflow role.
Read `.codex/agents/director.toml` for the shared operating contract. Use the
injected read-only company projection; if missing, run status once for this
explicit home and explain the injection failure. Missing injected memory does
not imply deletion. Never bypass the selected host's hook review or copy trust
records from another path. Host configuration controls supported wakeups; no
SpielOS polling daemon is enabled.
"""

_LAYOUT_MARKER = "<!-- spielos-layout-contract v2 -->"

_LAYOUT_CONTRACT_SECTION = """## Company layout contract

<!-- spielos-layout-contract v2 -->

Editable company content lives in the visible `company/` folder:

| Path | Ownership |
| --- | --- |
| `profile.md` | explicit identity, users, owner, responsibilities and boundaries |
| `strategy/` | canonical owner direction and positioning |
| `brand/` | assets, design-system tokens/components, voice, templates and examples |
| `workflows/<id>/` | workflow.json, brief.md, execution, evaluation rubric/cases, examples |
| `agents/installed/`, `skills/` | reusable workflow implementation declarations |
| `connections/` | non-secret provider references |
| `departments/` | optional ownership groupings |

Pinned runtime code lives in `.spielos/runtime/company/`; `.agents/company` is
only its compatibility alias. Private state and artifacts live in `.spielos/`.
Do not put company content into runtime internals or credentials into definitions.
Audit with `company layout --home <this-home>`. Department-private build assets
may stay in their package. Updates never replace owner content templates.
"""

_PRODUCT_MARKER = "<!-- spielos-product-contract v2 -->"
_PRODUCT_CONTRACT_SECTION = """## Product operating contract

<!-- spielos-product-contract v2 -->

The current product concepts are Company, Workflow, Run and Improvement. This
section supersedes older generated instructions for Goal pursuit, WorkOrders,
six hidden content layers and runner commands; those records are historical.
One production Run invokes a pinned independently accepted workflow release,
uses scoped context, evaluates actual output and obtains its required review.
GODAE is the bounded development process for an Improvement, never a repeated
production pursuit. Structural edits require exact allowed files and actual
acceptance evidence. No product scheduler, tick/watch or autonomous repair runs.

Owner preferences and strategic direction are explicit; workflow lessons cite
evaluated runs of that workflow. Never fabricate facts, strategy, learning,
metrics or business impact. Show names, progress, outcomes and clear named
options; keep raw IDs, enums and JSON in machine payloads. Record the owner's
plain-language answer yourself. Exact external-action approval is separate from
quality and binds action, destination, content and scope. Do not send/publish or
enable a held integration merely because output passed evaluation.

Slash commands: /start invokes or builds bounded work; /stop cancels a named
run; /status inspects; /approve records the displayed exact-action decision;
/update refreshes reviewed product files. No command enables global pursuit.
Read `.agents/company/README.md` for the CLI/MCP contract and recovery limits.
"""

_AGENTS_MD = ("# Agent operating rules — harness section\n\n" + _PRODUCT_CONTRACT_SECTION
              + "\n" + _LAYOUT_CONTRACT_SECTION + "\n" + _PRIMARY_DIRECTOR_SECTION)


def _merge_operating_doc(current: str) -> str:
    """Refresh only explicitly marked generated sections, preserve owner notes."""
    import re
    updated=current
    for prefix,section in (("spielos-layout-contract",_LAYOUT_CONTRACT_SECTION),
                           ("spielos-primary-director",_PRIMARY_DIRECTOR_SECTION),
                           ("spielos-product-contract",_PRODUCT_CONTRACT_SECTION)):
        pattern=r"(?m)^## [^\n]+\n\n<!-- "+re.escape(prefix)+r" v[0-9]+ -->[\s\S]*?(?=^## |^# |\Z)"
        if re.search(pattern,updated):updated=re.sub(pattern,lambda match:section+"\n",updated,count=1)
        else:updated=updated.rstrip("\n")+"\n\n"+section
    return updated
