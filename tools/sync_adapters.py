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

    Preserves command-relevant frontmatter fields (agent, model, subtask)
    so that IDEs like opencode can dispatch commands to the right subagent.

    Single source of truth for how a slash command is rendered. Used by
    both the emit_*() and install_*() paths so the adapter/ folder and
    the live IDE config stay in sync byte-for-byte.
    """
    import yaml
    clean = {"description": description}
    if frontmatter:
        for key in ("agent", "model", "subtask", "name"):
            if key in frontmatter:
                clean[key] = frontmatter[key]
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
    # Post dispatcher: a minimal agent that delegates to @director.
    post_toml = _toml_agent(
        name="post",
        description="Dispatch a /post request. Delegates to @director with the user's args. See team/post.md for details.",
        body=(
            "# /post - Dispatch to @director\n\n"
            "You are a dispatch agent, not a pipeline runner. Your ONLY action:\n\n"
            "1. Read the user's message after `/post`.\n"
            "2. Invoke @director with the exact text the user typed after /post.\n"
            "3. If the user typed just `/post` with no args, invoke @director with no args.\n"
            "4. Return @director's response. Do nothing else.\n\n"
            "Hard rules:\n"
            "- No preamble, menu, or clarification.\n"
            "- No running tools (bash, read, write, grep, glob).\n"
            "- No deciding mode (topic/file/session) - @director parses the args.\n"
            "- No writing files.\n"
            "- No explaining the pipeline.\n"
        ),
    )
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
    post_agent = _toml_agent(
        name="post",
        description="Dispatch a /post request. Delegates to @director with the user's args. See team/post.md for details.",
        body=(
            "# /post\n\nInvoke `@director` with the exact text after `/post`.\n"
        ),
    )
    (agents_target / "post.toml").write_text(post_agent, encoding="utf-8")
    count += 1
    if verbose:
        print(f"  [codex] installed {count} files to {agents_target}")
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
    new_hooks = json.loads(src.read_text(encoding="utf-8"))
    if "hooks" not in existing or not isinstance(existing.get("hooks"), dict):
        existing["hooks"] = {}
    existing["hooks"].update(new_hooks.get("hooks", {}))
    target.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    if verbose:
        print(f"  [claude] installed hooks to {target}")
    return 1


def install_cursor_hooks(verbose: bool = False) -> int:
    """Install deterministic post hooks to ~/.cursor/hooks.json + post-hook.py script."""
    if not detect_ide(CURSOR_CONFIG, "cursor"):
        return 0
    count = 0
    src = ADAPTERS_DIR / "cursor" / "hooks.json"
    if not src.is_file():
        return 0
    target = CURSOR_CONFIG / "hooks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    count += 1
    hooks_scripts_dir = CURSOR_CONFIG / "hooks"
    hooks_scripts_dir.mkdir(parents=True, exist_ok=True)
    script_src = VAULT / "tools" / "post-hook.py"
    if script_src.is_file():
        script_dst = hooks_scripts_dir / "post-hook.py"
        script_dst.write_text(script_src.read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(script_dst, 0o755)
        count += 1
    if verbose:
        print(f"  [cursor] installed hooks ({count} files) to {CURSOR_CONFIG}")
    return count


def install_opencode_plugins(verbose: bool = False) -> int:
    """Install deterministic post plugins to ~/.config/opencode/plugins/."""
    if not OPENCODE_CONFIG.exists():
        print(f"  {OPENCODE_CONFIG} does not exist — skipping install")
        return 0
    src_dir = ADAPTERS_DIR / "opencode" / "plugins"
    if not src_dir.is_dir():
        return 0
    target = OPENCODE_CONFIG / "plugins"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src_dir.glob("*.ts"):
        dst = target / f.name
        dst.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [opencode] installed {count} plugins to {target}")
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
    # Register the post-hook plugin so /post captures the session.
    if _register_opencode_plugin(verbose=verbose):
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
    # Codex: agents/
    _walk(CODEX_CONFIG, ["agents", "commands"], "codex")
    return out


def _register_opencode_plugin(verbose: bool = False) -> bool:
    """Register the post-hook plugin in ~/.config/opencode/opencode.jsonc.

    The plugin is what captures the session transcript and writes
    content/current.md + content/sessions/current.md to the vault
    BEFORE the Director subagent runs. Without this registration, the
    Director gets an empty session and halts.

    Idempotent: safe to run multiple times. Preserves all other config.
    """
    config_path = OPENCODE_CONFIG / "opencode.jsonc"
    if not config_path.exists():
        return False

    plugin_path = "~/.config/opencode/plugins/post-hook.ts"
    expected_entry = str(Path(plugin_path).expanduser())

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return False

    # Already registered? Check both absolute and ~ forms.
    if (expected_entry in text or
        plugin_path in text or
        "post-hook.ts" in text):
        return False

    # Find the right place to insert. Prefer after "skills" if present,
    # else after the opening "{".
    import re
    insertion = f'  "plugin": ["{plugin_path}"],\n'

    if '"skills"' in text:
        # Insert after the skills block's closing brace.
        new_text = re.sub(
            r'("skills"\s*:\s*\{[^}]*\}\s*,?)',
            r'\1\n' + insertion.rstrip(",\n") + ",",
            text,
            count=1,
        )
        if new_text == text:
            # Fallback: insert before "provider"
            new_text = text.replace('  "provider"', insertion + '  "provider"', 1)
    elif '"provider"' in text:
        new_text = text.replace('  "provider"', insertion + '  "provider"', 1)
    else:
        return False

    if new_text == text:
        return False

    config_path.write_text(new_text, encoding="utf-8")
    if verbose:
        print(f"  [plugin] registered {plugin_path} in {config_path}")
    return True


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
    installed = set(_collect_installed_paths().keys())
    stale = installed - expected
    removed = 0
    for path in stale:
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
        expected[CODEX_CONFIG / "agents" / "post.toml"] = _toml_agent(
            name="post",
            description="Dispatch a /post request. Delegates to @director with the user's args. See team/post.md for details.",
            body="# /post\n\nInvoke `@director` with the exact text after `/post`.\n",
        )

    return expected


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
        stale = [p for p in installed if p in (
            OPENCODE_CONFIG.rglob("*") if OPENCODE_CONFIG.exists() else [],
            CURSOR_CONFIG.rglob("*") if CURSOR_CONFIG.exists() else [],
            CLAUDE_CONFIG.rglob("*") if CLAUDE_CONFIG.exists() else [],
        ) and isinstance(p, Path) and p.is_file()
            and p.suffix in (".md",) and not any(p.match(str(ep)) for ep in expected_paths)]
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

    if args.install or args.install_opencode or args.install_cursor or args.install_claude or args.install_codex:
        do_oc = args.install or args.install_opencode
        do_cu = args.install or args.install_cursor
        do_cl = args.install or args.install_claude
        do_cx = args.install or args.install_codex

        n_oc_inst = (install_opencode() + install_opencode_plugins()) if do_oc else 0
        n_cu_inst = (install_cursor_skills() + install_cursor_commands() + install_cursor_hooks()) if do_cu else 0
        n_cl_inst = (install_claude_skills() + install_claude_agents() + install_claude_commands() + install_claude_hooks()) if do_cl else 0
        n_cx_inst = install_codex() if do_cx else 0

        print()
        print(f"Installed to live IDEs:")
        if do_oc:
            print(f"  opencode:    {OPENCODE_CONFIG}  (agents + commands + skills + plugins)")
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
    else:
        print()
        print(f"To install to all detected IDEs, re-run with --install")
        print(f"  opencode:    {OPENCODE_CONFIG}")
        print(f"  cursor:      {CURSOR_CONFIG}")
        print(f"  claude:      {CLAUDE_CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
