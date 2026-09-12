"""`spielos update` must preserve every owner layer while refreshing the spine.

Simulates two releases (template roots A and B built from the real
templates), a home with owner content in every user layer, and asserts the
A->B update refreshes vendored files, prunes stale vendored files, and keeps
every owner-created file — including legacy homes created before the
vendored manifest existed.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from company.__main__ import main

REAL_TEMPLATES = Path(__file__).resolve().parents[1] / "init_templates"

DEPARTMENT_SOURCE = '''"""Custom owner Department."""

WORKFLOWS = ()


class Custom:
    department_id = "custom"
    id = "custom"
    version = "1.0.0"
    description = "owner-owned department"
    workflows = WORKFLOWS
'''


def _copy_real_templates(target: Path) -> None:
    shutil.copytree(REAL_TEMPLATES, target)


class _TemplateEnv:
    """Point SPIELOS_TEMPLATE_DIR at a complete template root, verbatim."""

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self) -> Path:
        self._old = os.environ.get("SPIELOS_TEMPLATE_DIR")
        os.environ["SPIELOS_TEMPLATE_DIR"] = str(self.path)
        return self.path

    def __exit__(self, *args) -> None:
        if self._old is None:
            os.environ.pop("SPIELOS_TEMPLATE_DIR", None)
        else:
            os.environ["SPIELOS_TEMPLATE_DIR"] = self._old


def _add_owner_content(home: Path) -> None:
    """Owner-created files in every user layer, on every host and spine."""
    agents = home / ".agents" / "company"
    (agents / "departments" / "custom").mkdir(parents=True)
    (agents / "departments" / "custom" / "department.py").write_text(DEPARTMENT_SOURCE)
    (agents / "skills" / "my-skill").mkdir(parents=True)
    (agents / "skills" / "my-skill" / "SKILL.md").write_text("# My skill\n")
    (agents / "capabilities" / "browser").mkdir(parents=True)
    (agents / "capabilities" / "browser" / "run.py").write_text("print('hi')\n")
    (agents / "connections" / "registry.py").write_text("# owner registry\n")
    (agents / "strategy").mkdir(parents=True, exist_ok=True)
    (agents / "strategy" / "growth.md").write_text("# Growth\n")
    (agents / "agents" / "installed").mkdir(parents=True, exist_ok=True)
    (agents / "agents" / "installed" / "worker.py").write_text("# worker\n")
    opencode = home / ".opencode"
    (opencode / "agents").mkdir(parents=True, exist_ok=True)
    (opencode / "commands").mkdir(parents=True, exist_ok=True)
    (opencode / "plugins").mkdir(parents=True, exist_ok=True)
    (opencode / "agents" / "my-agent.md").write_text("---\ndescription: mine\n---\n")
    (opencode / "commands" / "mine.md").write_text("my command\n")
    (opencode / "plugins" / "mine.ts").write_text("export default {}\n")
    (home / ".codex" / "agents").mkdir(parents=True, exist_ok=True)
    (home / ".codex" / "agents" / "custom.toml").write_text('name = "custom"\n')
    claude = home / ".claude"
    (claude / "agents").mkdir(parents=True, exist_ok=True)
    (claude / "commands").mkdir(parents=True, exist_ok=True)
    (claude / "agents" / "my-claude-agent.md").write_text(
        "---\nname: my-claude-agent\ndescription: mine\n---\n")
    (claude / "commands" / "mine.md").write_text("my command\n")


def _owner_config(home: Path) -> None:
    """Owner-edited opencode.json and AGENTS.md with legacy keys."""
    (home / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "default_agent": "director",
        "plugin": ["./.opencode/plugins/spielos-notifications.ts"],
        "model": "custom-owner-model",
        "mcp": {"servers": {"mine": {"type": "local"}}},
    }, indent=2) + "\n")
    agents_md = home / "AGENTS.md"
    agents_md.write_text(
        agents_md.read_text().rstrip("\n")
        + "\n\n## My custom rules\n\n- never delete this line\n")


OWNER_CLAUDE_SETTINGS = {
    "model": "opus",
    "permissions": {"allow": ["Bash(npm run test:*)"],
                    "deny": ["Read(./.env)"]},
    "env": {"MY_KEY": "owner"},
    "hooks": {"PreToolUse": [
        {"matcher": "Write|Edit", "hooks": [
            {"type": "command", "command": "npx prettier --write",
             "timeout": 5}]},
    ]},
}


def _owner_claude_settings(home: Path) -> None:
    """Owner-edited .claude/settings.json: permissions, env, model, and one
    hook of the owner's own, all of which an update must preserve."""
    (home / ".claude" / "settings.json").write_text(
        json.dumps(OWNER_CLAUDE_SETTINGS, indent=2) + "\n")


def _claude_hook_commands(home: Path) -> dict[str, list[str]]:
    settings = json.loads(
        (home / ".claude" / "settings.json").read_text())
    hooks = settings.get("hooks") or {}
    commands: dict[str, list[str]] = {}
    for event, groups in hooks.items():
        entries = [entry.get("command") for group in groups
                   if isinstance(group, dict)
                   for entry in (group.get("hooks") or [])
                   if isinstance(entry, dict)]
        commands[event] = [command for command in entries if command]
    return commands


class UpdatePreservationTests(unittest.TestCase):
    def _run_company(self, home: Path, *command: str) -> dict:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-B", "-m", "company", *command], cwd=home,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                 "PYTHONPATH": str(home / ".agents")},
            capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def _init(self, templates: Path, home: Path) -> None:
        with _TemplateEnv(templates) as _:
            self.assertEqual(0, main(["init", "--dir", str(home),
                                      "-y", "--json"]))

    def _update(self, templates: Path, home: Path) -> None:
        with _TemplateEnv(templates) as _:
            self.assertEqual(0, main(["update", "--dir", str(home),
                                      "--json"]))

    def test_update_preserves_owner_layers_and_refreshes_spine(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release_a, release_b = base / "a", base / "b"

            # Release A: like the current release plus one extra vendored
            # spine module that release B will stop shipping.
            _copy_real_templates(release_a)
            (release_a / "agents" / "company" / "legacy_module.py").write_text(
                "# removed in release B\n")
            # Release B: adds a new vendored spine file and changes one
            # vendored host file on every host adapter.
            _copy_real_templates(release_b)
            (release_b / "agents" / "company" / "new_module.py").write_text(
                "# added in release B\n")
            marker = release_b / "hosts" / "opencode" / "agents" / "director.md"
            marker.write_text(marker.read_text() + "\n<!-- release B -->\n")
            claude_marker = release_b / "hosts" / "claude" / "agents" / "director.md"
            claude_marker.write_text(
                claude_marker.read_text() + "\n<!-- release B claude -->\n")

            self._init(release_a, home)
            _add_owner_content(home)
            _owner_config(home)
            _owner_claude_settings(home)
            # Owner notes below the CLAUDE.md import survive updates.
            (home / "CLAUDE.md").write_text(
                "@AGENTS.md\n\n# My Claude notes\n- keep this line\n")
            # Operational state must survive updates untouched.
            state = home / ".spielos" / "state" / "company.sqlite"
            self._run_company(home, "status")
            self.assertTrue(state.is_file())

            self._update(release_b, home)

            agents = home / ".agents" / "company"
            # Owner content survives in every user layer.
            for rel in (
                "departments/custom/department.py",
                "skills/my-skill/SKILL.md",
                "capabilities/browser/run.py",
                "connections/registry.py",
                "strategy/growth.md",
                "agents/installed/worker.py",
            ):
                self.assertTrue((agents / rel).is_file(), rel)
            self.assertEqual(DEPARTMENT_SOURCE,
                             (agents / "departments" / "custom" / "department.py").read_text())
            # Owner host files survive.
            for rel in ("agents/my-agent.md", "commands/mine.md", "plugins/mine.ts"):
                self.assertTrue((home / ".opencode" / rel).is_file(), rel)
            self.assertTrue((home / ".codex" / "agents" / "custom.toml").is_file())
            for rel in ("agents/my-claude-agent.md", "commands/mine.md"):
                self.assertTrue((home / ".claude" / rel).is_file(), rel)
            # Vendored files refresh: new module appears, changed director.md
            # content lands on every host, stale vendored file is pruned.
            self.assertTrue((agents / "new_module.py").is_file())
            self.assertFalse((agents / "legacy_module.py").exists())
            self.assertIn("<!-- release B -->",
                          (home / ".opencode" / "agents" / "director.md").read_text())
            self.assertIn("<!-- release B claude -->",
                          (home / ".claude" / "agents" / "director.md").read_text())
            # The owner's CLAUDE.md notes survive (only the release writes
            # it when absent; owner edits are preserved like AGENTS.md).
            self.assertIn("keep this line", (home / "CLAUDE.md").read_text())
            # The manifest now tracks release B's vendored set.
            manifest = json.loads(
                (home / ".spielos" / "vendored.json").read_text())
            self.assertIn("company/runtime/bootstrap.py",
                          manifest["files"]["agents"])
            self.assertIn("company/new_module.py",
                          manifest["files"]["agents"])
            self.assertNotIn("company/legacy_module.py",
                             manifest["files"]["agents"])
            self.assertIn("plugins/spielos-notifications.ts",
                          manifest["files"]["opencode"])
            self.assertIn("hooks.json", manifest["files"]["codex"])
            self.assertIn("hooks/spielos-context.py",
                          manifest["files"]["claude"])
            self.assertNotIn("CLAUDE.md", manifest["files"]["claude"])
            # Owner config is fixed up, never clobbered.
            config = json.loads((home / "opencode.json").read_text())
            self.assertEqual("custom-owner-model", config["model"])
            self.assertEqual({"servers": {"mine": {"type": "local"}}},
                             config["mcp"])
            self.assertNotIn("plugin", config)
            self.assertEqual("director", config["default_agent"])
            # Claude settings stay the owner's: permissions, env, and model
            # untouched; each SpielOS hook wired exactly once; the owner's
            # own PreToolUse hook preserved; settings.local.json never
            # written.
            settings = json.loads(
                (home / ".claude" / "settings.json").read_text())
            self.assertEqual(OWNER_CLAUDE_SETTINGS["permissions"],
                             settings["permissions"])
            self.assertEqual(OWNER_CLAUDE_SETTINGS["env"], settings["env"])
            self.assertEqual("opus", settings["model"])
            self.assertEqual(
                ["npx prettier --write"],
                [entry["command"]
                 for group in settings["hooks"]["PreToolUse"]
                 for entry in group["hooks"]])
            commands = _claude_hook_commands(home)
            context = [command for command in
                       commands["UserPromptSubmit"] + commands["SessionStart"]
                       if "spielos-context.py" in command]
            attention = [command for command in commands["Stop"]
                         if "spielos-attention.py" in command]
            self.assertEqual(2, len(context),
                             "context hook wired once per event, not duplicated")
            self.assertEqual(1, len(attention))
            self.assertFalse(
                (home / ".claude" / "settings.local.json").exists())
            # Owner AGENTS.md rules survive and gain the layout contract.
            agents_md = (home / "AGENTS.md").read_text()
            self.assertIn("never delete this line", agents_md)
            self.assertIn("spielos-layout-contract", agents_md)
            # State survives.
            self.assertTrue(state.is_file())

    def test_pre_manifest_home_never_loses_user_layer_files(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)

            self._init(release, home)
            # Legacy home: no manifest at all.
            (home / ".spielos" / "vendored.json").unlink()
            _add_owner_content(home)
            # A user file whose name looks like stale vendored residue.
            (home / ".agents" / "company" / "skills" / "legacy").mkdir()
            (home / ".agents" / "company" / "skills" / "legacy" / "SKILL.md") \
                .write_text("kept\n")

            self._update(release, home)

            agents = home / ".agents" / "company"
            self.assertTrue((agents / "skills" / "legacy" / "SKILL.md").is_file())
            for rel in (
                "departments/custom/department.py",
                "skills/my-skill/SKILL.md",
                "capabilities/browser/run.py",
                "connections/registry.py",
                "strategy/growth.md",
                "agents/installed/worker.py",
            ):
                self.assertTrue((agents / rel).is_file(), rel)
            self.assertTrue((home / ".opencode" / "plugins" / "mine.ts").is_file())

    def test_pre_manifest_home_refreshes_shipped_adapters_keeps_owner_files(self):
        """Pre-manifest homes: shipped adapters refresh, owner files stay.

        Homes created before the vendored manifest existed carry no history
        to consult, so `update` must still refresh every host-adapter file
        the current release itself ships (Director prompts, Codex and
        Claude Code hooks, the notifications plugin) to the new release
        bytes while keeping every owner file at a path the release does not
        ship — including .codex and .claude paths outside the classic user
        layers.
        """
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)

            self._init(release, home)
            # Legacy home: no manifest at all.
            (home / ".spielos" / "vendored.json").unlink()

            # Owner content at paths the release does not ship.
            owner = {
                ".codex/agents/custom.toml": 'name = "custom"\n',
                ".codex/agents/other.toml": 'name = "other"\n',
                ".codex/workflow/scout.md": "# scout\n",
                ".opencode/agents/my-agent.md": "---\ndescription: mine\n---\n",
                ".claude/agents/my-claude-agent.md":
                    "---\nname: my-claude-agent\ndescription: mine\n---\n",
                ".claude/commands/mine.md": "my command\n",
                ".claude/rules/notes.md": "# owner rule\n",
            }
            for rel, content in owner.items():
                path = home / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            # Diverged old-generation adapter content at template paths.
            stale = {
                ".codex/agents/director.toml": "# OLD director\n",
                ".codex/hooks.json": '{\n  "old": true\n}\n',
                ".codex/hooks/spielos-context.py": "# OLD hook\n",
                ".opencode/agents/director.md": "OLD director\n",
                ".claude/agents/director.md": "OLD claude director\n",
                ".claude/hooks/spielos-context.py": "# OLD claude hook\n",
                ".claude/settings-fragment.json": '{\n  "old": true\n}\n',
            }
            for rel, content in stale.items():
                (home / rel).write_text(content)

            self._update(release, home)

            # Every template-path adapter equals the release bytes.
            shipped = {
                ".codex/agents/director.toml":
                    release / "hosts" / "codex" / "agents" / "director.toml",
                ".codex/hooks.json":
                    release / "hosts" / "codex" / "hooks.json",
                ".codex/hooks/spielos-context.py":
                    release / "hosts" / "codex" / "hooks" / "spielos-context.py",
                ".codex/hooks/spielos-attention.py":
                    release / "hosts" / "codex" / "hooks" / "spielos-attention.py",
                ".opencode/agents/director.md":
                    release / "hosts" / "opencode" / "agents" / "director.md",
                ".opencode/plugins/spielos-notifications.ts":
                    release / "hosts" / "opencode"
                    / "plugins" / "spielos-notifications.ts",
                ".claude/agents/director.md":
                    release / "hosts" / "claude" / "agents" / "director.md",
                ".claude/commands/status.md":
                    release / "hosts" / "claude" / "commands" / "status.md",
                ".claude/hooks/spielos-context.py":
                    release / "hosts" / "claude" / "hooks" / "spielos-context.py",
                ".claude/hooks/spielos-attention.py":
                    release / "hosts" / "claude" / "hooks" / "spielos-attention.py",
                ".claude/settings-fragment.json":
                    release / "hosts" / "claude" / "settings-fragment.json",
            }
            for rel, source in shipped.items():
                self.assertEqual(
                    source.read_text(), (home / rel).read_text(),
                    f"{rel} must equal the release template bytes")
            # Every non-template owner file survives byte-identical.
            for rel, content in owner.items():
                self.assertTrue((home / rel).is_file(), rel)
                self.assertEqual(content, (home / rel).read_text(), rel)
            # settings.json is merged, never refreshed to release bytes:
            # only the SpielOS hooks land in it.
            settings = json.loads(
                (home / ".claude" / "settings.json").read_text())
            self.assertEqual(
                {"hooks"}, set(settings),
                "the release must not own any settings.json key but hooks")
            # The update restores the manifest, so the next update prunes
            # residue the current release no longer ships.
            self.assertTrue((home / ".spielos" / "vendored.json").is_file())

    def test_manifest_home_preserves_codex_owner_files(self):
        """3.1 (audit ledger): a manifest home must never delete owner
        files in .codex/ outside the shipped adapter set.

        Manifest knowledge narrows what update may touch below the
        shipped set; it never widens it above the prefix list. Owner
        content at any host-tree path the release does not ship survives
        the update, while vendored refresh and stale prune still work.
        """
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)

            # The home has a manifest (fresh init wrote one).
            self.assertTrue((home / ".spielos" / "vendored.json").is_file())
            # Owner files in .codex/ outside the shipped adapter paths.
            owner = {
                ".codex/README.md": "# owner notes\n",
                ".codex/workflow/owner.md": "# workflow\n",
                ".codex/agents/custom.toml": 'name = "custom"\n',
            }
            for rel, content in owner.items():
                path = home / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

            self._update(release, home)

            for rel, content in owner.items():
                path = home / rel
                self.assertTrue(path.is_file(), f"{rel} was deleted by update")
                self.assertEqual(content, path.read_text(), rel)
            # Vendored refresh still works: the shipped adapter refreshes
            # to the release bytes (byte-identical here, but written).
            self.assertTrue((home / ".codex" / "hooks.json").is_file())
            # Stale vendored prune still works: a manifest-tracked path
            # the next release stops shipping is pruned.
            stale = release / "hosts" / "codex" / "hooks" / "old-hook.py"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("# vendored in this release only\n")
            self._update(release, home)
            self.assertTrue((home / ".codex" / "hooks" / "old-hook.py").is_file())
            stale.unlink()
            self._update(release, home)
            self.assertFalse((home / ".codex" / "hooks" / "old-hook.py").exists(),
                             "stale vendored file must prune on update")
            # Owner files still survive the prune run.
            self.assertTrue((home / ".codex" / "README.md").is_file())

    def test_manifest_home_preserves_claude_owner_files(self):
        """A manifest home must never delete owner files in .claude/ outside
        the shipped adapter set, exactly as it preserves .codex/."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)

            self.assertTrue((home / ".spielos" / "vendored.json").is_file())
            owner = {
                ".claude/rules/owner.md": "# rule\n",
                ".claude/agents/custom.md":
                    "---\nname: custom\ndescription: mine\n---\n",
                ".claude/skills/my-skill/SKILL.md": "# skill\n",
                ".claude/settings.local.json": '{"permissions": {}}',
            }
            for rel, content in owner.items():
                path = home / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

            self._update(release, home)

            for rel, content in owner.items():
                path = home / rel
                self.assertTrue(path.is_file(), f"{rel} was deleted by update")
                self.assertEqual(content, path.read_text(), rel)
            # Vendored refresh still works and stale vendored prune still
            # works below the shipped set.
            self.assertTrue(
                (home / ".claude" / "settings-fragment.json").is_file())
            stale = release / "hosts" / "claude" / "hooks" / "old-hook.py"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("# vendored in this release only\n")
            self._update(release, home)
            self.assertTrue((home / ".claude" / "hooks" / "old-hook.py").is_file())
            stale.unlink()
            self._update(release, home)
            self.assertFalse((home / ".claude" / "hooks" / "old-hook.py").exists(),
                             "stale vendored claude file must prune on update")
            # Owner files still survive the prune run.
            self.assertTrue((home / ".claude" / "rules" / "owner.md").is_file())

    def test_claude_settings_merge_is_append_only_and_idempotent(self):
        """D: the Claude hook merge never disturbs owner settings.

        Existing owner permissions, env, and model keys are preserved
        byte-for-byte in meaning, the owner's own hooks survive untouched,
        each SpielOS hook is added exactly once across repeated updates,
        a release that changes its own command replaces only its own
        earlier wiring, and settings.local.json is never written.
        """
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)
            _owner_claude_settings(home)

            for _ in range(2):  # two updates: the merge must be idempotent
                self._update(release, home)

            settings = json.loads(
                (home / ".claude" / "settings.json").read_text())
            # Owner keys untouched.
            self.assertEqual(OWNER_CLAUDE_SETTINGS["permissions"],
                             settings["permissions"])
            self.assertEqual(OWNER_CLAUDE_SETTINGS["env"], settings["env"])
            self.assertEqual(OWNER_CLAUDE_SETTINGS["model"], settings["model"])
            # The owner's own hook survives, unchanged.
            self.assertIn("PreToolUse", settings["hooks"])
            self.assertEqual(
                [{"matcher": "Write|Edit",
                  "hooks": [{"type": "command",
                             "command": "npx prettier --write",
                             "timeout": 5}]}],
                settings["hooks"]["PreToolUse"])
            # SpielOS hooks wired exactly once each.
            commands = _claude_hook_commands(home)
            self.assertEqual(1, len([c for c in commands["UserPromptSubmit"]
                                     if "spielos-context.py" in c]))
            self.assertEqual(1, len([c for c in commands["SessionStart"]
                                     if "spielos-context.py" in c]))
            self.assertEqual(1, len([c for c in commands["Stop"]
                                     if "spielos-attention.py" in c]))
            self.assertFalse(
                (home / ".claude" / "settings.local.json").exists())

            # A release that changes its own hook command replaces only its
            # own earlier wiring — no duplicate, no owner entry touched.
            fragment = release / "hosts" / "claude" / "settings-fragment.json"
            fragment.write_text(fragment.read_text().replace(
                '"timeout": 10', '"timeout": 15'))
            self._update(release, home)
            settings = json.loads(
                (home / ".claude" / "settings.json").read_text())
            commands = _claude_hook_commands(home)
            context = [c for c in commands["UserPromptSubmit"]
                       if "spielos-context.py" in c]
            self.assertEqual(1, len(context))
            entries = [entry for group in
                       settings["hooks"]["UserPromptSubmit"]
                       for entry in group["hooks"]
                       if "spielos-context.py" in entry.get("command", "")]
            self.assertEqual(15, entries[0]["timeout"])
            self.assertIn("PreToolUse", settings["hooks"])
            self.assertEqual("opus", settings["model"])

    def test_claude_settings_merge_never_rewrites_unparseable_owner_file(self):
        """An owner's hand-broken settings.json is left exactly as it is."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)
            broken = "{not json at all"
            (home / ".claude" / "settings.json").write_text(broken)
            self._update(release, home)
            self.assertEqual(
                broken,
                (home / ".claude" / "settings.json").read_text(),
                "unparseable owner settings must never be rewritten")

    def test_claude_settings_merge_leaves_owner_shaped_hooks_alone(self):
        """Owner-shaped hooks values and foreign-tree hook commands are
        owner content: the merge never replaces them, and a hook command
        that mentions a SpielOS script under a different tree (for
        example the Codex adapter's) is never claimed as ours."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)
            owner = {
                "hooks": {
                    "UserPromptSubmit": {"owner": "shaped"},
                    "Stop": [{"hooks": [{"type": "command",
                                         "command": "python3 .codex/hooks/spielos-attention.py"}]}],
                },
            }
            (home / ".claude" / "settings.json").write_text(
                json.dumps(owner, indent=2) + "\n")
            self._update(release, home)
            settings = json.loads(
                (home / ".claude" / "settings.json").read_text())
            # The owner-shaped event value survives untouched.
            self.assertEqual({"owner": "shaped"},
                             settings["hooks"]["UserPromptSubmit"])
            # The foreign-tree command (a Codex path) is still there and
            # was never rewritten or removed.
            self.assertIn(
                "python3 .codex/hooks/spielos-attention.py",
                settings["hooks"]["Stop"][0]["hooks"][0]["command"])
            # Nothing of ours was added on top of owner-shaped content.
            self.assertNotIn("SessionStart", settings["hooks"])

    def test_fresh_home_without_claude_settings_gets_hooks_only(self):
        """A fresh home with no prior .claude/settings.json gets exactly
        the SpielOS hook wiring and nothing else."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)
            settings = json.loads(
                (home / ".claude" / "settings.json").read_text())
            self.assertEqual({"hooks"}, set(settings))
            commands = _claude_hook_commands(home)
            self.assertEqual(
                {"SessionStart", "UserPromptSubmit", "Stop"},
                set(commands))

    def test_fresh_init_writes_manifest_and_canonical_config(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            home = base / "home"
            release = base / "release"
            _copy_real_templates(release)
            self._init(release, home)
            manifest = json.loads(
                (home / ".spielos" / "vendored.json").read_text())
            self.assertIn("company/runtime/bootstrap.py",
                          manifest["files"]["agents"])
            self.assertIn("plugins/spielos-notifications.ts",
                          manifest["files"]["opencode"])
            self.assertIn("hooks.json", manifest["files"]["codex"])
            self.assertIn("hooks/spielos-context.py",
                          manifest["files"]["claude"])
            self.assertIn("settings-fragment.json",
                          manifest["files"]["claude"])
            self.assertNotIn("CLAUDE.md", manifest["files"]["claude"],
                             "the bridge ships at the home root, not in .claude")
            config = json.loads((home / "opencode.json").read_text())
            self.assertEqual({"$schema": "https://opencode.ai/config.json",
                             "default_agent": "director"}, config)

    def test_real_templates_update_end_to_end(self):
        """The shipped release updating its own fresh home keeps owner files."""
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            self.assertEqual(0, main(["init", "--dir", str(home),
                                      "-y", "--json"]))
            _add_owner_content(home)
            _owner_config(home)
            self.assertEqual(0, main(["update", "--dir", str(home),
                                      "--json"]))
            agents = home / ".agents" / "company"
            self.assertTrue((agents / "departments" / "custom" / "department.py").is_file())
            self.assertTrue((agents / "skills" / "my-skill" / "SKILL.md").is_file())
            self.assertTrue((agents / "capabilities" / "browser" / "run.py").is_file())
            self.assertTrue((agents / "connections" / "registry.py").is_file())
            self.assertTrue((agents / "strategy" / "growth.md").is_file())
            self.assertTrue((agents / "agents" / "installed" / "worker.py").is_file())
            self.assertTrue((home / ".opencode" / "plugins" / "mine.ts").is_file())
            config = json.loads((home / "opencode.json").read_text())
            self.assertEqual("custom-owner-model", config["model"])
            self.assertNotIn("plugin", config)


if __name__ == "__main__":
    unittest.main()
