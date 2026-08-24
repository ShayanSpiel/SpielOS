"""Integrity 6.1: observation and tests must not mutate live company state."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from company.__main__ import main
from company.runtime.loop import Runtime
from company.runtime.models import GoalHandler, GoalStatus, RunStatus, StageResult
from company.runtime.store import Store, canonical_live_db, is_canonical_live_db
from company.runtime.system_improvement import SystemImprovement


COMPANY_ROOT = Path(__file__).resolve().parents[1]


class _ProbeHandler(GoalHandler):
    id = "isolation_probe"
    version = "9.9.9"

    def observe(self, ctx):
        return StageResult("collect", {"ok": True})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "finish"})

    def act(self, ctx, decision):
        return StageResult("execute", {"done": True})

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult("goal_check", {"done": True}, RunStatus.IDLE,
                           goal_status=GoalStatus.ACHIEVED,
                           evaluation={"verdict": "goal_met", "goal_met": True,
                                       "metrics": {ctx.goal.metric: True},
                                       "validity": validity})


def _audit_projection(db_path: Path) -> dict:
    con = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True, timeout=10)
    try:
        tables = ("goals", "runs", "evidence", "owner_versions", "approvals",
                  "evaluations", "decisions", "change_tasks", "work_orders",
                  "notifications")
        out = {}
        for table in tables:
            present = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            if not present:
                out[table] = []
                continue
            out[table] = [tuple(row) for row in con.execute(f"SELECT * FROM {table}")]
        return out
    finally:
        con.close()


def _file_fingerprint(root: Path) -> list[str]:
    items = []
    if not root.exists():
        return items
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        items.append(f"{path.relative_to(root)}:{digest}")
    return items


def _department_fingerprint() -> dict[str, list[str]]:
    return {
        "departments": _file_fingerprint(COMPANY_ROOT / "departments"),
        "installed_agents": _file_fingerprint(COMPANY_ROOT / "agents" / "installed"),
    }


class IsolationTests(unittest.TestCase):
    def test_test_isolation_env_is_enabled(self):
        self.assertEqual(os.environ.get("SPIELOS_TEST_ISOLATION"), "1")

    def test_runtime_init_does_not_register_deployments(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "company.sqlite"
            Runtime(db, {"isolation_probe": _ProbeHandler()})
            self.assertEqual(Store(db).owner_versions(), [])

    def test_complete_change_is_the_explicit_version_write_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Runtime(Path(tmp) / "company.sqlite",
                              {"system-improvement": SystemImprovement()})
            goal = runtime.create_goal(
                name="Version only on complete", owner_id="system-improvement",
                metric="acceptance_tests_passed", operator="eq", target=True,
                run_type="system_improvement", evidence_validity="technical_only",
                config={
                    "owner_id": "email", "from_version": "2.0.0",
                    "target_version": "2.0.1",
                    "problem": "isolation probe", "allowed_files": ["email.py"],
                    "acceptance_tests": ["python -m unittest"],
                    "owner_override": True,
                })
            runtime.once(goal["id"])
            runtime.approve(goal["id"])
            blocked = runtime.once(goal["id"])
            task = blocked["change_tasks"][0]
            self.assertEqual([], runtime.store.owner_versions("email"))
            runtime.complete_change(
                task["id"], passed=True,
                result={"passed": True, "commands": ["python -m unittest"]})
            versions = runtime.store.owner_versions("email")
            self.assertEqual(versions[-1]["version"], "2.0.1")
            self.assertEqual(versions[-1]["status"], "tested")

    def test_read_commands_do_not_change_audit_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "company.sqlite"
            runtime = Runtime(db, {"isolation_probe": _ProbeHandler()})
            runtime.create_goal(
                name="Read me", owner_id="isolation_probe", metric="done",
                operator="eq", target=True, config={})
            before = _audit_projection(db)
            captured = io.StringIO()
            with redirect_stdout(captured):
                self.assertEqual(0, main(["--db", str(db), "status"]))
                self.assertEqual(0, main(["--db", str(db), "catalog"]))
                self.assertEqual(0, main(["--db", str(db), "departments"]))
                self.assertEqual(0, main(["--db", str(db), "goal", "list"]))
            self.assertEqual(before, _audit_projection(db))
            self.assertEqual([], Store(db).owner_versions())

    def test_readonly_store_rejects_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "company.sqlite"
            Runtime(db, {"isolation_probe": _ProbeHandler()})
            readonly = Store(db, readonly=True)
            with self.assertRaises(sqlite3.OperationalError):
                readonly.create_goal(
                    name="nope", owner_id="isolation_probe", metric="done",
                    operator="eq", target=True)

    def test_canonical_live_db_write_is_blocked_in_tests(self):
        live = canonical_live_db()
        self.assertTrue(is_canonical_live_db(live))
        with self.assertRaisesRegex(RuntimeError, "cannot open the canonical live"):
            Store(live)
        with self.assertRaisesRegex(RuntimeError, "cannot open the canonical live"):
            Runtime(live, {"isolation_probe": _ProbeHandler()})

    def test_status_and_catalog_leave_live_versions_and_files_unchanged(self):
        live = canonical_live_db()
        if not live.exists():
            self.skipTest("no live company database")
        before_versions = _audit_projection(live)["owner_versions"]
        before_files = _department_fingerprint()
        captured = io.StringIO()
        with redirect_stdout(captured):
            self.assertEqual(0, main(["status"]))
            self.assertEqual(0, main(["catalog"]))
            self.assertEqual(0, main(["departments"]))
        after = _audit_projection(live)
        self.assertEqual(before_versions, after["owner_versions"])
        self.assertEqual(before_files, _department_fingerprint())

    def test_catalog_json_does_not_require_a_runtime(self):
        captured = io.StringIO()
        with redirect_stdout(captured):
            code = main(["catalog"])
        self.assertEqual(0, code)
        payload = json.loads(captured.getvalue())
        self.assertIn("departments", payload)
        self.assertIn("runtime", payload)


class InstallTreeIsolationTests(unittest.TestCase):
    def test_isolated_install_does_not_touch_live_department_tree(self):
        from company.runtime.install import install_department
        from company.tests.test_install import isolated_install_roots

        before = _department_fingerprint()
        with isolated_install_roots() as tree:
            receipt = install_department({
                "id": "iso_ops",
                "purpose": "Isolation sandbox",
                "metrics": ["items"],
                "evidence_sources": ["item_record"],
                "template": "research",
            }, force=True)
            self.assertTrue(receipt["ok"])
            self.assertTrue((tree["departments"] / "iso_ops" / "department.py").is_file())
            self.assertFalse((COMPANY_ROOT / "departments" / "iso_ops").exists())
        self.assertEqual(before, _department_fingerprint())


if __name__ == "__main__":
    unittest.main()
