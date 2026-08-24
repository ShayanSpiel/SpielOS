"""Acceptance tests for goal-notification-surface-repair-20260815 (change_kind=repair).

Problem statement (the spec): "The runner-persistence change
(goal-runner-persistence-20260815) marks every pending notification delivered on
each watch tick; the OpenCode notifications plugin
(.opencode/plugins/spielos-notifications.ts) surfaces only --status pending
notifications, so the chat confirmation channel is starved (runner log shows
notifications_delivered: 51 draining the backlog; new notes delivered within
seconds of creation). The plugin also runs `company runner tick` every 5s while
the daemon watch loop ticks, causing lease races (already running in another
client). Fix: plugin queries recent reportable notifications across
pending+delivered with the existing 5-minute re-prompt throttle, and skips its
own tick when the runner daemon state is running; add a static-contract
acceptance test for the plugin behavior."

Intended API contract (implementer must make every test pass by editing ONLY
`.opencode/plugins/spielos-notifications.ts` and this module):

1. The plugin check reads BOTH `--status pending` and `--status delivered`
   notifications, merges them by id (pending wins on duplicates), keeps the
   REPORTABLE kind filter, the 300_000 ms (5-minute) per-id re-prompt throttle,
   the approval_required wake-up, and the chat surface.
2. The plugin skips its own `company runner tick` while the runner daemon is
   running (`runner status --json` reports `running: true`), keeping the
   `enabled === false` guard; the notifications read still happens when the
   daemon is running.
3. The plugin lifecycle (cleanup, session.idle event, runner-down /
   loop-wedged chat alerts) is unchanged in intent.

Goal-runner-watchdog-supervision-20260815 extends the surface contract:

4. The plugin INVERTS the silent skip: when the polled runner status says not
   running, or the daemon's heartbeat stamp
   (.spielos/state/runner.heartbeat) is older than ALIVE_STALE_MS (45_000 ms),
   it surfaces a chat-visible runner-down alert throttled by the same
   300_000 ms re-prompt window via the synthetic "runner-down" key, and that
   key survives the id prune.
5. The REPORTABLE kind set additionally accepts the runtime watchdog kinds
   `runner_down` and `stuck_goal`, and action_required payloads carrying a
   `watchdog.signal` marker are surfaced with the watchdog titles.

CORRECTED PREMISE (Director evidence 2026-08-15): the app is opencode2 V2
(0.0.0-next-17444), so the V1 surfaces (`client.session.promptAsync`,
`client.tui.showToast`, `command.execute.before`, `$` BunShell) do not exist
in the V2 server Context and are replaced by `ctx.session.prompt` /
`ctx.session.synthetic` / `ctx.event.subscribe()`; daemon lifecycle moved to
the OS supervisor (supervisor.py). The behavioral contract above is unchanged.

This suite is hermetic and static: it only reads the plugin source file from
the repo and asserts the required behaviors exist in the source. No network, no
subprocesses, no live state is touched.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_RELATIVE = Path("company/init_templates/hosts/opencode/plugins/spielos-notifications.ts")


def indent_of(line):
    return len(line) - len(line.lstrip())


class NotificationSurfaceContractTests(unittest.TestCase):
    """Static-contract checks for the OpenCode notifications surfacing plugin."""

    @classmethod
    def setUpClass(cls):
        cls.plugin_path = REPO_ROOT / PLUGIN_RELATIVE
        cls.source = cls.plugin_path.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    def check_body(self):
        """Lines of the `check` function only (where the queries live)."""
        start = next(
            i for i, line in enumerate(self.lines)
            if line.strip().startswith("const check = async () => {"))
        end = next(
            i for i, line in enumerate(self.lines)
            if line.strip().startswith("const timer = setInterval("))
        return self.lines[start:end]

    def test_plugin_source_file_exists(self):
        self.assertTrue(
            self.plugin_path.is_file(),
            "plugin source missing: %s" % self.plugin_path)

    def test_check_queries_both_pending_and_delivered(self):
        body = "\n".join(self.check_body())
        self.assertIn('"--status", "pending"', body)
        self.assertIn('"--status", "delivered"', body)

    def test_pending_and_delivered_merged_by_id_with_pending_winning(self):
        self.assertIn("byID.set(item.id, item)", self.source)
        # The pending spread must come after the delivered spread so a pending
        # entry overwrites a delivered entry with the same id.
        self.assertGreater(
            self.source.index("JSON.parse(pendingRaw)"),
            self.source.index("JSON.parse(deliveredRaw)"),
        )

    def test_reprompt_throttle_constant_present(self):
        self.assertIn("REPROMPT_THROTTLE_MS", self.source)
        self.assertIn("300_000", self.source)
        # The throttle is applied as the existing 5-minute re-prompt window.
        self.assertIn("> REPROMPT_THROTTLE_MS", self.source)

    def test_tick_skipped_when_daemon_state_running(self):
        body = self.check_body()
        tick_index = next(
            i for i, line in enumerate(body) if '"runner", "tick"' in line)
        guard_index = next(
            i for i, line in enumerate(body[:tick_index])
            if "running" in line and line.strip().startswith("if ("))
        guard = body[guard_index]
        self.assertIn("status.running", guard)
        # The tick is nested inside the running-state guard...
        self.assertGreater(
            indent_of(body[tick_index]), indent_of(guard),
            "tick invocation must sit inside the running-state guard")
        # ...and the enabled===false guard is retained.
        self.assertTrue(
            any("status.enabled === false" in line for line in body),
            "enabled === false guard must be retained")

    def test_notifications_read_still_happens_when_daemon_running(self):
        body = self.check_body()
        guard_index = next(
            i for i, line in enumerate(body)
            if "status.running" in line and line.strip().startswith("if ("))
        guard_indent = indent_of(body[guard_index])
        for needle in ('"--status", "pending"', '"--status", "delivered"'):
            query_index = next(i for i, line in enumerate(body) if needle in line)
            # Queries run after the guard, at the check-body indent level, so
            # they are NOT skipped when the daemon is running.
            self.assertGreater(query_index, guard_index)
            self.assertEqual(indent_of(body[query_index]), guard_indent)

    def test_reportable_kind_set_unchanged(self):
        block = self.source[self.source.index("const REPORTABLE"):]
        block = block[:block.index("])") + 1]
        for kind in ("approval_required", "blocked", "failed",
                     "run_completed", "goal_achieved"):
            self.assertIn('"%s"' % kind, block)
        self.assertIn("REPORTABLE.has(item.kind)", self.source)

    def test_approval_required_wakeup_intact(self):
        self.assertIn('item.kind === "approval_required"', self.source)
        self.assertIn("ctx.session.prompt", self.source)
        self.assertIn(
            "Immediately invoke the native question tool", self.source)
        self.assertIn("approval_interaction", self.source)

    def test_lifecycle_contract_intact_v2(self):
        # V2 lifecycle: event subscription drives session.idle; timers are
        # cleared by the setup cleanup. The V1-only surfaces (toast, command
        # hook, BunShell) are gone from the V2 server Context.
        self.assertIn("ctx.event.subscribe()", self.source)
        self.assertIn("session.idle", self.source)
        self.assertIn("clearInterval(timer)", self.source)
        self.assertIn("clearInterval(hudTimer)", self.source)
        self.assertIn("return async () => {", self.source)
        self.assertNotIn("client.tui.showToast", self.source)
        self.assertNotIn("command.execute.before", self.source)

    def test_heartbeat_two_signal_thresholds_and_path_present(self):
        # Wedge hardening (2026-08-15): the heartbeat is TWO signals —
        # alive_at (heartbeat thread, every 10s) for process liveness and
        # last_tick (per watch cycle) for loop progress. A long measure tick
        # must never false-alarm runner-down (alive_at stays fresh), while a
        # wedged loop is caught by a stale last_tick.
        self.assertIn("ALIVE_STALE_MS", self.source)
        self.assertIn("45_000", self.source)
        self.assertIn("LOOP_STALE_MS", self.source)
        self.assertIn("75_000", self.source)
        self.assertIn(".spielos/state/runner.heartbeat", self.source)
        # The heartbeat reader parses BOTH signals (heartbeatAgeMs is outside
        # the check body, so assert on the full source here).
        self.assertIn("parsed.alive_at", self.source)
        self.assertIn("parsed.last_tick", self.source)
        body = "\n".join(self.check_body())
        self.assertIn("alive > ALIVE_STALE_MS", body)
        self.assertIn("tick > LOOP_STALE_MS", body)

    def test_runner_down_detection_inverts_silent_skip(self):
        body = "\n".join(self.check_body())
        # The alert condition combines the polled status with the PROCESS
        # signal (alive_at from the dedicated heartbeat thread). The early
        # return must NOT fire when the runner is down: fresh notifications
        # are skipped but the runner-down alert still runs.
        self.assertIn("status.running !== true", body)
        self.assertIn("alive !== null && alive > ALIVE_STALE_MS", body)
        self.assertIn("if (!fresh.length && !runnerDown) return", body)
        # Throttled by the same 300_000 ms re-prompt window via a synthetic key.
        self.assertIn('prompted.get("runner-down")', body)
        self.assertIn('prompted.set("runner-down", now)', body)
        self.assertIn("> REPROMPT_THROTTLE_MS", body)

    def test_wedged_loop_signal_surfaces_distinct_alert(self):
        # alive_at fresh + last_tick stale = wedged serial loop (the 2026-08-15
        # wedge), a different failure than a dead process: own throttle key,
        # own chat alert text.
        body = "\n".join(self.check_body())
        self.assertIn("loopWedged", body)
        self.assertIn("tick > LOOP_STALE_MS", body)
        self.assertIn('prompted.get("loop-wedged")', body)
        self.assertIn('prompted.set("loop-wedged", now)', body)
        self.assertIn("SpielOS runner loop wedged", body)

    def test_runner_down_alert_surfaces_in_chat(self):
        body = "\n".join(self.check_body())
        self.assertIn("SpielOS runner down", body)
        self.assertIn("company runner start", body)

    def test_runner_down_key_survives_prompted_prune(self):
        # The synthesized key is not a notification id; the prune must skip it
        # or the throttle resets on every check and the alert spams.
        self.assertIn('id !== "runner-down"', self.source)

    def test_runner_down_and_stuck_goal_kinds_surfaced(self):
        block = self.source[self.source.index("const REPORTABLE"):]
        block = block[:block.index("])") + 1]
        for kind in ("runner_down", "stuck_goal"):
            self.assertIn('"%s"' % kind, block)
        # Runtime watchdog notifications ride the action_required kind with a
        # payload watchdog.signal marker; the plugin types surface it.
        self.assertIn("watchdog?.signal", self.source)

    def test_hud_ticker_reads_live_status_surface(self):
        # Watchdog v2 HUD: the ticker reads the daemon's live_status.json and
        # injects a compact line via session.synthetic on its own cadence.
        self.assertIn(".spielos/state/live_status.json", self.source)
        self.assertIn("ctx.session.synthetic", self.source)
        self.assertIn("buildHudTicker", self.source)
        self.assertIn("HUD_TICKER_INTERVAL_MS", self.source)


if __name__ == "__main__":
    unittest.main()
