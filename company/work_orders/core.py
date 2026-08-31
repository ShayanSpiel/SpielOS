from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..state import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorkOrder:
    id: str
    goal_id: str
    run_id: str
    intervention_id: str
    agent_id: str
    brief: dict[str, Any]
    status: str
    workflow_run_id: str | None = None
    step_id: str | None = None
    claimed_by: str | None = None
    result: dict[str, Any] | None = None


class WorkOrderRepository:
    def __init__(self, database: Database):
        self.database = database

    def open(self, *, goal_id: str, run_id: str, intervention_id: str,
             agent_id: str, brief: dict, workflow_run_id: str | None = None,
             step_id: str | None = None) -> WorkOrder:
        with self.database.connect() as connection:
            existing = connection.execute("""SELECT id FROM core_work_orders
                WHERE intervention_id=? AND COALESCE(workflow_run_id,'')=COALESCE(?,'')
                  AND COALESCE(step_id,'')=COALESCE(?,'')
                  AND status IN ('open','claimed') ORDER BY created_at DESC LIMIT 1""",
                (intervention_id, workflow_run_id, step_id)).fetchone()
            if existing:
                return self.get(existing[0])
            order_id = f"work-{uuid.uuid4().hex[:12]}"
            stamp = _now()
            connection.execute("""INSERT INTO core_work_orders
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, goal_id, run_id, intervention_id, workflow_run_id,
                 agent_id, step_id, json.dumps(brief), "open", None, None,
                 stamp, stamp))
        return self.get(order_id)

    def get(self, order_id: str) -> WorkOrder:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_work_orders WHERE id=?", (order_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown work order: {order_id}")
        return WorkOrder(row["id"], row["goal_id"], row["run_id"],
                         row["intervention_id"], row["agent_id"],
                         json.loads(row["brief_json"]), row["status"],
                         row["workflow_run_id"], row["step_id"], row["claimed_by"],
                         json.loads(row["result_json"]) if row["result_json"] else None)

    def claim(self, order_id: str, executor_id: str) -> WorkOrder:
        with self.database.connect() as connection:
            changed = connection.execute("""UPDATE core_work_orders
                SET status='claimed',claimed_by=?,updated_at=?
                WHERE id=? AND status='open'""", (executor_id, _now(), order_id)).rowcount
        if changed != 1:
            current = self.get(order_id)
            if current.status == "claimed" and current.claimed_by == executor_id:
                return current
            raise RuntimeError("work order is not open")
        return self.get(order_id)

    def complete(self, order_id: str, result: dict, *, executor_id: str) -> WorkOrder:
        with self.database.connect() as connection:
            changed = connection.execute("""UPDATE core_work_orders
                SET status='completed',result_json=?,updated_at=?
                WHERE id=? AND status='claimed' AND claimed_by=?""",
                (json.dumps(result), _now(), order_id, executor_id)).rowcount
        if changed != 1:
            current = self.get(order_id)
            if current.status == "completed":
                return current
            raise RuntimeError("only the claiming Agent executor can complete a WorkOrder")
        return self.get(order_id)

    def fail(self, order_id: str, error: str, *, executor_id: str) -> WorkOrder:
        with self.database.connect() as connection:
            changed = connection.execute("""UPDATE core_work_orders
                SET status='failed',result_json=?,updated_at=?
                WHERE id=? AND status='claimed' AND claimed_by=?""",
                (json.dumps({"error": error}), _now(), order_id, executor_id)).rowcount
        if changed != 1:
            raise RuntimeError("only the claiming Agent executor can fail a WorkOrder")
        return self.get(order_id)

    def for_workflow_run(self, workflow_run_id: str) -> list[WorkOrder]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute("""SELECT id
                FROM core_work_orders WHERE workflow_run_id=? ORDER BY created_at""",
                (workflow_run_id,))]
        return [self.get(item) for item in ids]
