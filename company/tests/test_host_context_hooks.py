from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from company.runtime.bootstrap import _AGENTS_MD
from company.runtime.onboard import _next_steps


ROOT = Path(__file__).resolve().parents[2]


class HostContextHookTests(unittest.TestCase):
    def test_opencode_onboarding_selects_director_without_start_or_status_probe(self):
        steps, _ = _next_steps(
            Path("/tmp/new-company"), {"opencode": True, "codex": False},
            True, [])
        rendered = "\n".join(f"{command} {note}" for command, note in steps)
        self.assertIn("select the Director agent", rendered)
        self.assertNotIn("/start", rendered)
        self.assertNotIn("company status", rendered)
        codex_steps, _ = _next_steps(
            Path("/tmp/new-company"), {"opencode": False, "codex": True},
            True, [])
        self.assertIn("select the Director agent", "\n".join(
            f"{command} {note}" for command, note in codex_steps))
        self.assertIn("select the Director agent before chatting", _AGENTS_MD)
        self.assertIn("do not begin with a manual status", _AGENTS_MD)

    def test_codex_hooks_load_at_start_and_each_prompt(self):
        hooks = json.loads((ROOT / ".codex" / "hooks.json").read_text())
        self.assertIn("SessionStart", hooks["hooks"])
        self.assertIn("UserPromptSubmit", hooks["hooks"])
        start = hooks["hooks"]["SessionStart"][0]
        self.assertIn("compact", start["matcher"])
        command = start["hooks"][0]["command"]
        self.assertIn("spielos-context.py", command)
        adapter = (ROOT / ".codex" / "hooks" / "spielos-context.py").read_text()
        self.assertIn("readonly=True", adapter)
        self.assertIn("ContextAssembler", adapter)

    def test_opencode_injects_on_model_request_and_keeps_idle_notifications(self):
        plugin = (ROOT / ".opencode" / "plugins" / "spielos-notifications.ts").read_text()
        self.assertIn("export const SpielOSContext: Plugin", plugin)
        self.assertNotIn("PluginModule", plugin)
        self.assertNotIn("server: SpielOSContext", plugin)
        self.assertIn('"context", "--prompt"', plugin)
        self.assertIn('args.push("--boot")', plugin)
        self.assertIn('"experimental.chat.system.transform"', plugin)
        self.assertIn('PYTHONPATH: pythonPath', plugin)
        self.assertIn('`${directory}/.agents`', plugin)
        self.assertIn('event.type !== "session.idle"', plugin)
        self.assertIn("SpielOS context unavailable for this request", plugin)
        self.assertIn("synthetic: true", plugin)

        instructions = (ROOT / ".opencode" / "agents" / "director.md").read_text()
        self.assertIn("ordinary request\nfor status, priorities, progress", instructions)
        self.assertIn("projection was assembled for this exact model request", instructions)
        self.assertIn("focus or run a Goal", instructions)
        self.assertNotIn("begin with the compact `company status`", instructions)
        self.assertNotIn("asks\nfor a fresh status/audit", instructions)
        self.assertIn("company/strategy/focus.md", instructions)
        self.assertNotIn("`.agents/company/strategy/focus.md`", instructions)
        self.assertIn("company memory summary --json", instructions)
        self.assertIn("company\nmemory apply-candidate", instructions)
        self.assertIn("Never say “memory is empty”", instructions)

    @unittest.skipUnless(shutil.which("opencode"), "OpenCode is not installed")
    def test_installed_opencode_accepts_spielos_plugin_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env.update({
                "XDG_DATA_HOME": str(Path(directory) / "data"),
                "XDG_STATE_HOME": str(Path(directory) / "state"),
                "XDG_CACHE_HOME": str(Path(directory) / "cache"),
            })
            result = subprocess.run(
                ["opencode", "debug", "startup", "--print-logs", "--log-level", "INFO"],
                cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)
        combined = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, combined[-2000:])
        self.assertNotIn("failed to load plugin", "\n".join(
            line for line in combined.splitlines()
            if "spielos-notifications.ts" in line))

    @unittest.skipUnless(shutil.which("opencode"), "OpenCode is not installed")
    def test_installed_opencode_discovers_director_with_plugin_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env.update({
                "XDG_DATA_HOME": str(Path(directory) / "data"),
                "XDG_STATE_HOME": str(Path(directory) / "state"),
                "XDG_CACHE_HOME": str(Path(directory) / "cache"),
            })
            result = subprocess.run(
                ["opencode", "agent", "list"], cwd=ROOT, env=env,
                text=True, capture_output=True, timeout=30)

        combined = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, combined[-2000:])
        self.assertIn("director (primary)", combined)

    @unittest.skipUnless(shutil.which("bun"), "Bun is not installed")
    def test_opencode_adapter_executes_real_context_injection(self):
        script = r'''
import { SpielOSContext } from "./.opencode/plugins/spielos-notifications.ts"
const hooks = await SpielOSContext({
  client: { session: { prompt: async () => ({}) } },
  directory: process.cwd(),
})
await hooks["chat.message"](
  { sessionID: "acceptance" },
  { message: {}, parts: [{ type: "text", text: "what do you remember?" }] },
)
const output = { system: [] }
await hooks["experimental.chat.system.transform"](
  { sessionID: "acceptance", model: {} }, output,
)
console.log(JSON.stringify(output.system))
'''
        result = subprocess.run(
            ["bun", "-e", script], cwd=ROOT, text=True,
            capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        injected = json.loads(result.stdout)
        self.assertTrue(any("SpielOS context v2" in item for item in injected))
        self.assertTrue(any("company_change_ux_review" in item for item in injected))

    @unittest.skipUnless(shutil.which("bun"), "Bun is not installed")
    def test_opencode_adapter_routes_bare_greeting_without_state_probe(self):
        script = r'''
import { SpielOSContext } from "./.opencode/plugins/spielos-notifications.ts"
const hooks = await SpielOSContext({
  client: { session: { prompt: async () => ({}) } },
  directory: process.cwd(),
})
await hooks["chat.message"](
  { sessionID: "greeting" },
  { message: {}, parts: [{ type: "text", text: "hi" }] },
)
const output = { system: [] }
await hooks["experimental.chat.system.transform"](
  { sessionID: "greeting", model: {} }, output,
)
console.log(JSON.stringify(output.system))
'''
        result = subprocess.run(
            ["bun", "-e", script], cwd=ROOT, text=True,
            capture_output=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)
        injected = "\n".join(json.loads(result.stdout))
        self.assertIn("Request route · bare greeting", injected)
        self.assertIn("Make no tool calls", injected)
        self.assertNotIn("Company profile", injected)

    def test_director_hosts_use_injected_status_and_helpful_greeting(self):
        paths = (
            ROOT / ".codex" / "agents" / "director.toml",
            ROOT / ".opencode" / "agents" / "director.md",
            ROOT / "company" / "init_templates" / "hosts" / "codex" / "agents" / "director.toml",
            ROOT / "company" / "init_templates" / "hosts" / "opencode" / "agents" / "director.md",
        )
        for path in paths:
            instructions = path.read_text()
            self.assertIn("For a bare greeting", instructions)
            self.assertIn("contract violation", instructions)
            self.assertIn("Workflow or Department", instructions)
            self.assertIn("without running `company status` again", instructions)
            self.assertNotIn("begin with the compact company status projection", instructions)
            self.assertIn("company memory summary --json", instructions)
            self.assertIn("memory apply-candidate", instructions)
            self.assertIn("context unavailable", instructions)

        source_codex = (ROOT / ".codex" / "agents" / "director.toml").read_text()
        shipped_codex = (ROOT / "company" / "init_templates" / "hosts" /
                         "codex" / "agents" / "director.toml").read_text()
        self.assertIn("company/strategy/focus.md", source_codex)
        self.assertIn(".agents/company/strategy/focus.md", shipped_codex)

        skill = (ROOT / "company" / "skills" / "director" / "SKILL.md").read_text()
        self.assertIn("user experience", skill)
        self.assertIn("visible UI behavior", skill)
        self.assertIn("Director voice/tone", skill)

    def test_shipped_host_hooks_match_source_checkout_adapters(self):
        pairs = (
            (ROOT / ".codex" / "hooks.json",
             ROOT / "company/init_templates/hosts/codex/hooks.json"),
            (ROOT / ".codex" / "hooks/spielos-context.py",
             ROOT / "company/init_templates/hosts/codex/hooks/spielos-context.py"),
            (ROOT / ".opencode/plugins/spielos-notifications.ts",
             ROOT / "company/init_templates/hosts/opencode/plugins/spielos-notifications.ts"),
        )
        for source, shipped in pairs:
            self.assertEqual(source.read_bytes(), shipped.read_bytes())


if __name__ == "__main__":
    unittest.main()
