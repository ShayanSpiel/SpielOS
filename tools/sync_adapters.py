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
    """Return sorted list of canonical role files (excluding README)."""
    return sorted(p for p in TEAM_DIR.glob("*.md") if p.name != "README.md")


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
    """Write per-role subagents + real skills from skills/ to adapters/opencode/.

    Subagents (from team/*.md) → adapters/opencode/agents/<name>.md
    Skills (from skills/*/SKILL.md) → adapters/opencode/skill/<name>/SKILL.md
    """
    target = ADAPTERS_DIR / "opencode"
    (target / "agents").mkdir(parents=True, exist_ok=True)
    (target / "skill").mkdir(parents=True, exist_ok=True)
    count = 0
    # Subagents from team/*.md
    for src in roles():
        role_name, description, _fm, _body = role_metadata(src)
        (target / "agents" / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    # Real skills from skills/*/SKILL.md
    for src in skills():
        skill_name, description, _fm, _body = skill_metadata(src)
        skill_dir = target / "skill" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    return count


# ─── Claude Code adapter ─────────────────────────────────────────────────

def emit_claude() -> int:
    target = ADAPTERS_DIR / "claude" / "agents"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in roles():
        (target / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    return count


# ─── Cursor adapter ──────────────────────────────────────────────────────

def emit_cursor() -> int:
    target = ADAPTERS_DIR / "cursor" / "commands"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in roles():
        role_name, description, _fm, body = role_metadata(src)
        out = make_frontmatter({"description": description}) + body + "\n"
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


# ─── Live install ────────────────────────────────────────────────────────

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


def install_opencode_commands(verbose: bool = False) -> int:
    """Install slash commands at ~/.config/opencode/commands/<name>.md.

    Each file becomes a /name slash command in opencode. The body delegates
    to the subagent (if available) or falls back to the spiel CLI.
    """
    if not detect_ide(OPENCODE_CONFIG, "opencode"):
        return 0
    target = OPENCODE_CONFIG / "commands"
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in roles():
        role_name, description, _fm, body = role_metadata(src)
        # If body lacks a clear "delegate to subagent X" instruction, append one
        if "delegate" not in body.lower() and "subagent" not in body.lower():
            suffix = (

                "\n\n## Delegation\n\n"
                f"When this command fires, you ARE the `{role_name}` role. "
                "Do not explain, do not ask clarifying questions, do not offer a menu. "
                "Take the role's full body above as your system prompt and run the user's request.\n"
            )
            body = body.rstrip() + suffix
        (target / src.name).write_text(
            make_slash_command(role_name, description, body),
            encoding="utf-8",
        )
        count += 1
    if verbose:
        print(f"  [opencode] installed {count} slash commands to {target}")
    return count


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
        skill_name, description, _fm, body = skill_metadata(src)
        skill_dir = target / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = (
            f"---\nname: {skill_name}\ndescription: {description}\n---\n\n"
            + body.lstrip()
        )
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
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
        skill_name, description, _fm, body = skill_metadata(src)
        skill_dir = target / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = (
            f"---\nname: {skill_name}\ndescription: {description}\n---\n\n"
            + body.lstrip()
        )
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
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
        out = "---\n" + yaml.safe_dump(clean_fm, sort_keys=False, allow_unicode=True).rstrip() + "\n---\n\n" + body.lstrip()
        (target / src.name).write_text(out, encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [claude] installed {count} agents to {target}")
    return count


def install_opencode(verbose: bool = False) -> int:
    """Install subagents (from team/*.md) + real skills (from skills/*/SKILL.md)
    to ~/.config/opencode/. Subagents go in agents/, skills go in skill/.
    """
    if not OPENCODE_CONFIG.exists():
        print(f"  {OPENCODE_CONFIG} does not exist — skipping install")
        return 0
    count = 0
    for src in roles():
        dst_agent = OPENCODE_CONFIG / "agents" / src.name
        dst_agent.parent.mkdir(parents=True, exist_ok=True)
        dst_agent.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    for src in skills():
        skill_name, _desc, _fm, _body = skill_metadata(src)
        skill_dir = OPENCODE_CONFIG / "skill" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  installed {count} files (subagents + skills) to {OPENCODE_CONFIG}")
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
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    return count


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate IDE adapter files from team/*.md")
    parser.add_argument("--install", action="store_true",
                        help="Install to all detected IDE configs "
                             "(opencode: agents + commands, Cursor: skills, Claude Code: skills + agents)")
    parser.add_argument("--install-opencode", action="store_true",
                        help="Install to opencode only (agents + commands + skills)")
    parser.add_argument("--install-cursor", action="store_true",
                        help="Install to Cursor only (skills)")
    parser.add_argument("--install-claude", action="store_true",
                        help="Install to Claude Code only (skills + agents)")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if installed adapters are out of date.")
    parser.add_argument("--show", metavar="IDE", choices=["opencode", "claude", "cursor", "mcp"],
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

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    # Real skills live in skills/*/SKILL.md (user-managed, not auto-generated)
    n_skills = sum(1 for _ in SKILLS_DIR.glob("*/SKILL.md"))
    print(f"Found {n_skills} canonical skill(s) in skills/")

    n_oc = emit_opencode()
    n_cl = emit_claude()
    n_cu = emit_cursor()
    n_mc = emit_mcp()
    total = n_oc + n_cl + n_cu + n_mc
    print(f"Generated {total} adapter files in adapters/  "
          f"(opencode={n_oc}, claude={n_cl}, cursor={n_cu}, mcp={n_mc})")

    if args.install or args.install_opencode or args.install_cursor or args.install_claude:
        do_oc = args.install or args.install_opencode
        do_cu = args.install or args.install_cursor
        do_cl = args.install or args.install_claude

        n_oc_inst = 0
        n_cu_inst = 0
        n_cl_inst = 0
        if do_oc:
            n_oc_inst = install_opencode() + install_opencode_commands()
        if do_cu:
            n_cu_inst = install_cursor_skills()
        if do_cl:
            n_cl_inst = install_claude_skills() + install_claude_agents()

        print()
        print(f"Installed to live IDEs:")
        if do_oc:
            print(f"  opencode:    {OPENCODE_CONFIG}  (agents + commands)")
        if do_cu:
            print(f"  cursor:      {CURSOR_CONFIG / 'skills'}")
        if do_cl:
            print(f"  claude:      {CLAUDE_CONFIG}  (agents + skills)")
    else:
        print()
        print(f"To install to all detected IDEs, re-run with --install")
        print(f"  opencode:    {OPENCODE_CONFIG}")
        print(f"  cursor:      {CURSOR_CONFIG / 'skills'}")
        print(f"  claude:      {CLAUDE_CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
