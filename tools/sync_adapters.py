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


def templated_text(text: str) -> str:
    """Replace `{vault_root}` placeholders with the absolute vault path.

    This is the bridge between the canonical team/*.md (which has
    `{vault_root}` in the frontmatter and body) and the installed copy
    (which has the absolute path baked in). The LLM running the MD subagent
    gets the absolute path, so it never gets confused by cwd.

    Called by emit_*() and install_*() for every role file.
    """
    return text.replace("{vault_root}", str(VAULT))


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


def build_command_md(description: str, body: str) -> str:
    """Build a slash-command markdown file from a description + body.

    Single source of truth for how a slash command is rendered. Used by
    both the emit_*() and install_*() paths so the adapter/ folder and
    the live IDE config stay in sync byte-for-byte.
    """
    import yaml
    clean = {"description": description}
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
    """Return sorted list of canonical SUBAGENT role files (excluding README + commands).

    Subagents are: md, researcher, strategist, copywriter, editor, designer, publisher, analyst.
    Commands (like post.md) are NOT subagents — they go in commands/, not agents/.
    """
    return sorted(
        p for p in TEAM_DIR.glob("*.md")
        if p.name not in ("README.md", "post.md")
    )


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
            build_command_md(description, body),
            encoding="utf-8",
        )
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
            build_command_md(description, body),
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
        out = build_command_md(description, templated_text(body))
        (target / src.name).write_text(out, encoding="utf-8")
        count += 1
    # Plus post.md as /post (one-line dispatcher to @md).
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        out = build_command_md(description, body)
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
        # Write the canonical SKILL.md verbatim — the parser reads
        # `name:` + `description:` from frontmatter, the rest is body.
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
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
        # Write the canonical SKILL.md verbatim.
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
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
            clean_fm["vault_root"] = str(VAULT)
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
        (target / src.name).write_text(build_command_md(description, body), encoding="utf-8")
        count += 1
    if verbose:
        print(f"  [claude] installed {count} commands to {target}")
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
        (target / src.name).write_text(build_command_md(description, templated_text(body)), encoding="utf-8")
        count += 1
    for src in commands():
        role_name, description, _fm, body = role_metadata(src)
        (target / src.name).write_text(build_command_md(description, body), encoding="utf-8")
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
        dst_cmd.write_text(build_command_md(description, body), encoding="utf-8")
        count += 1
    # Skills: skills/*/SKILL.md
    for src in skills():
        skill_name, _desc, _fm, _body = skill_metadata(src)
        skill_dir = OPENCODE_CONFIG / "skill" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
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
        (skill_dir / "SKILL.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
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
    return out


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
                build_command_md(description, body)
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
                build_command_md(description, templated_text(body))
            )
        for src in commands():
            role_name, description, _fm, body = role_metadata(src)
            expected[CURSOR_CONFIG / "commands" / src.name] = (
                build_command_md(description, body)
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
            expected[CLAUDE_CONFIG / "agents" / src.name] = (
                "---\n"
                + _yaml.safe_dump(clean, sort_keys=False, allow_unicode=True).rstrip()
                + "\n---\n\n"
                + templated_text(body).lstrip()
            )
        for src in commands():
            role_name, description, _fm, body = role_metadata(src)
            expected[CLAUDE_CONFIG / "commands" / src.name] = (
                build_command_md(description, body)
            )
        for src in skills():
            skill_name, _d, _fm, _body = skill_metadata(src)
            expected[CLAUDE_CONFIG / "skills" / skill_name / "SKILL.md"] = (
                src.read_text(encoding="utf-8")
            )

    return expected


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate IDE adapter files from team/*.md")
    parser.add_argument("--install", action="store_true",
                        help="Install to all detected IDE configs "
                             "(opencode: agents + commands + skills, "
                             "Cursor: skills + commands, Claude Code: skills + agents + commands)")
    parser.add_argument("--install-opencode", action="store_true",
                        help="Install to opencode only (agents + commands + skills)")
    parser.add_argument("--install-cursor", action="store_true",
                        help="Install to Cursor only (skills + commands)")
    parser.add_argument("--install-claude", action="store_true",
                        help="Install to Claude Code only (skills + agents + commands)")
    parser.add_argument("--check", action="store_true",
                        help="Compare installed adapters against canonical "
                             "team/*.md + skills/*.md. Exit 0 if in sync, "
                             "1 if any file would be regenerated, 2 if any "
                             "files are missing entirely.")
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
    total = n_oc + n_cl + n_cu + n_mc
    print(f"Generated {total} adapter files in adapters/  "
          f"(opencode={n_oc}, claude={n_cl}, cursor={n_cu}, mcp={n_mc})")

    if args.install or args.install_opencode or args.install_cursor or args.install_claude:
        do_oc = args.install or args.install_opencode
        do_cu = args.install or args.install_cursor
        do_cl = args.install or args.install_claude

        n_oc_inst = install_opencode() if do_oc else 0
        n_cu_inst = (install_cursor_skills() + install_cursor_commands()) if do_cu else 0
        n_cl_inst = (install_claude_skills() + install_claude_agents() + install_claude_commands()) if do_cl else 0

        print()
        print(f"Installed to live IDEs:")
        if do_oc:
            print(f"  opencode:    {OPENCODE_CONFIG}  (agents + commands + skills)")
        if do_cu:
            print(f"  cursor:      {CURSOR_CONFIG}  (skills + commands)")
        if do_cl:
            print(f"  claude:      {CLAUDE_CONFIG}  (agents + skills + commands)")
    else:
        print()
        print(f"To install to all detected IDEs, re-run with --install")
        print(f"  opencode:    {OPENCODE_CONFIG}")
        print(f"  cursor:      {CURSOR_CONFIG}")
        print(f"  claude:      {CLAUDE_CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
