"""Acceptance tests for goal-577aaacc7d / change-7cc84900b7 (Watchdog v2).

Plugin-contract portion — CORRECTED PREMISE (Director evidence 2026-08-15):
the running app is opencode2 (V2, build 0.0.0-next-17444), NOT opencode
1.18.15 V1. Proof: `ps aux` shows `opencode2.exe serve --service` and
`opencode2` only; @opencode-ai/cli package.json version = 0.0.0-next-17444;
npm dist-tags `next` = 0.0.0-next-17444; the app log on 2026-08-15 16:36:23 /
16:36:57 shows the V2 loader rejecting the V1 `{ id, server }` default with
`SchemaError(Missing key at ["default"]["effect"])` +
`Missing key at ["default"]["setup"])`.

The V2 plugin contract (@opencode-ai/plugin@0.0.0-next-17444, promise
variant): `export default { id: string, setup: (ctx) => Promise<Cleanup|void> |
Cleanup | void }`. `define()` is identity, so the default export is a plain
object with NO runtime import from @opencode-ai/plugin. The V2 server Context
exposes `event` (subscribe -> AsyncIterable; session.idle events carry
`data.sessionID`), `session` (prompt/synthetic with
`{ sessionID, text: { text } }`), `command` (no execute hook), and no
`client.tui.showToast` / no `$` BunShell.

Intended API contract (implementer must make every test pass by editing ONLY
`.opencode/plugins/spielos-notifications.ts` and this module):

1. The module's default export is a plain object with
   `id === "spielos-notifications"` and a `setup` function; the module has no
   runtime import from `@opencode-ai/plugin` (no V1 types leak in).
2. V1-only APIs are GONE: no `client.session.promptAsync`, no
   `client.tui.showToast`, no `command.execute.before` hook, no `$`/BunShell
   factory parameters.
3. The SpielOS1 adapter uses V2 event subscription only. On session.idle it
   reads pending notifications, surfaces them through `session.synthetic`, and
   acknowledges exact ids only after display. It owns no timer, heartbeat,
   watchdog, or `runner tick` fallback.
4. T2 (load contract under bun): importing the module yields `mod.default`
   with the id/setup shape; invoking `setup` with a hermetic stub Context
   resolves to a cleanup function; invoking cleanup resolves without
   throwing. The stub's `event.subscribe` is an empty async generator, so no
   live state is read or written and no subprocess ever runs (the 5s/60s
   timers are cleared by cleanup before the probe exits).
5. T3: the existing `company.tests.test_notification_surface` and
   `company.tests.test_chat_visible_supervision` suites still pass unchanged
   in intent (run as separate acceptance commands).

Variant handling for T2 (the parent spec): bun is at
/Users/shayan/.bun/bin/bun and natively imports TypeScript, so variant A
imports the `.ts` file directly. If importing the TS file fails for environment
reasons, this module DOCUMENTS it and falls back to variant B: transpile the
plugin with `bun build ... --format esm --target bun` and run the same probe
against the transpiled module record. The variant that ran is recorded and
printed.

Hermeticity notes for T2: no live `.spielos` state is read or written, no real
OpenCode app is started, and no network is used. The stub Context provides
`event.subscribe` (empty async generator) and `session.prompt`/`session.
synthetic` (immediate resolves). All probe-side state is in-memory.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_RELATIVE = Path("company/init_templates/hosts/opencode/plugins/spielos-notifications.ts")
BUN = Path(os.environ.get("BUN_BIN", "/Users/shayan/.bun/bin/bun"))

# The probe runs inside bun (ESM). __MODULE_PATH__ is substituted with the
# JSON-encoded absolute module path of the plugin (`.ts` for variant A, the
# bun-built `.mjs` for variant B).
PROBE_TEMPLATE = r"""
// Load-contract probe for the SpielOS OpenCode V2 plugin
// (opencode2 / @opencode-ai/plugin@0.0.0-next-17444, promise variant).
// Asserts the V2 module contract: default = { id, setup }, setup(ctx) with a
// hermetic stub Context resolves to a cleanup function, cleanup resolves.
const modulePath = __MODULE_PATH__;

// Hermetic stub Context standing in for the V2 plugin Context: the setup
// only touches event.subscribe (empty async generator -> the iteration loop
// ends immediately) and session.prompt/synthetic (immediate resolves). No
// subprocess ever runs and no live state is touched — the 5s/60s timers are
// cleared by the cleanup function before the probe exits.
const stubCtx = {
  event: {
    subscribe: async function* () {
      return;
    },
  },
  session: {
    prompt: async () => ({}),
    synthetic: async () => ({}),
  },
};

const failures = [];
const mod = await import(modulePath);

if (!mod.default || typeof mod.default !== "object") {
  failures.push(`PROBE-FAIL: mod.default expected object, got ${typeof mod.default}`);
} else {
  if (mod.default.id !== "spielos-notifications") {
    failures.push(`PROBE-FAIL: mod.default.id = ${JSON.stringify(mod.default.id)}, expected 'spielos-notifications'`);
  }
  if (typeof mod.default.setup !== "function") {
    failures.push(`PROBE-FAIL: typeof mod.default.setup = ${typeof mod.default.setup}, expected 'function'`);
  }
  if (mod.default.effect !== undefined) {
    failures.push("PROBE-FAIL: mod.default.effect must be undefined (promise variant, not effect variant)");
  }
  if (mod.default.server !== undefined) {
    failures.push("PROBE-FAIL: mod.default.server must be undefined (V1 shape removed)");
  }
}

if (mod.default && typeof mod.default.setup === "function") {
  let cleanup = null;
  try {
    cleanup = await mod.default.setup(stubCtx);
  } catch (error) {
    failures.push(`PROBE-FAIL: setup rejected: ${(error && error.stack) || error}`);
  }
  if (typeof cleanup !== "function") {
    failures.push(`PROBE-FAIL: setup must return a cleanup function, got ${typeof cleanup}`);
  } else {
    try {
      await cleanup();
    } catch (error) {
      failures.push(`PROBE-FAIL: cleanup rejected: ${(error && error.stack) || error}`);
    }
  }
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(
  "PROBE-OK load-contract: default={id,setup} setup->cleanup->ok no-v1-shape",
);
process.exit(0);
"""


class PluginExportContractStaticTests(unittest.TestCase):
    """T1 — static guards on the plugin source file (V2 contract)."""

    @classmethod
    def setUpClass(cls):
        cls.plugin_path = REPO_ROOT / PLUGIN_RELATIVE
        cls.source = cls.plugin_path.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    def test_plugin_source_file_exists(self):
        self.assertTrue(
            self.plugin_path.is_file(),
            "plugin source missing: %s" % self.plugin_path)

    def test_v2_default_object_export_with_id_and_setup(self):
        self.assertIn('export default {', self.source)
        self.assertIn('id: "spielos-notifications"', self.source)
        self.assertIn("setup: async (ctx: V2Context) => {", self.source)

    def test_no_runtime_import_from_opencode_ai_plugin(self):
        # define() is identity; a runtime import would drag the V1 types
        # (installed .opencode/node_modules/@opencode-ai/plugin is 1.18.15)
        # into a V2 module. Only a type-only import would be tolerable, and
        # the file uses local structural types instead — so NO import at all.
        for line in self.lines:
            self.assertNotIn(
                'from "@opencode-ai/plugin"', line,
                "no import from @opencode-ai/plugin is allowed in the V2 "
                "module; found: %r" % line)

    def test_v1_apis_removed(self):
        # V1-only surfaces that do not exist in the V2 server Context.
        self.assertNotIn("client.session.promptAsync", self.source)
        self.assertNotIn("client.tui.showToast", self.source)
        self.assertNotIn("command.execute.before", self.source)
        self.assertNotIn("$.cwd(", self.source)

    def test_v2_apis_used(self):
        self.assertIn("ctx.event.subscribe()", self.source)
        self.assertIn("event.type !== \"session.idle\"", self.source)
        self.assertNotIn("runner tick", self.source)
        self.assertNotIn("setInterval", self.source)
        self.assertNotIn("ctx.session.prompt({", self.source)
        self.assertIn("ctx.session.synthetic({", self.source)
        self.assertIn('"notifications", "list", "--status", "pending"', self.source)
        self.assertIn('["notifications", "ack", item.id, "--json"]', self.source)

    def test_setup_returns_cleanup_without_a_second_watch_loop(self):
        self.assertIn("return async () => {", self.source)


class PluginLoadContractTests(unittest.TestCase):
    """T2 — load-contract probe under bun (hermetic; variant recorded)."""

    VARIANT = "not_run"

    def _run_probe(self, module_path: Path, variant_label: str,
                   directory) -> dict:
        probe = Path(directory) / "probe.mjs"
        probe.write_text(
            PROBE_TEMPLATE.replace("__MODULE_PATH__",
                                   json.dumps(str(module_path))),
            encoding="utf-8")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": ".."}
        try:
            completed = subprocess.run(
                [str(BUN), str(probe), variant_label],
                cwd=str(REPO_ROOT), env=env,
                capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as error:
            return {"ok": False, "environment": True, "label": variant_label,
                    "stdout": "", "stderr": "probe timed out: %s" % error}
        return {
            "ok": completed.returncode == 0,
            "environment": "PROBE-FAIL" not in completed.stderr,
            "label": variant_label,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def _build_transpiled(self, directory) -> Path | None:
        """Variant B: transpile the plugin with bun, return the built file."""
        outfile = Path(directory) / "plugin_built.mjs"
        completed = subprocess.run(
            [str(BUN), "build", str(self.plugin_path),
             "--outfile", str(outfile), "--format", "esm", "--target", "bun"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
        if completed.returncode != 0 or not outfile.is_file():
            return None
        return outfile

    @classmethod
    def setUpClass(cls):
        cls.plugin_path = REPO_ROOT / PLUGIN_RELATIVE
        cls.assertTrue(
            BUN.is_file(),
            "bun not found at %s — T2 cannot run" % BUN)

    def test_load_contract_under_bun(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self._run_probe(self.plugin_path, "bun_direct_import",
                                    directory)
            if first["ok"]:
                PluginLoadContractTests.VARIANT = "bun_direct_import"
                self.assertIn("PROBE-OK", first["stdout"])
                print("\n[variant] bun_direct_import — direct bun import of "
                      "the plugin .ts file passed the V2 load contract")
                return
            # Import failed cleanly for environment reasons: document and
            # fall back to the transpiled module record.
            if first["environment"]:
                print("\n[bun] direct import of %s failed for environment "
                      "reasons; stderr follows:\n%s"
                      % (self.plugin_path, first["stderr"].strip()))
                built = self._build_transpiled(directory)
                if built is not None:
                    second = self._run_probe(
                        built, "bun_build_transpile_import", directory)
                    if second["ok"]:
                        PluginLoadContractTests.VARIANT = \
                            "bun_build_transpile_import"
                        self.assertIn("PROBE-OK", second["stdout"])
                        print("\n[variant] bun_build_transpile_import — "
                              "bun-built module record passed the V2 load "
                              "contract")
                        return
                    first = second
            self.fail(
                "load-contract probe failed (variant %s):\nstdout:\n%s\n"
                "stderr:\n%s" % (first["label"], first["stdout"],
                                 first["stderr"]))

    def test_recorded_variant(self):
        self.assertIn(
            PluginLoadContractTests.VARIANT,
            ("bun_direct_import", "bun_build_transpile_import"),
            "no load-contract variant ran; T2 must run before this test")


if __name__ == "__main__":
    unittest.main()
