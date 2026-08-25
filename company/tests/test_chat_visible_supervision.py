"""Acceptance tests for goal-chat-visible-supervision-20260815 (change_kind=repair).

Problem statement (the spec): "Owner-verified supervision gap in the OpenCode
chat surface, repeated across sessions: the durable runner demonstrably
watches goals on resume_at schedules and emits notifications (316 rows in
company.sqlite, delivered_at within seconds), yet NOTHING is visible inside
the conversation on a schedule. The OpenCode plugin surfaces only event-driven
items and prompts only for approval_required; there is no periodic progress
digest posted into the chat, and after a goal reaches a terminal state the
goal_achieved row is marked delivered and no follow-up prompt with a
recommended next action is raised. From the owner perspective the system goes
silent after goal completion."

Intended API contract (implementer must make every test pass by editing ONLY
`company/runtime/runner.py`, `company/runtime/notifications.py`,
`company/runtime/loop.py`, `.opencode/plugins/spielos-notifications.ts`
and this module):

T1. Digest emission cadence: while at least one goal is active,
    `Runner._maybe_emit_digest` emits exactly one `watchdog_digest`
    notification per `DIGEST_INTERVAL_SECONDS` (default 900). The cadence is
    durable (state marker `.spielos/state/runner_digest.json`), so a fresh
    Runner over the same store (simulated daemon restart) inside the interval
    re-emits nothing; an interval boundary re-emits. With no active goals
    (none, or paused) nothing is emitted and the marker is not advanced.

T2. Digest payload contract: the notification payload carries the active goal
    ids with stage/step, run_status, resume_at and last tick time, the pending
    approvals (with goal ids), recent terminal outcomes, blockers, and a
    numeric summary.

T3. Terminal follow-up: a goal reaching ACHIEVED (handler evaluation), EXPIRED
    (deadline), or ABANDONED (owner) emits BOTH the existing `goal_<status>`
    notification and a `goal_completed_followup` notification whose payload
    carries a non-empty `recommended_next_action` derived from the goal
    context (owner-specific: deploy/verify for system improvements,
    resume/continue-or-escalate for outbound campaigns).

T4. Plugin surfacing: the plugin's REPORTABLE set accepts `watchdog_digest`
    and `goal_completed_followup`, and the surfacing path builds a typed text
    prompt from the payload (digest summary + goals, follow-up recommended
    next action) inside the same `activeSessionID` resolution as the approval
    flow, fed by the throttle-filtered `fresh` list. Contract-tested
    statically from the plugin source (hermetic: no real promptAsync), the
    same pattern as test_notification_surface.py.

This suite is hermetic: every test builds its own runtime in a temp directory
with in-memory handlers. No live state, no real sessions, no daemons.
"""

import json
import sys
import tempfile
import unittest
from company.tests._adapter_mode import requires_full_plugin
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.runtime.loop import Runtime  # noqa: E402
from company.runtime.models import (  # noqa: E402
    GoalHandler, GoalStatus, RunStatus, Stage, StageResult,
)
from company.runtime.runner import (  # noqa: E402
    DIGEST_FILENAME, DIGEST_INTERVAL_SECONDS, Runner,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_RELATIVE = Path("company/init_templates/hosts/opencode/plugins/spielos-notifications.ts")


class ParkingHandler(GoalHandler):
    """One guarded action; a parked run keeps a goal active for digest checks."""

    id = "digest_parking_test"

    def observe(self, ctx):
        return StageResult("collect", {"real": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "execute_gated"})

    def act(self, ctx, decision):
        if ctx.approval_status("execute") != "approved":
            return StageResult(
                "review", {"prepared": True}, RunStatus.AWAITING_APPROVAL, Stage.ACT)
        return StageResult("execute", {"executed": True})

    def evaluate(self, ctx, action_result):
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True}, "validity": "business"})


class ImmediateAchieveHandler(GoalHandler):
    """Runs straight to ACHIEVED in one `once` call."""

    id = "digest_achieving_test"

    def observe(self, ctx):
        return StageResult("collect", {"ok": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "finish"})

    def act(self, ctx, decision):
        return StageResult("execute", {"done": True})

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True},
                        "validity": validity})


class DigestEmissionTests(unittest.TestCase):
    """T1: cadence, no-active-goals silence, durable restart survival."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {"digest_parking_test": ParkingHandler()})
        self.runner = Runner(self.runtime)

    def parked_goal(self):
        goal = self.runtime.create_goal(
            name="Digest Parked", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(goal["id"])  # parks awaiting approval; goal stays active
        return goal

    def digest_rows(self):
        with self.runtime.store.connect() as con:
            rows = con.execute(
                "SELECT id, goal_id, run_id, kind, payload_json, created_at "
                "FROM notifications WHERE kind='watchdog_digest'").fetchall()
        return [{"id": r[0], "goal_id": r[1], "run_id": r[2], "kind": r[3],
                 "payload": json.loads(r[4]), "created_at": r[5]} for r in rows]

    def marker_path(self) -> Path:
        return self.runtime.store.path.parent / DIGEST_FILENAME

    def test_exactly_one_digest_per_interval_with_restart_survival(self):
        goal = self.parked_goal()
        t0 = datetime.now(timezone.utc) - timedelta(minutes=30)
        # First interval: exactly one emission.
        self.assertEqual([goal["id"]], self.runner._maybe_emit_digest(now=t0))
        self.assertEqual(1, len(self.digest_rows()))
        self.assertTrue(self.marker_path().is_file(),
                        "digest cadence must be durable, not in-memory")
        # Inside the interval: no duplicate.
        self.assertEqual([], self.runner._maybe_emit_digest(
            now=t0 + timedelta(minutes=5)))
        self.assertEqual(1, len(self.digest_rows()))
        # Simulated daemon restart: a fresh Runner shares no in-memory state,
        # but the durable marker must hold the interval open.
        restarted = Runner(self.runtime)
        self.assertEqual([], restarted._maybe_emit_digest(
            now=t0 + timedelta(minutes=10)))
        self.assertEqual(1, len(self.digest_rows()))
        # Next interval boundary: exactly one (re-)emission, still one row
        # (the store upsert keeps one watchdog_digest per goal/run/kind).
        boundary = t0 + timedelta(minutes=15, seconds=1)
        self.assertEqual([goal["id"]], restarted._maybe_emit_digest(now=boundary))
        rows = self.digest_rows()
        self.assertEqual(1, len(rows))
        marker = json.loads(self.marker_path().read_text())
        self.assertEqual(boundary.isoformat(), marker["last_emitted_at"])
        self.assertEqual(rows[0]["payload"]["watchdog"]["generated_at"],
                         boundary.isoformat())

    def test_no_digest_without_active_goals(self):
        # No goals at all: silent, and the marker is NOT advanced.
        self.assertEqual([], self.runner._maybe_emit_digest(
            now=datetime.now(timezone.utc)))
        self.assertEqual([], self.digest_rows())
        self.assertFalse(self.marker_path().exists(),
                         "with no active goals the digest marker must stay untouched")
        # A paused goal is not active: still silent.
        goal = self.runtime.create_goal(
            name="Paused", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.set_goal_status(goal["id"], GoalStatus.PAUSED)
        self.assertEqual([], self.runner._maybe_emit_digest(
            now=datetime.now(timezone.utc)))
        self.assertEqual([], self.digest_rows())

    def test_interval_default_is_15_minutes(self):
        self.assertEqual(900, DIGEST_INTERVAL_SECONDS)

    def test_digest_emitted_from_watch_loop(self):
        # The digest must fire from the daemon watch loop, so it never depends
        # on the plugin being present.
        goal = self.parked_goal()
        with unittest.mock.patch("company.runtime.runner.time.sleep"):
            list(self.runner.watch(goal_id=goal["id"], max_ticks=3))
        self.assertEqual(1, len(self.digest_rows()))


class DigestPayloadTests(unittest.TestCase):
    """T2: digest payload contract (active goals, approvals, terminal, blockers)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {
            "digest_parking_test": ParkingHandler(),
            "digest_achieving_test": ImmediateAchieveHandler(),
        })
        self.runner = Runner(self.runtime)

    def backdate_cycle(self, goal_id: str, *, run_status: str, resume_at=None,
                       stage="ACT", step="collect", updated_at=None):
        past = (updated_at or (datetime.now(timezone.utc) - timedelta(minutes=5)))
        with self.runtime.store.connect() as con:
            con.execute(
                "UPDATE cycles SET run_status=?, resume_at=?, stage=?, step=?, "
                "updated_at=? WHERE goal_id=?",
                (run_status,
                 resume_at.isoformat() if resume_at else None,
                 stage, step, past.isoformat(), goal_id))

    def test_digest_payload_contract(self):
        # Active goal 1: parked awaiting approval (pending approval_required).
        parked = self.runtime.create_goal(
            name="Parked", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(parked["id"])
        # Active goal 2: waiting on a future resume_at.
        waiting = self.runtime.create_goal(
            name="Waiting", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True, config={})
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        self.backdate_cycle(waiting["id"], run_status="waiting", resume_at=future)
        # Terminal goal: achieved earlier.
        done = self.runtime.create_goal(
            name="Done", owner_id="digest_achieving_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(done["id"])
        self.assertEqual("achieved",
                         self.runtime.store.goal(done["id"])["goal_status"])
        # Active blocker: cycle in blocked state.
        blocked = self.runtime.create_goal(
            name="Blocked", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True, config={})
        self.backdate_cycle(blocked["id"], run_status="blocked",
                            updated_at=datetime.now(timezone.utc) - timedelta(hours=2))

        t0 = datetime.now(timezone.utc)
        emitted = self.runner._maybe_emit_digest(now=t0)
        self.assertEqual([parked["id"]], emitted,
                         "the digest must attach to the first active goal")
        rows = [row for row in self.runtime.store.notifications("pending")
                if row["kind"] == "watchdog_digest"]
        self.assertEqual(1, len(rows))
        payload = rows[0]["payload"]

        # Watchdog block identifies the digest and its interval.
        self.assertEqual("progress_digest", payload["watchdog"]["signal"])
        self.assertEqual(t0.isoformat(), payload["watchdog"]["generated_at"])
        self.assertEqual(DIGEST_INTERVAL_SECONDS,
                         payload["watchdog"]["interval_seconds"])

        # Active goals: ids plus stage/step/run_status/resume_at/last tick.
        goals = payload["goals"]
        goal_ids = [g["goal_id"] for g in goals]
        self.assertIn(parked["id"], goal_ids)
        self.assertIn(waiting["id"], goal_ids)
        self.assertIn(blocked["id"], goal_ids)
        self.assertNotIn(done["id"], goal_ids, "terminal goals are not active")
        for entry in goals:
            self.assertIn("stage", entry)
            self.assertIn("step", entry)
            self.assertIn("run_status", entry)
            self.assertIn("resume_at", entry)
            self.assertIn("last_tick_at", entry)
        waiting_entry = next(g for g in goals if g["goal_id"] == waiting["id"])
        self.assertEqual("waiting", waiting_entry["run_status"])
        self.assertEqual(future.isoformat(), waiting_entry["resume_at"])

        # Pending approvals: the parked goal's approval_required is pending.
        self.assertEqual(1, len(payload["pending_approvals"]))
        self.assertIn(parked["id"],
                      [p["goal_id"] for p in payload["pending_approvals"]])

        # Recent terminal outcomes: the achieved goal appears with its status.
        self.assertTrue(
            any(t["goal_id"] == done["id"] and t["goal_status"] == "achieved"
                for t in payload["recent_terminal"]),
            "recent terminal outcomes must include the achieved goal")

        # Blockers: the blocked cycle is called out with its run status.
        self.assertTrue(
            any(b["goal_id"] == blocked["id"] and b["run_status"] == "blocked"
                for b in payload["blockers"]),
            "the blocked active goal must appear in blockers")

        # Numeric summary mirrors the lists.
        self.assertEqual({"active_goals": 3, "pending_approvals": 1,
                          "recent_terminal": len(payload["recent_terminal"]),
                          "blockers": 1}, payload["summary"])


class TerminalFollowupTests(unittest.TestCase):
    """T3: achieved/expired/abandoned each keep goal_<status> AND add a
    follow-up carrying a non-empty context-derived recommended next action."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / ".spielos/state/company.sqlite"
        self.runtime = Runtime(self.db, {
            "digest_parking_test": ParkingHandler(),
            "digest_achieving_test": ImmediateAchieveHandler(),
        })
        self.runner = Runner(self.runtime)

    def notifications_for(self, goal_id):
        with self.runtime.store.connect() as con:
            rows = con.execute(
                "SELECT kind, payload_json FROM notifications WHERE goal_id=? "
                "ORDER BY created_at", (goal_id,)).fetchall()
        return {kind: json.loads(payload) for kind, payload in rows}

    def assert_followup(self, payload, expected_status):
        self.assertIn("followup", payload)
        self.assertEqual(expected_status, payload["followup"]["goal_status"])
        action = payload["followup"]["recommended_next_action"]
        self.assertTrue(isinstance(action, str) and action.strip(),
                        "recommended_next_action must be non-empty")
        self.assertEqual(action, payload["required_user_action"],
                         "the follow-up must make the next action the required user action")

    def test_achieved_keeps_goal_achieved_and_emits_followup(self):
        goal = self.runtime.create_goal(
            name="Achieve", owner_id="digest_achieving_test",
            metric="done", operator="eq", target=True, config={})
        self.runtime.once(goal["id"])
        notifications = self.notifications_for(goal["id"])
        self.assertIn("goal_achieved", notifications,
                      "the existing goal_achieved notification must still fire")
        self.assertIn("goal_completed_followup", notifications)
        self.assert_followup(notifications["goal_completed_followup"], "achieved")

    def test_expired_keeps_goal_expired_and_emits_followup(self):
        goal = self.runtime.create_goal(
            name="Expire", owner_id="digest_achieving_test",
            metric="done", operator="eq", target=True,
            deadline=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            config={})
        state = self.runtime.once(goal["id"])
        self.assertEqual("expired", state["goal"]["goal_status"])
        notifications = self.notifications_for(goal["id"])
        self.assertIn("goal_expired", notifications,
                      "deadline expiry must still fire goal_expired")
        self.assertIn("goal_completed_followup", notifications)
        self.assert_followup(notifications["goal_completed_followup"], "expired")

    def test_abandoned_keeps_goal_abandoned_and_emits_followup(self):
        goal = self.runtime.create_goal(
            name="Abandon", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True, config={})
        state = self.runtime.set_goal_status(goal["id"], GoalStatus.ABANDONED)
        self.assertEqual("abandoned", state["goal"]["goal_status"])
        notifications = self.notifications_for(goal["id"])
        self.assertIn("goal_abandoned", notifications,
                      "owner abandon must still fire goal_abandoned")
        self.assertIn("goal_completed_followup", notifications)
        self.assert_followup(notifications["goal_completed_followup"], "abandoned")

    def test_recommended_next_action_is_derived_from_goal_context(self):
        runtime = Runtime(self.db, {
            "system-improvement": ParkingHandler(),
            "outbound": ParkingHandler(),
            "director": ParkingHandler(),
            "digest_parking_test": ParkingHandler(),
        })
        cases = [
            ("system-improvement", ("deploy", "verify")),
            ("outbound", ("resume", "continue")),
            ("director", ("next goal",)),
        ]
        for owner_id, needles in cases:
            with self.subTest(owner=owner_id):
                goal = runtime.create_goal(
                    name="Context", owner_id=owner_id,
                    metric="done", operator="eq", target=True, config={})
                runtime.set_goal_status(goal["id"], GoalStatus.ABANDONED)
                notifications = self.notifications_for(goal["id"])
                action = notifications["goal_completed_followup"]["followup"][
                    "recommended_next_action"]
                self.assertTrue(any(n.lower() in action.lower() for n in needles),
                                f"{owner_id} recommendation should mention {needles}: {action}")
        # Unknown owners still get a concrete, non-empty recommendation.
        goal = runtime.create_goal(
            name="Custom", owner_id="digest_parking_test",
            metric="done", operator="eq", target=True,
            config={"workflow": "custom-pipeline"})
        runtime.set_goal_status(goal["id"], GoalStatus.ABANDONED)
        action = self.notifications_for(goal["id"])[
            "goal_completed_followup"]["followup"]["recommended_next_action"]
        self.assertIn("custom-pipeline", action)


@requires_full_plugin
class PluginSurfaceContractTests(unittest.TestCase):
    """T4: plugin REPORTABLE + payload-built typed prompt for the two new kinds.

    Hermetic static contract (the pattern established by
    test_notification_surface.py): reads the plugin source and asserts the
    required behavior exists; no real promptAsync is ever invoked.
    """

    @classmethod
    def setUpClass(cls):
        cls.plugin_path = REPO_ROOT / PLUGIN_RELATIVE
        cls.source = cls.plugin_path.read_text(encoding="utf-8")
        cls.lines = cls.source.splitlines()

    def test_plugin_source_file_exists(self):
        self.assertTrue(self.plugin_path.is_file(),
                        "plugin source missing: %s" % self.plugin_path)

    def test_reportable_set_includes_both_new_kinds(self):
        block = self.source[self.source.index("const REPORTABLE"):]
        block = block[:block.index("])") + 1]
        self.assertIn('"watchdog_digest"', block)
        self.assertIn('"goal_completed_followup"', block)

    def test_surfacing_filters_the_new_kinds(self):
        self.assertIn('item.kind === "watchdog_digest"', self.source)
        self.assertIn('item.kind === "goal_completed_followup"', self.source)

    def test_surfacing_prompt_is_built_from_the_payload(self):
        # The digest prompt reads the payload summary + active goals list.
        self.assertIn("payload.summary", self.source)
        self.assertIn("payload.goals", self.source)
        self.assertIn("summary.active_goals", self.source)
        self.assertIn("summary.pending_approvals", self.source)
        # The follow-up prompt quotes the recommended next action.
        self.assertIn("recommended_next_action", self.source)
        self.assertIn("payload.followup", self.source)

    def test_surfacing_prompts_inside_active_session_resolution(self):
        # Both new kinds ride the same activeSessionID resolution as the
        # approval flow: the prompt loop must sit inside the
        # `if (activeSessionID) {` block, and prompts target that session
        # (V2: ctx.session.prompt({ sessionID, text }) — no agent field).
        body = self.lines
        guard = next(i for i, line in enumerate(body)
                     if line.strip().startswith("if (activeSessionID) {"))
        guard_indent = len(body[guard]) - len(body[guard].lstrip())
        surfaced = next(i for i, line in enumerate(body)
                        if "buildSurfacePrompt(item)" in line)
        self.assertGreater(surfaced, guard)
        self.assertGreater(len(body[surfaced]) - len(body[surfaced].lstrip()),
                           guard_indent,
                           "the digest/follow-up prompt loop must sit inside "
                           "the activeSessionID guard")
        self.assertIn("ctx.session.prompt", self.source)
        self.assertIn("sessionID: activeSessionID", self.source)

    def test_surfacing_respects_existing_throttle_and_approval_flow(self):
        # The surfaced filter consumes the throttle-filtered `fresh` list, so
        # the existing 300s per-id re-prompt window applies unchanged.
        self.assertIn("const surfaced = fresh.filter", self.source)
        # Approval prompting must be untouched.
        self.assertIn('item.kind === "approval_required"', self.source)
        self.assertIn("Immediately invoke the native question tool", self.source)
        # The runner-down self-tick fallback and detection survive.
        self.assertIn('"runner", "tick"', self.source)
        self.assertIn("status.running !== true", self.source)
        self.assertIn('prompted.set("runner-down", now)', self.source)


if __name__ == "__main__":
    unittest.main()