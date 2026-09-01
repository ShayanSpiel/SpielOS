from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..state import Database


@dataclass(frozen=True)
class Evidence:
    id: str
    goal_id: str
    run_id: str
    kind: str
    payload: dict[str, Any]
    intervention_id: str | None = None
    workflow_run_id: str | None = None
    work_order_id: str | None = None


class EvidenceRepository:
    def __init__(self, database: Database):
        self.database = database

    def record(self, *, goal_id: str, run_id: str, kind: str, payload: dict,
               intervention_id: str | None = None,
               workflow_run_id: str | None = None,
               work_order_id: str | None = None) -> Evidence:
        evidence_id = f"evidence-{uuid.uuid4().hex[:12]}"
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO core_evidence VALUES (?,?,?,?,?,?,?,?,?)",
                (evidence_id, goal_id, run_id, intervention_id, workflow_run_id,
                 work_order_id, kind, json.dumps(payload),
                 datetime.now(timezone.utc).isoformat()),
            )
        return self.get(evidence_id)

    def get(self, evidence_id: str) -> Evidence:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_evidence WHERE id=?", (evidence_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown evidence: {evidence_id}")
        return Evidence(row["id"], row["goal_id"], row["run_id"], row["kind"],
                        json.loads(row["payload_json"]), row["intervention_id"],
                        row["workflow_run_id"], row["work_order_id"])

    def for_run(self, run_id: str) -> list[Evidence]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM core_evidence WHERE run_id=? ORDER BY created_at", (run_id,))]
        return [self.get(item) for item in ids]
