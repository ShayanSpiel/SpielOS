import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from company.__main__ import main
from company.runtime import store as store_module
from company.runtime.loop import Runtime
from company.runtime.models import GoalStatus
from company.runtime.store import Store


class CompanySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "company.sqlite"
        self.runtime = Runtime(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def goal(self, goal_id, name="Snapshot goal"):
        return self.runtime.create_goal(
            goal_id=goal_id, name=name, owner_id="content",
            metric="content_packages", operator="ge", target=1,
            config={"workflow": "content-package", "allowed_files": ["x" * 10_000]},
        )

    def capture(self, *arguments):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(self.db), *arguments])
        self.assertEqual(0, code)
        return output.getvalue()

    def test_default_status_is_bounded_and_human_readable(self):
        self.goal("goal-active")
        output = self.capture("status")
        self.assertIn("# SpielOS company", output)
        self.assertIn("Snapshot goal", output)
        self.assertIn("Open work orders", output)
        self.assertNotIn("allowed_files", output)
        self.assertNotIn("x" * 100, output)
        self.assertLess(len(output), 5_000)

    def test_status_and_tasks_surface_open_work_orders(self):
        goal = self.goal("goal-work-order")
        blocked = self.runtime.once(goal["id"])
        self.assertEqual("blocked", blocked["cycle"]["run_status"])
        orders = self.runtime.store.work_orders(status="open", goal_id=goal["id"])
        self.assertEqual(1, len(orders))
        self.assertEqual("content-strategist", orders[0]["employee_id"])
        output = self.capture("status")
        self.assertIn(orders[0]["id"], output)
        self.assertIn("content-strategist", output)
        tasks = self.capture("tasks")
        self.assertIn(orders[0]["id"], tasks)
        self.assertIn("content-strategist", tasks)

    def test_raw_status_remains_an_explicit_full_audit_escape_hatch(self):
        self.goal("goal-raw")
        output = self.capture("status", "--raw")
        self.assertIn('"allowed_files"', output)
        self.assertIn("x" * 100, output)

    def test_single_goal_status_is_compact_and_actionable(self):
        goal = self.goal("goal-one")
        cycle = self.runtime.store.cycle(goal["id"])
        self.runtime.store.update_cycle(
            cycle["id"], stage="ACT", step="review",
            run_status="awaiting_approval", data={"large": "x" * 10_000})
        self.runtime.store.notify(goal["id"], cycle["id"], "approval_required", {
            "result": {"message": "Review the package"},
            "required_user_action": "Approve the exact package",
            "approval_interaction": {
                "question": "Approve this package?", "action": "Publish package",
                "artifact": "batch-1", "destination": "Threads", "scope": "one batch",
                "risk": "Public post", "consequence": "Nothing publishes",
                "fallback_command": "company approve goal-one",
            },
            "large": "x" * 10_000,
        })
        output = self.capture("status", goal["id"])
        self.assertIn("Approve the exact package", output)
        self.assertIn("awaiting_approval", output)
        self.assertIn("Approve this package?", output)
        self.assertIn("company approve goal-one", output)
        self.assertNotIn("x" * 100, output)
        self.assertLess(len(output), 5_000)

    def test_history_is_bounded_by_limit(self):
        for index in range(3):
            goal = self.goal(f"goal-history-{index}", f"History {index}")
            self.runtime.set_goal_status(goal["id"], GoalStatus.ABANDONED)
        output = self.capture("status", "--history", "--limit", "2")
        self.assertEqual(2, output.count("(`goal-history-"))


class CardOutputTests(unittest.TestCase):
    """Every user-facing command prints a card-style render by default (`# title`
    plus `- ` bullet items), keeps a parseable --json view, and `company status
    --raw` stays token-identical in shape."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "company.sqlite"
        self.runtime = Runtime(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def capture(self, *arguments, expect=0):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--db", str(self.db), *arguments])
        self.assertEqual(expect, code)
        return output.getvalue()

    def capture_error(self, *arguments):
        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["--db", str(self.db), *arguments])
        return code, error.getvalue()

    def goal(self, goal_id="goal-card", name="Card goal"):
        return self.runtime.create_goal(
            goal_id=goal_id, name=name, owner_id="content",
            metric="content_packages", operator="ge", target=1,
            config={"workflow": "content-package"})

    def assert_card(self, output, title_prefix):
        self.assertTrue(output.startswith(f"# {title_prefix}"), output)
        self.assertIn("\n- ", output)

    def test_goal_commands_render_cards_by_default(self):
        self.goal()
        created = self.capture(
            "goal", "create", "--name", "Second goal", "--owner", "content",
            "--metric", "content_packages", "--target", "1",
            "--config", '{"workflow":"content-package"}')
        self.assert_card(created, "Goal created:")
        listed = self.capture("goal", "list")
        self.assert_card(listed, "Goals (")
        self.assertIn("goal-card", listed)
        shown = self.capture("goal", "show", "goal-card")
        self.assert_card(shown, "Card goal")

    def test_goal_views_keep_parseable_json_shapes(self):
        self.goal()
        listed = json.loads(self.capture("goal", "list", "--json"))
        self.assertIsInstance(listed, list)
        self.assertEqual("goal-card", listed[0]["id"])
        shown = json.loads(self.capture("goal", "show", "goal-card", "--json"))
        self.assertEqual("goal-card", shown["goal"]["id"])
        created = json.loads(self.capture(
            "goal", "create", "--name", "Json goal", "--owner", "content",
            "--metric", "content_packages", "--target", "1", "--json",
            "--config", '{"workflow":"content-package"}'))
        self.assertEqual("active", created["goal_status"])

    def test_notifications_list_and_ack_render_cards(self):
        self.goal()
        note = self.runtime.store.notify(
            "goal-card", self.runtime.store.cycle("goal-card")["id"],
            "blocked", {"result": {"message": "Executor needed"}})
        listed = self.capture("notifications", "list")
        self.assert_card(listed, "Notifications (")
        self.assertIn(note["id"], listed)
        self.assertIn("Executor needed", listed)
        rows = json.loads(self.capture(
            "notifications", "list", "--status", "pending", "--limit", "100", "--json"))
        self.assertEqual(note["id"], rows[0]["id"])
        acked = self.capture("notifications", "ack", note["id"])
        self.assert_card(acked, "Notification acknowledged")
        self.assertIn("delivered", acked)
        self.assertEqual([], json.loads(self.capture(
            "notifications", "list", "--status", "pending", "--limit", "100", "--json")))

    def test_departments_and_strategy_render_cards(self):
        departments = self.capture("departments")
        self.assert_card(departments, "Departments (")
        packages = self.capture("department", "list")
        self.assert_card(packages, "Department packages (")
        rows = json.loads(self.capture("department", "list", "--json"))
        self.assertTrue(rows)
        self.assertIn("id", rows[0])
        strategy = self.capture("strategy")
        self.assert_card(strategy, "Strategy kernel")
        kernel = json.loads(self.capture("strategy", "--json"))
        self.assertIn("views", kernel)
        context = self.capture("strategy", "--topic", "outbound")
        self.assert_card(context, "Strategy context:")

    def test_runner_status_start_stop_render_cards(self):
        value = {"enabled": True, "running": False, "pid": None,
                 "started_at": None, "pid_path": "/tmp/p", "log_path": "/tmp/l",
                 "db_path": "/tmp/d"}
        with patch("company.__main__.RunnerService.status", return_value=value):
            output = self.capture("runner", "status")
        self.assert_card(output, "Runner status")
        with patch("company.__main__.RunnerService.status", return_value=value):
            parsed = json.loads(self.capture("runner", "status", "--json"))
        self.assertFalse(parsed["running"])
        with patch("company.__main__.RunnerService.stop", return_value=value):
            stopped = self.capture("runner", "stop")
        self.assert_card(stopped, "Runner stopped")
        with patch("company.__main__.RunnerService.start",
                   return_value={**value, "running": True, "pid": 4242}):
            started = self.capture("runner", "start")
        self.assert_card(started, "Runner started")

    def test_transitions_render_cards(self):
        goal = self.goal()
        paused = self.capture("pause", goal["id"])
        self.assert_card(paused, "Paused:")
        self.assertIn("`paused`", paused)
        resumed = self.capture("resume", goal["id"])
        self.assert_card(resumed, "Resumed:")
        state = json.loads(self.capture("resume", goal["id"], "--json"))
        self.assertEqual("active", state["goal"]["goal_status"])
        abandoned = self.capture("abandon", goal["id"])
        self.assert_card(abandoned, "Abandoned:")
        once = self.capture("once", goal["id"])
        self.assert_card(once, "Run once:")

    def test_evidence_and_change_complete_render_cards(self):
        goal = self.goal()
        added = self.capture("evidence", "add", goal["id"], "--kind", "draft",
                             "--source", "manual_test", "--payload", '{"note":"ok"}')
        self.assert_card(added, "Evidence added: draft")
        rows = json.loads(self.capture(
            "evidence", "add", goal["id"], "--kind", "draft",
            "--source", "manual_test", "--payload", '{"note":"ok"}', "--json"))
        self.assertEqual(goal["id"], rows["goal"]["id"])
        cycle = self.runtime.store.cycle(goal["id"])
        with sqlite3.connect(self.db) as con:
            con.execute("""INSERT INTO change_tasks
                (id,goal_id,run_id,owner_id,from_version,target_version,problem,
                 allowed_files_json,acceptance_tests_json,status,result_json,
                 originating_run_id,created_at,updated_at,change_kind,specification_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("change-card", goal["id"], cycle["id"], "company-runtime",
                 "5.2.0", "5.3.0", "card smoke", '["f"]', '["cmd"]', "approved",
                 '{}', "run-card", cycle["created_at"], cycle["created_at"],
                 "repair", '{}'))
        completed = self.capture("change", "complete", "change-card", "--passed",
                                 "--result", '{"acceptance": ["ok"], "changed": ["f"]}')
        self.assert_card(completed, "Change complete:")

    def test_status_raw_and_json_shapes_stay_stable(self):
        self.goal()
        raw = json.loads(self.capture("status", "--raw", "goal-card"))
        self.assertEqual(
            {"goal", "cycle", "run", "evidence", "decisions", "evaluation",
             "latest_result", "change_tasks", "work_orders", "children",
             "pending_notifications"},
            set(raw))
        self.assertNotIn("why_next", raw["cycle"])
        compact = json.loads(self.capture("status", "goal-card", "--json"))
        self.assertEqual({"goal", "attention", "unread_results", "work_orders"},
                         set(compact))

    def test_errors_print_readable_messages_on_stderr(self):
        code, error = self.capture_error("status", "goal-missing")
        self.assertEqual(1, code)
        self.assertIn("company: unknown goal: goal-missing", error)
        self.assertNotIn('"error"', error)
        code, error = self.capture_error("status", "goal-missing", "--json")
        self.assertEqual(1, code)
        self.assertEqual("unknown goal: goal-missing", json.loads(error)["error"])


class TerminalStateTests(unittest.TestCase):
    def test_store_initialization_removes_attention_from_previous_run_state(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "company.sqlite"
            runtime = Runtime(db)
            goal = runtime.create_goal(
                goal_id="goal-current-attention", name="Attention", owner_id="content",
                metric="content_packages", operator="ge", target=1,
                config={"workflow": "content-package"})
            cycle = runtime.store.cycle(goal["id"])
            runtime.store.update_cycle(cycle["id"], stage="ACT", step="work",
                                       run_status="blocked", data={})
            runtime.store.notify(goal["id"], cycle["id"], "approval_required", {})
            runtime.store.notify(goal["id"], cycle["id"], "blocked", {})
            # Repair scans run once per process per database file (audit
            # 2026-08-23 bug 15); this test simulates OUT-OF-BAND mutation
            # between opens, so it resets the scan marker like a new process.
            store_module._REPAIR_SCANNED_DBS.discard(str(db.resolve()))
            repaired = Store(db)
            self.assertEqual(["blocked"], [item["kind"] for item in repaired.attention()])

    def test_terminal_transition_closes_run_and_actionable_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory) / "company.sqlite")
            goal = runtime.create_goal(
                goal_id="goal-terminal", name="Terminal", owner_id="content",
                metric="content_packages", operator="ge", target=1,
                config={"workflow": "content-package"})
            cycle = runtime.store.cycle(goal["id"])
            runtime.store.update_cycle(cycle["id"], stage="ACT", step="review",
                                       run_status="awaiting_approval", data={})
            note = runtime.store.notify(goal["id"], cycle["id"], "approval_required", {})
            runtime.set_goal_status(goal["id"], GoalStatus.ABANDONED)
            self.assertEqual("completed", runtime.store.cycle(goal["id"])["run_status"])
            self.assertEqual("completed", runtime.store.run(cycle["id"])["status"])
            delivered = {item["id"]: item for item in runtime.store.notifications("delivered")}
            self.assertIn(note["id"], delivered)
            self.assertEqual([], runtime.store.attention())

    def test_store_initialization_repairs_legacy_terminal_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "company.sqlite"
            runtime = Runtime(db)
            goal = runtime.create_goal(
                goal_id="goal-drift", name="Drift", owner_id="content",
                metric="content_packages", operator="ge", target=1,
                config={"workflow": "content-package"})
            cycle = runtime.store.cycle(goal["id"])
            runtime.store.notify(goal["id"], cycle["id"], "blocked", {})
            with sqlite3.connect(db) as con:
                con.execute("UPDATE goals SET goal_status='abandoned' WHERE id=?", (goal["id"],))
                con.execute("UPDATE cycles SET run_status='blocked' WHERE id=?", (cycle["id"],))
                con.execute("UPDATE runs SET status='blocked' WHERE id=?", (cycle["id"],))
            # Once-per-process repair guard: reset so the reopened Store
            # re-scans this externally mutated file like a fresh process.
            store_module._REPAIR_SCANNED_DBS.discard(str(db.resolve()))
            repaired = Store(db)
            self.assertEqual("completed", repaired.cycle(goal["id"])["run_status"])
            self.assertEqual("completed", repaired.run(cycle["id"])["status"])
            self.assertEqual([], repaired.attention())


class DirectorRetrievalContractTests(unittest.TestCase):
    def test_director_keeps_autonomy_but_avoids_routine_history_scans(self):
        root = Path(__file__).resolve().parents[2]
        director = (root / "company/init_templates/hosts/opencode/agents/director.md").read_text()
        command = (root / "company/init_templates/hosts/opencode/commands/status.md").read_text()
        self.assertIn("This is retrieval discipline, not a loss of autonomy", director)
        self.assertIn("compact projection as authoritative", command)
        self.assertIn("retain full autonomy to drill down", command)
        self.assertIn("--raw", command)


if __name__ == "__main__":
    unittest.main()
