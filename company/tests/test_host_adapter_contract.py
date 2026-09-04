"""Host adapter contracts: the OpenCode plugin must load under the V2 loader,
the Codex hooks must inject context and surface attention, and the repo's
live adapters must stay byte-identical with the shipped templates."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMPLATE_HOSTS = REPO / "company" / "init_templates" / "hosts"
PLUGIN = TEMPLATE_HOSTS / "opencode" / "plugins" / "spielos-notifications.ts"


class OpenCodePluginContractTests(unittest.TestCase):
    def test_plugin_uses_the_v2_default_export_contract(self):
        """The loader requires `export default { id, setup }`.

        The 1.x named-export shape fails schema validation with
        "Missing key at [\\"default\\"]" and the host degrades silently to
        a coding agent with no company state.
        """
        source = PLUGIN.read_text()
        self.assertIn('id: "spielos-notifications"', source)
        self.assertIn("export default plugin", source)
        self.assertIn("const setup = async (ctx", source)

    def test_plugin_has_no_runtime_imports(self):
        """A fresh home has no node_modules; only type-stripped imports pass."""
        for line in PLUGIN.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") and "import type" not in stripped:
                if "from" in stripped or "require(" in stripped:
                    self.fail(f"runtime import in plugin: {stripped}")

    def test_plugin_resolves_the_sessions_home_not_the_servers(self):
        """A server may be started in a different folder than the session it
        serves; the adapter must find the session's own home. The 2026-09-04
        failure ("can't load context") was exactly a server started in
        ShayanSpiel.Github.io serving SpielOS1 sessions with no injection.
        """
        source = PLUGIN.read_text()
        self.assertIn("sessionDirectoryFrom", source)
        self.assertIn("homeCandidates", source)
        self.assertIn(".agents/company/__main__.py", source)
        self.assertIn("SPIELOS_HOME", source)
        # Every host generation must keep loading the same file.
        self.assertIn("export { SpielOSContext, setup }", source)
        self.assertIn('hooks["experimental.chat.system.transform"]', source)

    def test_plugin_injects_context_and_surfaces_attention(self):
        source = PLUGIN.read_text()
        self.assertIn('ctx.session.hook("context"', source)
        self.assertIn('"--owner", "director"', source)
        self.assertIn("session.idle", source)
        self.assertIn('"notifications", "list"', source)
        self.assertIn('"notifications", "ack"', source)
        # Injection failure must be reported to the model, not swallowed.
        self.assertIn("injection failed", source)

    def test_repo_plugin_is_byte_identical_with_template(self):
        live = REPO / ".opencode" / "plugins" / "spielos-notifications.ts"
        self.assertEqual(live.read_bytes(), PLUGIN.read_bytes())

    def test_repo_opencode_json_has_no_file_path_plugin_entry(self):
        config = json.loads((REPO / "opencode.json").read_text())
        self.assertNotIn("plugin", config)
        self.assertNotIn("plugins", config)
        self.assertEqual("director", config["default_agent"])


class CodexHostContractTests(unittest.TestCase):
    def test_hooks_json_registers_context_and_attention(self):
        config = json.loads(
            (TEMPLATE_HOSTS / "codex" / "hooks.json").read_text())
        hooks = config["hooks"]
        self.assertIn("UserPromptSubmit", hooks)
        self.assertEqual(
            "compact", hooks["SessionStart"][0]["matcher"])
        self.assertIn("Stop", hooks)
        commands = [entry["command"]
                    for group in hooks.values()
                    for item in group for entry in item["hooks"]]
        for command in commands:
            self.assertTrue(command.startswith("python3 "),
                            f"must use PATH python3 (>=3.11), not /usr/bin/python3 (3.9): {command}")

    def test_hook_scripts_anchor_the_home_from_their_own_location(self):
        for name in ("spielos-context.py", "spielos-attention.py"):
            source = (TEMPLATE_HOSTS / "codex" / "hooks" / name).read_text()
            self.assertIn("Path(__file__).resolve().parents[2]", source)

    def test_hook_scripts_compile(self):
        for name in ("spielos-context.py", "spielos-attention.py"):
            path = TEMPLATE_HOSTS / "codex" / "hooks" / name
            compile(path.read_text(), str(path), "exec")

    def test_attention_hook_filters_reportable_kinds(self):
        source = (TEMPLATE_HOSTS / "codex" / "hooks" / "spielos-attention.py").read_text()
        self.assertIn('REPORTABLE = {"owner_input_required"}', source)
        self.assertIn("systemMessage", source)

    def test_director_toml_carries_the_full_contract(self):
        source = (TEMPLATE_HOSTS / "codex" / "agents" / "director.toml").read_text()
        flat = " ".join(source.split())
        for marker in (
            "Layout contract (never break)",
            "company layout",
            "host injection failed",
            "system-improvement Goal",
            "Never invent folders or files outside these layers",
            "PYTHONPATH=.agents",
        ):
            self.assertIn(marker, flat)

    def test_repo_codex_tree_is_byte_identical_with_template(self):
        live = REPO / ".codex"
        for template_file in sorted((TEMPLATE_HOSTS / "codex").rglob("*")):
            if not template_file.is_file():
                continue
            relative = template_file.relative_to(TEMPLATE_HOSTS / "codex")
            live_file = live / relative
            self.assertTrue(live_file.is_file(), f"missing {relative}")
            self.assertEqual(template_file.read_bytes(), live_file.read_bytes(),
                             f"diverged: {relative}")


class HomeShippingTests(unittest.TestCase):
    """Fresh homes must receive the full Director contract on both hosts."""

    def setUp(self):
        import os
        import tempfile

        import company.__main__ as entry
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "home"
        self.assertEqual(0, entry.main(["init", "--dir", str(self.home),
                                        "-y", "--json"]))
        self._entry = entry
        self._env = os.environ.get("SPIELOS_TEMPLATE_DIR")
        if self._env:
            os.environ.pop("SPIELOS_TEMPLATE_DIR", None)

    def tearDown(self):
        import os

        if self._env is not None:
            os.environ["SPIELOS_TEMPLATE_DIR"] = self._env
        self._tmp.cleanup()

    def test_opencode_home_receives_all_three_agents(self):
        agents = self.home / ".opencode" / "agents"
        for name in ("director.md", "system-improvement.md",
                     "department-runner.md"):
            self.assertTrue((agents / name).is_file(), name)
        director = (agents / "director.md").read_text()
        flat = " ".join(director.split())
        for marker in ("Layout contract (never break)",
                       "company layout",
                       "host injection failed",
                       "system-improvement agent",
                       "Never invent folders or files outside these layers"):
            self.assertIn(marker, flat)
        improvement = " ".join((agents / "system-improvement.md").read_text().split())
        self.assertIn("exact list of allowed files", improvement)

    def test_codex_home_receives_director_and_hooks(self):
        self.assertTrue((self.home / ".codex" / "agents" / "director.toml").is_file())
        self.assertTrue((self.home / ".codex" / "hooks" / "spielos-context.py").is_file())
        self.assertTrue((self.home / ".codex" / "hooks" / "spielos-attention.py").is_file())

    def test_repo_agent_definitions_match_shipped_templates(self):
        for name in ("system-improvement.md", "department-runner.md"):
            live = REPO / ".opencode" / "agents" / name
            template = TEMPLATE_HOSTS / "opencode" / "agents" / name
            self.assertEqual(live.read_bytes(), template.read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
