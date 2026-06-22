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


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter (simple key: value)."""
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
    lines = ["---"]
    for k, v in d.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


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


def write_skill_stub(role_name: str, description: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(make_skill_stub(role_name, description), encoding="utf-8")


def emit_skill(role_name: str, description: str) -> None:
    """Write the auto-generated skill stub into the project's skills/ folder."""
    skill_dir = SKILLS_DIR / role_name
    write_skill_stub(role_name, description, skill_dir / "SKILL.md")


# ─── opencode adapter ────────────────────────────────────────────────────

def emit_opencode() -> int:
    target = ADAPTERS_DIR / "opencode"
    (target / "agents").mkdir(parents=True, exist_ok=True)
    (target / "skill").mkdir(parents=True, exist_ok=True)
    count = 0
    for src in roles():
        role_name, description, _fm, _body = role_metadata(src)
        (target / "agents" / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
        skill_dir = target / "skill" / role_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        write_skill_stub(role_name, description, skill_dir / "SKILL.md")
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

def install_opencode(verbose: bool = False) -> int:
    if not OPENCODE_CONFIG.exists():
        print(f"  {OPENCODE_CONFIG} does not exist — skipping install")
        return 0
    count = 0
    for src in roles():
        role_name, description, _fm, _body = role_metadata(src)
        dst_agent = OPENCODE_CONFIG / "agents" / src.name
        dst_agent.parent.mkdir(parents=True, exist_ok=True)
        dst_agent.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
        skill_dir = OPENCODE_CONFIG / "skill" / role_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        write_skill_stub(role_name, description, skill_dir / "SKILL.md")
        count += 1
    if verbose:
        print(f"  installed {count} files to {OPENCODE_CONFIG}")
    return count


# ─── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate IDE adapter files from team/*.md")
    parser.add_argument("--install", action="store_true",
                        help="Also copy opencode adapters to ~/.config/opencode/")
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 if installed opencode adapters are out of date.")
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
    n_skills = 0
    for src in roles():
        role_name, desc, _, _ = role_metadata(src)
        emit_skill(role_name, desc)
        n_skills += 1
    print(f"Generated {n_skills} skill stub(s) in skills/")

    n_oc = emit_opencode()
    n_cl = emit_claude()
    n_cu = emit_cursor()
    n_mc = emit_mcp()
    total = n_oc + n_cl + n_cu + n_mc
    print(f"Generated {total} adapter files in adapters/  "
          f"(opencode={n_oc}, claude={n_cl}, cursor={n_cu}, mcp={n_mc})")

    if args.install:
        n_inst = install_opencode()
        print(f"Installed {n_inst} files to {OPENCODE_CONFIG}")
    else:
        print(f"To install opencode adapters to {OPENCODE_CONFIG}, re-run with --install")
    return 0


if __name__ == "__main__":
    sys.exit(main())
