#!/usr/bin/env python3
"""tools/sync_adapters.py — Generate IDE adapter files from team/*.md.

SpielOS reads role prompts from `team/` (not `agents/`). This script
generates per-IDE adapter files so the same roles work in:

  - opencode (subagents + auto-generated skill stubs)
  - Claude Code (agents)
  - Cursor (slash commands)
  - MCP (server.json referencing canonical paths)

CLI:
    python3 tools/sync_adapters.py                  # regenerate adapters/ + skills/
    python3 tools/sync_adapters.py --install        # also install opencode to ~/.config/opencode/
    python3 tools/sync_adapters.py --check          # exit 1 if installed is out of date
    python3 tools/sync_adapters.py --show <ide>      # print what would be generated for one IDE
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


VAULT = Path(__file__).resolve().parent.parent
TEAM_DIR = VAULT / "team"
SKILLS_DIR = VAULT / "skills"
ADAPTERS_DIR = VAULT / "adapters"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode"
CURSOR_CONFIG = Path.home() / ".cursor"
CLAUDE_CONFIG = Path.home() / ".claude"
CODEX_CONFIG = Path.home() / ".codex"


# When the wizard runs sync_adapters from the canonical source repo but
# installs into a different target, VAULT_ROOT env var overrides the
# path that gets templated into the installed adapter files.
TEMPLATED_VAULT_ROOT = (
    Path(os.environ["VAULT_ROOT"]).expanduser().resolve()
    if os.environ.get("VAULT_ROOT")
    else VAULT
)


def _deep_merge_hooks(existing: dict, incoming: dict) -> dict:
    """Merge generated hook config into user hook config without dropping user hooks."""
    merged = dict(existing) if isinstance(existing, dict) else {}
    for event, value in incoming.items():
        if event not in merged or not isinstance(merged.get(event), dict) or not isinstance(value, dict):
            merged[event] = value
            continue
        event_cfg = dict(merged[event])
        for key, hook_value in value.items():
            if isinstance(event_cfg.get(key), list) and isinstance(hook_value, list):
                event_cfg[key] = event_cfg[key] + [h for h in hook_value if h not in event_cfg[key]]
            elif isinstance(event_cfg.get(key), dict) and isinstance(hook_value, dict):
                event_cfg[key] = {**event_cfg[key], **hook_value}
            else:
                event_cfg[key] = hook_value
        merged[event] = event_cfg
    return merged


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Returns (frontmatter_dict, body)."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2).strip()
    fm = {}
    try:
        import yaml
        fm = yaml.safe_load(fm_text) or {}
    except Exception:
        for line in fm_text.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def templated_text(text: str) -> str:
    """Replace `{vault_root}` placeholders with the absolute vault path.

    This is the bridge between the canonical team/*.md (which has
    `{vault_root}` in the frontmatter and body) and the installed copy
    (which has the absolute path baked in). The LLM running the MD subagent
    gets the absolute path, so it never gets confused by cwd.

    Called by emit_*() and install_*() for every role file.
    """
    return text.replace("{vault_root}", str(TEMPLATED_VAULT_ROOT))


def make_frontmatter(d: dict) -> str:
    """Render a dict as YAML frontmatter.

    Special handling for `tools:` (opencode requires an object or absence,
    not an array). Empty arrays become absent. Arrays of CLI tool paths
    become `{ bash: true }` (the subagent invokes them via the bash tool).
    """
    import yaml
    # Normalize tools: empty array -> omit; array of strings -> { bash: true }
    if "tools" in d:
        v = d["tools"]
        if isinstance(v, list) and len(v) == 0:
            del d["tools"]
        elif isinstance(v, list):
            # Treat as "this role can invoke CLI tools via bash"
            d["tools"] = {"bash": True}
    return "---\n" + yaml.safe_dump(d, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n\n"


def build_command_md(description: str, body: str, frontmatter: dict | None = None) -> str:
    """Build a slash-command markdown file from a description + body.

    Preserves command-relevant frontmatter fields (agent, model, subtask, vault_root)
    so that IDEs like opencode can dispatch commands to the right subagent and
    know the absolute vault path. Frontmatter values are run through templated_text
    so {vault_root} placeholders resolve to the absolute path.

    Single source of truth for how a slash command is rendered. Used by
    both the emit_*() and install_*() paths so the adapter/ folder and
    the live IDE config stay in sync byte-for-byte.
    """
    import yaml
    clean = {"description": description}
    if frontmatter:
        for key in ("agent", "model", "subtask", "name", "vault_root"):
            if key in frontmatter:
                value = frontmatter[key]
                if isinstance(value, str):
                    value = templated_text(value)
                clean[key] = value
    return "---\n" + yaml.safe_dump(clean, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n\n" + body.lstrip() + "\n"


def make_skill_stub(role_name: str, description: str) -> str:
    return (
        "---\n"
        f"name: {role_name}\n"
        f"description: {description}\n"
        "---\n\n"
        "# Spiel Content Dispatcher\n\n"
        f"When the user invokes `/post` or asks for content, delegate immediately to the `{role_name}` role.\n\n"
        f"The full role prompt lives at `team/{role_name}.md`. This skill is a one-line redirect for IDEs that discover skills separately from agents.\n\n"
        "Hard rules for the parent agent:\n\n"
        "- Do not explain the pipeline.\n"
        "- Do not ask what the user wants to do.\n"
        "- Do not offer a menu.\n"
        "- Do not run `spiel` commands yourself.\n"
        "- Do not read or summarize this skill back to the user.\n"
        "- Do not choose formats or publish decisions for the user.\n\n"
        f"The only correct parent action is to launch the `{role_name}` role with the user's exact request.\n"
    )


def roles() -> list[Path]:
    """Return sorted list of active SUBAGENT role files.

    Archived roles stay in `team/` for reference, but they are excluded from
    the live adapter surface so the IDEs only expose the production loop.
    """
    active = []
    for p in TEAM_DIR.glob("*.md"):
        if p.name in ("README.md", "post.md"):
            continue
        fm, _body = parse_frontmatter(p.read_text(encoding="utf-8"))
        if fm.get("status", "active") == "active":
            active.append(p)
    return sorted(active)


def commands() -> list[Path]:
    """Return sorted list of canonical SLASH COMMAND files (currently just post.md)."""
    return sorted(p for p in (TEAM_DIR / "post.md",) if p.exists())


def role_metadata(src: Path) -> tuple[str, str, dict, str]:
    """Return (role_name, description, frontmatter, body)."""
    fm, body = parse_frontmatter(src.read_text(encoding="utf-8"))
    return src.stem, fm.get("description", ""), fm, body


def skills() -> list[Path]:
    """Return sorted list of canonical skill folders (each has SKILL.md)."""
    return sorted(p for p in SKILLS_DIR.glob("*/SKILL.md"))


def skill_metadata(src: Path) -> tuple[str, str, dict, str]:
    """Return (skill_name, description, frontmatter, body) from a SKILL.md."""
    fm, body = parse_frontmatter(src.read_text(encoding="utf-8"))
    return src.parent.name, fm.get("description", ""), fm, body


def write_skill_stub(role_name: str, description: str, target: Path) -> None:
    """Legacy: kept for backwards compatibility. Use skills() instead."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(make_skill_stub(role_name, description), encoding="utf-8")


def emit_skill(role_name: str, description: str) -> None:
    """Legacy: emit auto-gen role stub. v2 uses real skills in skills/ instead."""


# ─── opencode adapter ────────────────────────────────────────────────────

def emit_opencode() -> int:
    """Write per-role subagents + slash commands + real skills to adapters/opencode/.

    Subagents (from team/*.md, excluding post.md + README) → adapters/opencode/agents/<name>.md
    Slash commands (from team/post.md + any future *.md)   → adapters/opencode/commands/<name>.md
    Skills (from skills/*/SKILL.md)                        → adapters/opencode/skill/<name>/SKILL.md
    """
    target = ADAPTERS_DIR / "opencode"
    (target / "agents").mkdir(parents=True, exist_ok=True)
    (target / "commands").mkdir(parents=True, exist_ok=True)
    (target / "skill").mkdir(parents=True, exist_ok=True)
    count = 0
    # Subagents from team/*.md (excludes post.md + README.md).
    for src in roles():
        role_name, description, _fm, _body = role_metadata(src)
        (target / "agents" / src.name).write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    # Slash commands from team/post.md (and any future command files).
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        (target / "commands" / src.name).write_text(
            build_command_md(description, templated_text(body), _fm),
            encoding="utf-8",
        )
        count += 1
    # Real skills from skills/*/SKILL.md
    for src in skills():
        skill_name, description, _fm, _body = skill_metadata(src)
        skill_dir = target / "skill" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    return count


# ─── Claude Code adapter ─────────────────────────────────────────────────

def emit_claude() -> int:
    """Write per-role subagents + slash commands to adapters/claude/.

    Subagents (from team/*.md, excluding post.md + README) → adapters/claude/agents/<name>.md
    Slash commands (from team/post.md + any future *.md)   → adapters/claude/commands/<name>.md
    """
    agents_target = ADAPTERS_DIR / "claude" / "agents"
    commands_target = ADAPTERS_DIR / "claude" / "commands"
    agents_target.mkdir(parents=True, exist_ok=True)
    commands_target.mkdir(parents=True, exist_ok=True)
    count = 0
    # Subagents (full role prompts — Claude discovers these as agents).
    for src in roles():
        (agents_target / src.name).write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    # Slash commands (stripped frontmatter, with `description:` only).
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        (commands_target / src.name).write_text(
            build_command_md(description, templated_text(body), _fm),
            encoding="utf-8",
        )
        count += 1
    return count


# ─── Cursor adapter ──────────────────────────────────────────────────────

def emit_cursor() -> int:
    """Write all roles (subagents + post command) as Cursor slash commands.

    Cursor doesn't have a separate subagent concept — every role is exposed
    as a /<name> slash command, including the 8 subagents AND the post
    command (which delegates to @md). All written to adapters/cursor/commands/.
    """
    target = ADAPTERS_DIR / "cursor" / "commands"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    # All roles (subagents) become /<role> slash commands.
    for src in roles():
        role_name, description, _fm, body = role_metadata(src)
        out = build_command_md(description, templated_text(body), _fm)
        (target / src.name).write_text(out, encoding="utf-8")
        count += 1
    # Plus post.md as /post (one-line dispatcher to @md).
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        out = build_command_md(description, templated_text(body), _fm)
        (target / src.name).write_text(out, encoding="utf-8")
        count += 1
    return count


# ─── MCP server adapter ──────────────────────────────────────────────────

def emit_mcp() -> int:
    target = ADAPTERS_DIR / "mcp"
    target.mkdir(parents=True, exist_ok=True)
    role_list = [{"name": src.stem, "path": str(src)} for src in roles()]
    config = {
        "server": {
            "name": "spielos",
            "version": "1.0.0",
            "vault": str(VAULT),
            "roles": role_list,
            "engine_entrypoint": str(VAULT / "bin" / "spiel"),
        }
    }
    (target / "server.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return 1


# ─── Codex adapter ──────────────────────────────────────────────────────

def _toml_agent(name: str, description: str, body: str) -> str:
    """Build a Codex agent TOML file from name + description + markdown body."""
    import yaml
    # Escape any triple-quotes in the body to avoid breaking the TOML literal.
    safe_body = body.replace('"""', '\\"\\"\\"')
    return (
        f'name = "{name}"\n'
        f'description = "{description}"\n'
        f'developer_instructions = """\n'
        f'{safe_body}\n'
        f'"""\n'
    )


CODEX_POST_DESCRIPTION = (
    "Start a content run. The deterministic UserPromptSubmit hook "
    "(plugins/spielos/hooks.json) runs first for topic/@file: invocations. "
    "This agent handles session mode (compile transcript, run spiel post "
    "--mode session) and advances the pipeline via spiel next for both modes. "
    "See team/post.md for details."
)


def _build_codex_post_toml_template() -> str:
    """Read the canonical Codex `post` subagent TOML template.

    The canonical source `adapters/codex/agents/post.toml` is already in
    Codex-compatible TOML form. Keep its `{vault_root}` placeholders intact
    in the source tree. Installed copies are templated separately. If the
    file is missing for any reason, fall back to a
    minimal safe body.
    """
    canonical = ADAPTERS_DIR / "codex" / "agents" / "post.toml"
    if canonical.is_file():
        return canonical.read_text(encoding="utf-8")
    return _toml_agent(
        name="post",
        description=CODEX_POST_DESCRIPTION,
        body=(
            "# /post\n\n"
            "Deterministic runtime already initialized. Read content/.state.json, "
            "run `spiel next`, and invoke the role it returns.\n"
        ),
    )


CODEX_POST_BODY = ""  # retained for back-compat; not used by install paths
CODEX_POST_TOML_TEMPLATE = _build_codex_post_toml_template()
CODEX_POST_TOML = templated_text(CODEX_POST_TOML_TEMPLATE)


def emit_codex() -> int:
    """Write per-role TOML agents + post dispatcher to adapters/codex/agents/.

    Codex uses a single `agents/` directory of TOML subagents; there is no
    separate `commands/` convention. `/post` is exposed as the `post` agent
    (TOML), invoked by typing `/post` in the Codex TUI. Earlier versions of
    this script wrote a markdown-with-YAML-frontmatter `commands/post.toml`
    which is invalid TOML and broke Codex adapter loading.
    """
    agents_target = ADAPTERS_DIR / "codex" / "agents"
    agents_target.mkdir(parents=True, exist_ok=True)
    count = 0
    # Subagents from team/*.md (excludes post.md + README.md).
    for src in roles():
        role_name, description, fm, body = role_metadata(src)
        body_with_vault = templated_text(body)
        toml = _toml_agent(src.stem, description, body_with_vault)
        (agents_target / f"{src.stem}.toml").write_text(toml, encoding="utf-8")
        count += 1
    # Post dispatcher template. Keep placeholders in adapters/ so this file
    # can be copied to a different vault without baking this machine's path.
    post_toml = CODEX_POST_TOML_TEMPLATE
    (agents_target / "post.toml").write_text(post_toml, encoding="utf-8")
    count += 1
    return count


def install_codex(verbose: bool = False) -> int:
    """Install to ~/.codex/agents/: active roles + post dispatcher.

    Codex has no `commands/` directory convention — custom subagents live
    only in `agents/`. `/post` is exposed as the `post` agent (TOML), and
    the user invokes it from the Codex TUI by typing `/post`.
    """
    if not CODEX_CONFIG.exists():
        if verbose:
            print(f"  [codex] {CODEX_CONFIG} not found — skipping")
        return 0
    agents_target = CODEX_CONFIG / "agents"
    agents_target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in roles():
        role_name, description, fm, body = role_metadata(src)
        body_with_vault = templated_text(body)
        toml = _toml_agent(src.stem, description, body_with_vault)
        (agents_target / f"{src.stem}.toml").write_text(toml, encoding="utf-8")
        count += 1
    # Post dispatcher
    post_agent = CODEX_POST_TOML
    (agents_target / "post.toml").write_text(post_agent, encoding="utf-8")
    count += 1
    count += install_codex_plugin_hooks(verbose=verbose)
    if verbose:
        print(f"  [codex] installed {count} files to {agents_target}")
    return count


def install_codex_plugin_hooks(verbose: bool = False) -> int:
    """Mirror the deterministic hook files into the live Codex plugin cache.

    The Codex plugin manager copies plugins from the marketplace source to
    `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`. Codex
    auto-discovers `hooks.json` at the plugin root and a `scripts/` sibling.
    The marketplace path resolution is a one-time setup; for in-development
    iterations we copy directly to the cache so the next Codex session picks
    up hook changes without forcing a marketplace reinstall.

    Discovers the marketplace name from `<vault>/.agents/plugins/marketplace.json`
    if present, then walks `~/.codex/plugins/cache/` for any matching
    `<marketplace>/spielos/<version>/` and copies:
      - hooks.json
      - scripts/post-hook.sh  (chmod +x)
      - plugin.json and assets

    If the source plugin no longer declares skills, any stale cached skills/
    directory is removed. The Codex plugin should package the real product
    hook and agents, not a duplicated skill-level pipeline.
    """
    import shutil

    if not CODEX_CONFIG.exists():
        return 0
    plugin_root = VAULT / "plugins" / "spielos"
    hooks_src = plugin_root / "hooks.json"
    script_src = plugin_root / "scripts" / "post-hook.sh"
    if not hooks_src.is_file() or not script_src.is_file():
        if verbose:
            print(f"  [codex-hooks] canonical source missing in {plugin_root} — skipping")
        return 0

    # Discover marketplace name(s) we may be installed under.
    marketplace_names: list[str] = []
    mp_json = VAULT / ".agents" / "plugins" / "marketplace.json"
    if mp_json.is_file():
        try:
            mp = json.loads(mp_json.read_text(encoding="utf-8"))
            if isinstance(mp, dict) and isinstance(mp.get("name"), str):
                marketplace_names.append(mp["name"])
        except (OSError, json.JSONDecodeError):
            pass
    # If we couldn't read the marketplace name, walk the cache and try
    # every <marketplace>/spielos/<version>/ directory that exists.
    cache_root = CODEX_CONFIG / "plugins" / "cache"
    if not cache_root.is_dir():
        return 0

    targets: list[Path] = []
    for mp_name in marketplace_names:
        plugin_cache = cache_root / mp_name / "spielos"
        if plugin_cache.is_dir():
            for ver in plugin_cache.iterdir():
                if ver.is_dir():
                    targets.append(ver)
    if not targets:
        # Fallback: scan every cache dir for a spielos subdir.
        for plugin_cache in cache_root.glob("*/spielos"):
            for ver in plugin_cache.iterdir():
                if ver.is_dir():
                    targets.append(ver)

    count = 0
    for target in targets:
        try:
            (target / "hooks.json").write_text(hooks_src.read_text(encoding="utf-8"), encoding="utf-8")
            scripts_dir = target / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            shutil.copy2(script_src, scripts_dir / "post-hook.sh")
            (scripts_dir / "post-hook.sh").chmod(0o755)
            skills_src = plugin_root / "skills"
            skills_dst = target / "skills"
            skill_files = list(skills_src.rglob("SKILL.md")) if skills_src.is_dir() else []
            if skill_files:
                if skills_dst.exists():
                    shutil.rmtree(skills_dst)
                # Copy skills with {vault_root} templated to the absolute path.
                # Skills are referenced from the LLM as part of the plugin,
                # and a literal {vault_root} placeholder is not a valid path.
                skills_dst.mkdir(parents=True, exist_ok=True)
                for skill_md in skill_files:
                    rel = skill_md.relative_to(skills_src)
                    dst_skill = skills_dst / rel
                    dst_skill.parent.mkdir(parents=True, exist_ok=True)
                    dst_skill.write_text(templated_text(skill_md.read_text(encoding="utf-8")), encoding="utf-8")
                # Copy any non-SKILL.md files (assets, etc.) verbatim.
                for f in skills_src.rglob("*"):
                    if f.is_dir():
                        continue
                    rel = f.relative_to(skills_src)
                    if rel.name == "SKILL.md":
                        continue
                    dst = skills_dst / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
            elif skills_dst.exists():
                shutil.rmtree(skills_dst)
            # Copy plugin assets (logo, etc.) referenced by plugin.json.
            assets_src = plugin_root / "assets"
            assets_dst = target / "assets"
            if assets_src.is_dir():
                if assets_dst.exists():
                    shutil.rmtree(assets_dst)
                shutil.copytree(assets_src, assets_dst)
            # Mirror plugin.json too so the version bump propagates.
            plugin_json_src = plugin_root / ".codex-plugin" / "plugin.json"
            plugin_json_dst = target / ".codex-plugin" / "plugin.json"
            if plugin_json_src.is_file():
                plugin_json_dst.parent.mkdir(parents=True, exist_ok=True)
                plugin_json_dst.write_text(plugin_json_src.read_text(encoding="utf-8"), encoding="utf-8")
            count += 1
            if verbose:
                print(f"  [codex-hooks] refreshed {target}")
        except OSError as e:
            if verbose:
                print(f"  [codex-hooks] could not refresh {target}: {e}", file=sys.stderr)
    return count

def detect_ide(config_dir: Path, name: str) -> bool:
    """Return True if this IDE's config dir looks like it's installed."""
    if not config_dir.parent.exists():
        return False
    if not config_dir.exists():
        print(f"  [{name}] {config_dir} not found — skipping")
        return False
    return True


def make_slash_command(role_name: str, description: str, body: str) -> str:
    """Build a slash-command markdown file from a role.

    Format: YAML frontmatter with description + body that delegates to the
    subagent (or runs the spiel shim as fallback). The body must be the
    role's full prompt — when the LLM sees this command, it acts as if it
    were the role for this turn.
    """
    import yaml
    fm = {"description": description}
    return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n\n" + body.lstrip()


def install_cursor_skills(verbose: bool = False) -> int:
    """Install Agent Skills at ~/.cursor/skills/<name>/SKILL.md.

    Cursor's "Agent Skills" feature reads skills from this dir. Each skill
    directory becomes a /name slash command in the Cursor chat box.
    """
    if not detect_ide(CURSOR_CONFIG, "cursor"):
        return 0
    target = CURSOR_CONFIG / "skills"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in skills():
        skill_name, _d, _fm, _body = skill_metadata(src)
        skill_dir = target / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        # Write the canonical SKILL.md with {vault_root} templated to absolute path.
        (skill_dir / "SKILL.md").write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [cursor] installed {count} skills to {target}")
    return count


def install_claude_skills(verbose: bool = False) -> int:
    """Install Agent Skills at ~/.claude/skills/<name>/SKILL.md.

    Claude Code's slash commands come from skills. Each skill becomes /name.
    """
    if not detect_ide(CLAUDE_CONFIG, "claude"):
        return 0
    target = CLAUDE_CONFIG / "skills"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in skills():
        skill_name, _d, _fm, _body = skill_metadata(src)
        skill_dir = target / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        # Write the canonical SKILL.md with {vault_root} templated to absolute path.
        (skill_dir / "SKILL.md").write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [claude] installed {count} skills to {target}")
    return count


def install_claude_agents(verbose: bool = False) -> int:
    """Install subagent files at ~/.claude/agents/<name>.md.

    Claude Code discovers subagents from this dir (scanned recursively).
    The user's existing agents dir may have stale files from a prior install
    — this overwrites them with the current canonical prompts.
    """
    if not detect_ide(CLAUDE_CONFIG, "claude"):
        return 0
    target = CLAUDE_CONFIG / "agents"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in roles():
        # Strip our opencode-specific frontmatter keys; Claude uses a subset
        role_name, description, _fm, body = role_metadata(src)
        import yaml
        clean_fm = {"name": role_name, "description": description}
        # If the role uses tools: {...} (opencode format), keep it; Claude accepts it
        if "tools" in _fm:
            clean_fm["tools"] = _fm["tools"]
        # Also preserve vault_root (Claude should also know the absolute vault path)
        if "vault_root" in _fm:
            clean_fm["vault_root"] = str(TEMPLATED_VAULT_ROOT)
        out = "---\n" + yaml.safe_dump(clean_fm, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n\n" + templated_text(body).lstrip()
        (target / src.name).write_text(out, encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [claude] installed {count} agents to {target}")
    return count


def install_claude_commands(verbose: bool = False) -> int:
    """Install slash commands at ~/.claude/commands/<name>.md.

    Claude Code discovers slash commands from this dir. The `post.md` slash
    command lives here and dispatches to the `md` subagent.
    """
    if not detect_ide(CLAUDE_CONFIG, "claude"):
        return 0
    target = CLAUDE_CONFIG / "commands"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        (target / src.name).write_text(build_command_md(description, templated_text(body), _fm), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [claude] installed {count} commands to {target}")
    return count


def install_claude_hooks(verbose: bool = False) -> int:
    """Install deterministic post hooks into ~/.claude/settings.json.

    Merges the canonical hooks from adapters/claude/hooks.json into the user's
    settings.json, preserving any existing settings (model, permissions, etc.).
    Templates {vault_root} in hook commands to the absolute vault path.
    Sets VAULT_DIR in the env section so the hook script can find the vault.
    """
    if not detect_ide(CLAUDE_CONFIG, "claude"):
        return 0
    src = ADAPTERS_DIR / "claude" / "hooks.json"
    if not src.is_file():
        return 0
    target = CLAUDE_CONFIG / "settings.json"
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    # Read and template {vault_root} in hook commands
    hooks_text = src.read_text(encoding="utf-8")
    hooks_text = hooks_text.replace("{vault_root}", str(TEMPLATED_VAULT_ROOT))
    new_hooks = json.loads(hooks_text)
    incoming_hooks = new_hooks.get("hooks", {})

    if incoming_hooks:
        existing["hooks"] = _deep_merge_hooks(existing.get("hooks", {}), incoming_hooks)

    # Set VAULT_DIR in env so the hook script can find the vault
    if "env" not in existing or not isinstance(existing.get("env"), dict):
        existing["env"] = {}
    existing["env"]["VAULT_DIR"] = str(TEMPLATED_VAULT_ROOT)

    target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    if verbose:
        action = "merged hooks into" if incoming_hooks else "preserved hooks in"
        print(f"  [claude] {action} {target}")
    return 1 if incoming_hooks else 0


def install_cursor_hooks(verbose: bool = False) -> int:
    """Install deterministic post hooks to ~/.cursor/hooks.json + post-hook.py script.

    Templates {vault_root} in hook commands to the absolute vault path.
    """
    if not detect_ide(CURSOR_CONFIG, "cursor"):
        return 0
    count = 0
    src = ADAPTERS_DIR / "cursor" / "hooks.json"
    if not src.is_file():
        return 0
    target = CURSOR_CONFIG / "hooks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Template {vault_root} in hooks.json
    hooks_text = src.read_text(encoding="utf-8")
    hooks_text = hooks_text.replace("{vault_root}", str(TEMPLATED_VAULT_ROOT))
    incoming = json.loads(hooks_text)
    incoming_hooks = incoming.get("hooks", {})
    if not incoming_hooks:
        if verbose:
            print(f"  [cursor] canonical hooks are empty; preserved {target}")
        return 0
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}
    existing["version"] = incoming.get("version", existing.get("version", 1))
    existing["hooks"] = _deep_merge_hooks(existing.get("hooks", {}), incoming_hooks)
    target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    count += 1
    if verbose:
        print(f"  [cursor] installed hooks ({count} files) to {CURSOR_CONFIG}")
    return count


def install_cursor_commands(verbose: bool = False) -> int:
    """Install slash commands at ~/.cursor/commands/<name>.md.

    Cursor discovers slash commands from this dir.
    """
    if not detect_ide(CURSOR_CONFIG, "cursor"):
        return 0
    target = CURSOR_CONFIG / "commands"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    # Cursor treats every role as a /<role> slash command (no separate
    # subagent concept). So we write both the canonical subagents AND
    # the slash commands (post.md, etc.) here, mirroring adapters/cursor/commands/.
    for src in roles():
        role_name, description, _fm, body = role_metadata(src)
        (target / src.name).write_text(build_command_md(description, templated_text(body), _fm), encoding="utf-8")
        count += 1
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        (target / src.name).write_text(build_command_md(description, templated_text(body), _fm), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [cursor] installed {count} commands to {target}")
    return count


def install_opencode(verbose: bool = False) -> int:
    """Install to ~/.config/opencode/:

      - subagents (from team/*.md, excluding post.md) → agents/<name>.md
      - commands (from team/post.md) → commands/post.md
      - skills (from skills/*/SKILL.md) → skill/<name>/SKILL.md
    """
    if not OPENCODE_CONFIG.exists():
        print(f"  {OPENCODE_CONFIG} does not exist — skipping install")
        return 0
    count = 0
    # Subagents: team/*.md except post.md
    for src in roles():
        dst_agent = OPENCODE_CONFIG / "agents" / src.name
        dst_agent.parent.mkdir(parents=True, exist_ok=True)
        dst_agent.write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    # Commands: post.md (and any future command files)
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        dst_cmd = OPENCODE_CONFIG / "commands" / src.name
        dst_cmd.parent.mkdir(parents=True, exist_ok=True)
        dst_cmd.write_text(build_command_md(description, templated_text(body), _fm), encoding="utf-8")
        count += 1
    # Skills: skills/*/SKILL.md
    for src in skills():
        skill_name, _desc, _fm, _body = skill_metadata(src)
        skill_dir = OPENCODE_CONFIG / "skill" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  installed {count} files (subagents + commands + skills) to {OPENCODE_CONFIG}")
    return count


def install_opencode_skills(verbose: bool = False) -> int:
    """Install only the real skills (from skills/*/SKILL.md) to ~/.config/opencode/skill/."""
    if not OPENCODE_CONFIG.exists():
        return 0
    target = OPENCODE_CONFIG / "skill"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in skills():
        skill_name, _desc, _fm, _body = skill_metadata(src)
        skill_dir = target / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(templated_text(src.read_text(encoding="utf-8")), encoding="utf-8")
        count += 1
    return count


def _collect_installed_paths() -> dict[Path, str]:
    """Walk every installed IDE location and return {path: content} for every
    file we manage (subagents, commands, skills).

    Used by --check to compare against freshly-emitted content.
    """
    out: dict[Path, str] = {}

    def _walk(ide_root: Path, subdirs: list[str], kind: str) -> None:
        if not ide_root.exists():
            return
        for sub in subdirs:
            d = ide_root / sub
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        out[f] = f.read_text(encoding="utf-8")
                    except OSError:
                        pass

    # opencode: agents/, commands/, skill/
    _walk(OPENCODE_CONFIG, ["agents", "commands", "skill"], "opencode")
    # Cursor: skills/, commands/
    _walk(CURSOR_CONFIG, ["skills", "commands"], "cursor")
    # Claude Code: agents/, skills/, commands/
    _walk(CLAUDE_CONFIG, ["agents", "skills", "commands"], "claude")
    # Codex: agents/ + plugin cache hooks/scripts
    _walk(CODEX_CONFIG, ["agents", "commands"], "codex")
    # Codex plugin cache: hooks.json + scripts/post-hook.sh inside each
    # <marketplace>/<plugin>/<version>/.
    codex_cache = CODEX_CONFIG / "plugins" / "cache"
    if codex_cache.is_dir():
        for plugin_dir in codex_cache.glob("*/spielos/*"):
            if not plugin_dir.is_dir():
                continue
            for hook_file in ("hooks.json", "scripts/post-hook.sh"):
                p = plugin_dir / hook_file
                if p.is_file():
                    try:
                        out[p] = p.read_text(encoding="utf-8")
                    except OSError:
                        pass
    return out


def _cleanup_stale_files(verbose: bool = False) -> int:
    """Remove installed files that no longer exist in the canonical source.

    Prevents stale role files (e.g., old `md.md` from the 8-role system) from
    being left behind in `~/.config/opencode/agents/`, `~/.claude/agents/`, etc.
    after a refactor or role rename.

    Only removes files that are managed by SpielOS (i.e., files we would have
    written). User-added files in those directories are preserved.

    Returns count of stale files removed.
    """
    expected = set(_expected_content().keys())
    installed_content = _collect_installed_paths()
    installed = set(installed_content.keys())
    stale = installed - expected
    removed = 0
    for path in stale:
        text = installed_content.get(path, "")
        if "SpielOS" not in text and "spiel" not in text.lower() and "content/.state.json" not in text:
            if verbose:
                print(f"  [cleanup] preserved unmarked file: {path}")
            continue
        try:
            path.unlink()
            removed += 1
            if verbose:
                print(f"  [cleanup] removed stale: {path}")
        except OSError as e:
            if verbose:
                print(f"  [cleanup] could not remove {path}: {e}", file=sys.stderr)
    if verbose and removed:
        print(f"  [cleanup] removed {removed} stale file(s)")
    return removed


def _expected_content() -> dict[Path, str]:
    """Compute what every installed IDE file SHOULD be, based on the canonical
    team/*.md + skills/*/SKILL.md. Returns {installed_path: expected_content}.

    Mirrors the install_*() functions so --check can diff cleanly.
    """
    expected: dict[Path, str] = {}

    # opencode subagents (team/*.md except post.md) → agents/<name>.md
    if OPENCODE_CONFIG.exists():
        for src in roles():
            expected[OPENCODE_CONFIG / "agents" / src.name] = templated_text(src.read_text(encoding="utf-8"))
        # opencode commands (post.md + future) → commands/<name>.md
        for src in commands():
            role_name, description, _fm, body = role_metadata(src)
            expected[OPENCODE_CONFIG / "commands" / src.name] = (
                build_command_md(description, templated_text(body), _fm)
            )
        # opencode skills (skills/*/SKILL.md) → skill/<name>/SKILL.md
        for src in skills():
            skill_name, _d, _fm, _body = skill_metadata(src)
            expected[OPENCODE_CONFIG / "skill" / skill_name / "SKILL.md"] = (
                src.read_text(encoding="utf-8")
            )

    # Cursor commands + skills
    if CURSOR_CONFIG.exists():
        for src in roles():
            role_name, description, _fm, body = role_metadata(src)
            expected[CURSOR_CONFIG / "commands" / src.name] = (
                build_command_md(description, templated_text(body), _fm)
            )
        for src in commands():
            role_name, description, _fm, body = role_metadata(src)
            expected[CURSOR_CONFIG / "commands" / src.name] = (
                build_command_md(description, templated_text(body), _fm)
            )
        for src in skills():
            skill_name, _d, _fm, _body = skill_metadata(src)
            expected[CURSOR_CONFIG / "skills" / skill_name / "SKILL.md"] = (
                src.read_text(encoding="utf-8")
            )

    # Claude Code agents + commands + skills
    if CLAUDE_CONFIG.exists():
        for src in roles():
            role_name, description, _fm, body = role_metadata(src)
            import yaml as _yaml
            clean = {"name": role_name, "description": description}
            if "tools" in _fm:
                clean["tools"] = _fm["tools"]
            if "vault_root" in _fm:
                clean["vault_root"] = str(TEMPLATED_VAULT_ROOT)
            expected[CLAUDE_CONFIG / "agents" / src.name] = (
                "---\n"
                + _yaml.safe_dump(clean, sort_keys=False, allow_unicode=True).rstrip()
                + "\n---\n\n"
                + templated_text(body).lstrip()
            )
        for src in commands():
            role_name, description, _fm, body = role_metadata(src)
            expected[CLAUDE_CONFIG / "commands" / src.name] = (
                build_command_md(description, templated_text(body), _fm)
            )
        for src in skills():
            skill_name, _d, _fm, _body = skill_metadata(src)
            expected[CLAUDE_CONFIG / "skills" / skill_name / "SKILL.md"] = (
                src.read_text(encoding="utf-8")
            )

    # Codex agents (TOML format, agents/ only — no commands/ dir)
    if CODEX_CONFIG.exists():
        for src in roles():
            role_name, description, _fm, body = role_metadata(src)
            expected[CODEX_CONFIG / "agents" / f"{src.stem}.toml"] = (
                _toml_agent(src.stem, description, templated_text(body))
            )
        expected[CODEX_CONFIG / "agents" / "post.toml"] = CODEX_POST_TOML

    # Codex plugin cache: hooks.json + scripts/post-hook.sh mirror.
    # We register both files against the canonical bytes. The install
    # step copies the canonical content directly (chmod +x for the
    # script), so the on-disk bytes match the canonical bytes modulo
    # the chmod bit. Treat both as content-matched.
    codex_cache = CODEX_CONFIG / "plugins" / "cache"
    if codex_cache.is_dir():
        canonical_hooks = VAULT / "plugins" / "spielos" / "hooks.json"
        canonical_script = VAULT / "plugins" / "spielos" / "scripts" / "post-hook.sh"
        hooks_text = canonical_hooks.read_text(encoding="utf-8") if canonical_hooks.is_file() else None
        script_text = canonical_script.read_text(encoding="utf-8") if canonical_script.is_file() else None
        for plugin_dir in codex_cache.glob("*/spielos/*"):
            if not plugin_dir.is_dir():
                continue
            if hooks_text is not None:
                expected[plugin_dir / "hooks.json"] = hooks_text
            if script_text is not None:
                expected[plugin_dir / "scripts" / "post-hook.sh"] = script_text

    return expected


# ─── MCP Server Installation ──────────────────────────────────────────────

def _read_env(key: str, default: str = "") -> str:
    env_file = VAULT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(key, default)


def _mcp_servers_from_env() -> dict:
    servers = {}
    buffer_token = _read_env("BUFFER_ACCESS_TOKEN")
    if buffer_token:
        servers["buffer"] = {
            "command": "npx",
            "args": ["-y", "@damusix/buffer-mcp"],
            "env": {"BUFFER_ACCESS_TOKEN": buffer_token},
        }
    wp_url = _read_env("WP_URL")
    wp_user = _read_env("WP_USERNAME")
    wp_pass = _read_env("WP_APP_PASSWORD")
    if wp_url and wp_user and wp_pass:
        servers["wordpress"] = {
            "command": "npx",
            "args": ["-y", "@wpgaurav/wp-mcp"],
            "env": {
                "WP_URL": wp_url,
                "WP_USERNAME": wp_user,
                "WP_APP_PASSWORD": wp_pass,
            },
        }
    devto_key = _read_env("DEVTO_API_KEY")
    if devto_key:
        servers["devto"] = {
            "command": "npx",
            "args": ["-y", "@furkankoykiran/devto-mcp"],
            "env": {"DEVTO_API_KEY": devto_key},
        }
    return servers


def install_mcp_servers(verbose: bool = False) -> int:
    servers = _mcp_servers_from_env()
    if not servers:
        print("  No MCP servers configured. Set BUFFER_ACCESS_TOKEN, WP_URL, "
              "or DEVTO_API_KEY in .env")
        return 0

    count = 0

    # opencode — mcp in opencode.jsonc (McpLocalConfig format)
    oc_config = OPENCODE_CONFIG / "opencode.jsonc"
    if oc_config.exists():
        try:
            text = oc_config.read_text(encoding="utf-8")
            has_mcp = '"mcp"' in text
            if has_mcp:
                if verbose:
                    print(f"  opencode: mcp config already in {oc_config}")
            else:
                oc_servers = {}
                for name, cfg in servers.items():
                    oc_servers[name] = {
                        "type": "local",
                        "command": [cfg["command"]] + cfg.get("args", []),
                        "environment": cfg.get("env", {}),
                    }
                mcp_json = json.dumps({"mcp": oc_servers}, indent=2)
                new_text = text.rstrip()
                if new_text.endswith("}"):
                    new_text = new_text[:-1].rstrip() + ",\n" + mcp_json[1:] + "\n"
                oc_config.write_text(new_text, encoding="utf-8")
                count += 1
                if verbose:
                    print(f"  opencode: added mcp to {oc_config}")
        except OSError as e:
            if verbose:
                print(f"  opencode: could not write MCP config: {e}")

    # Cursor — ~/.cursor/mcp.json
    cursor_mcp = CURSOR_CONFIG / "mcp.json"
    if CURSOR_CONFIG.exists():
        existing = {}
        if cursor_mcp.exists():
            try:
                existing = json.loads(cursor_mcp.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        existing_servers = existing.get("mcpServers", {})
        for name, cfg in servers.items():
            existing_servers[name] = cfg
        existing["mcpServers"] = existing_servers
        cursor_mcp.parent.mkdir(parents=True, exist_ok=True)
        cursor_mcp.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        count += 1
        if verbose:
            print(f"  cursor: wrote {cursor_mcp} ({len(servers)} server(s))")

    # Claude — ~/.claude/claude_desktop_config.json
    claude_config = CLAUDE_CONFIG / "claude_desktop_config.json"
    if CLAUDE_CONFIG.exists():
        existing = {}
        if claude_config.exists():
            try:
                existing = json.loads(claude_config.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        existing_servers = existing.get("mcpServers", {})
        for name, cfg in servers.items():
            existing_servers[name] = cfg
        existing["mcpServers"] = existing_servers
        claude_config.parent.mkdir(parents=True, exist_ok=True)
        claude_config.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        count += 1
        if verbose:
            print(f"  claude: wrote {claude_config} ({len(servers)} server(s))")

    # Codex — ~/.codex/config.json (MCP servers section)
    codex_config = CODEX_CONFIG / "config.json"
    if CODEX_CONFIG.exists():
        existing = {}
        if codex_config.exists():
            try:
                existing = json.loads(codex_config.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        existing_servers = existing.get("mcpServers", {})
        for name, cfg in servers.items():
            existing_servers[name] = cfg
        existing["mcpServers"] = existing_servers
        codex_config.parent.mkdir(parents=True, exist_ok=True)
        codex_config.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        count += 1
        if verbose:
            print(f"  codex: wrote {codex_config} ({len(servers)} server(s))")

    return count


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate IDE adapter files from team/*.md")
    parser.add_argument("--install", action="store_true",
                        help="Install to all detected IDE configs "
                             "(opencode: agents + commands + skills, "
                             "Cursor: skills + commands, Claude Code: skills + agents + commands, "
                             "Codex: agents)")
    parser.add_argument("--install-opencode", action="store_true",
                        help="Install to opencode only (agents + commands + skills)")
    parser.add_argument("--install-cursor", action="store_true",
                        help="Install to Cursor only (skills + commands)")
    parser.add_argument("--install-claude", action="store_true",
                        help="Install to Claude Code only (skills + agents + commands)")
    parser.add_argument("--install-codex", action="store_true",
                        help="Install to Codex only (agents)")
    parser.add_argument("--mcp", action="store_true",
                        help="Install MCP server configs to all detected IDEs "
                             "(reads credentials from .env)")
    parser.add_argument("--check", action="store_true",
                        help="Compare installed adapters against canonical "
                             "team/*.md + skills/*.md. Exit 0 if in sync, "
                             "1 if any file would be regenerated, 2 if any "
                             "files are missing entirely.")
    parser.add_argument("--show", metavar="IDE", choices=["opencode", "claude", "cursor", "mcp", "codex"],
                        help="Print what would be generated for one IDE (no files written).")
    args = parser.parse_args()

    if not TEAM_DIR.exists():
        print(f"ERROR: {TEAM_DIR} not found. Run from vault root.")
        return 1

    if args.show:
        for src in roles():
            print(f"-- {src} --")
            print(src.read_text(encoding="utf-8"))
            role_name, desc, _, _ = role_metadata(src)
            print(f"-- skills/{role_name}/SKILL.md --")
            print(make_skill_stub(role_name, desc))
        return 0

    # --check: diff installed adapters against canonical. No file writes.
    if args.check:
        expected = _expected_content()
        installed = _collect_installed_paths()
        mismatched: list[Path] = []
        missing: list[Path] = []
        ok = 0
        for path, want in expected.items():
            if path not in installed:
                missing.append(path)
                continue
            if installed[path] != want:
                mismatched.append(path)
            else:
                ok += 1
        # Also report stale files (installed but no longer expected).
        expected_paths = set(expected.keys())
        stale = []
        for p, text in installed.items():
            if p in expected_paths or not p.is_file() or p.suffix != ".md":
                continue
            if "SpielOS" in text or "spiel" in text.lower() or "content/.state.json" in text:
                stale.append(p)
        if ok and not mismatched and not missing and not stale:
            print(f"  ✓ {ok} installed adapter file(s) match canonical. nothing to do.")
            return 0
        print(f"  ✗ {len(mismatched)} mismatched, {len(missing)} missing, {len(stale)} stale.")
        for p in mismatched[:20]:
            print(f"    diff: {p}")
        for p in missing[:20]:
            print(f"    miss: {p}")
        for p in stale[:20]:
            print(f"    stale: {p}")
        return 1 if missing else 2

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    n_skills = sum(1 for _ in SKILLS_DIR.glob("*/SKILL.md"))
    print(f"Found {n_skills} canonical skill(s) in skills/")

    n_oc = emit_opencode()
    n_cl = emit_claude()
    n_cu = emit_cursor()
    n_mc = emit_mcp()
    n_cx = emit_codex()
    total = n_oc + n_cl + n_cu + n_mc + n_cx
    print(f"Generated {total} adapter files in adapters/  "
          f"(opencode={n_oc}, claude={n_cl}, cursor={n_cu}, mcp={n_mc}, codex={n_cx})")

    # --mcp: standalone MCP server installation
    if args.mcp and not (args.install or args.install_opencode or args.install_cursor or args.install_claude or args.install_codex):
        n_mcp = install_mcp_servers(verbose=True)
        print(f"\nMCP servers installed: {n_mcp} IDE config(s) updated")
        return 0

    if args.install or args.install_opencode or args.install_cursor or args.install_claude or args.install_codex:
        do_oc = args.install or args.install_opencode
        do_cu = args.install or args.install_cursor
        do_cl = args.install or args.install_claude
        do_cx = args.install or args.install_codex

        n_oc_inst = install_opencode() if do_oc else 0
        n_cu_inst = (install_cursor_skills() + install_cursor_commands() + install_cursor_hooks()) if do_cu else 0
        n_cl_inst = (install_claude_skills() + install_claude_agents() + install_claude_commands() + install_claude_hooks()) if do_cl else 0
        n_cx_inst = install_codex() if do_cx else 0

        print()
        print(f"Installed to live IDEs:")
        if do_oc:
            print(f"  opencode:    {OPENCODE_CONFIG}  (agents + commands + skills)")
        if do_cu:
            print(f"  cursor:      {CURSOR_CONFIG}  (skills + commands + hooks)")
        if do_cl:
            print(f"  claude:      {CLAUDE_CONFIG}  (agents + skills + commands + hooks)")
        if do_cx:
            print(f"  codex:       {CODEX_CONFIG}  (agents)")

        # Remove stale files (e.g., old role files from a refactor that are
        # no longer in the canonical source).
        n_stale = _cleanup_stale_files(verbose=True)
        if n_stale:
            print(f"  ✓ removed {n_stale} stale file(s) from previous install")

    # MCP servers can also be installed as part of --install
    if args.install or args.mcp:
        n_mcp = install_mcp_servers(verbose=True)
        if n_mcp:
            print(f"  ✓ MCP server config(s) written to {n_mcp} IDE(s)")

    if not (args.install or args.install_opencode or args.install_cursor or args.install_claude or args.install_codex or args.mcp):
        print()
        print(f"To install to all detected IDEs, re-run with --install")
        print(f"  opencode:    {OPENCODE_CONFIG}")
        print(f"  cursor:      {CURSOR_CONFIG}")
        print(f"  claude:      {CLAUDE_CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
