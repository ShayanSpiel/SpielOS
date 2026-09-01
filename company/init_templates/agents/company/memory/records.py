from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from ..evidence import EvidenceRepository
from ..state import Database


@dataclass(frozen=True)
class Memory:
    id: str
    scope: str
    claim: str
    evidence_ids: tuple[str, ...]
    goal_id: str | None = None
    run_id: str | None = None
    intervention_id: str | None = None
    workflow_id: str | None = None


class MemoryRepository:
    def __init__(self, database: Database, evidence: EvidenceRepository):
        self.database = database
        self.evidence = evidence

    def remember(self, scope: str, claim: str, *, evidence_ids=(), goal_id=None,
                 run_id=None, intervention_id=None, workflow_id=None) -> Memory:
        if scope not in {"owner", "workflow", "strategy"}:
            raise ValueError(f"invalid memory scope: {scope}")
        ids = tuple(dict.fromkeys(evidence_ids))
        if scope != "owner" and not ids:
            raise ValueError(f"{scope} memory requires evidence")
        records = [self.evidence.get(item) for item in ids]
        if run_id and any(item.run_id != run_id for item in records):
            raise ValueError("memory evidence must belong to its causal run")
        memory_id = f"memory-{uuid.uuid4().hex[:12]}"
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO core_memory VALUES (?,?,?,?,?,?,?,?,?)",
                (memory_id, scope, claim, goal_id, run_id, intervention_id,
                 workflow_id, json.dumps(ids), datetime.now(timezone.utc).isoformat()),
            )
        return self.get(memory_id)

    def get(self, memory_id: str) -> Memory:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_memory WHERE id=?", (memory_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown memory: {memory_id}")
        return Memory(row["id"], row["scope"], row["claim"],
                      tuple(json.loads(row["evidence_ids_json"])), row["goal_id"],
                      row["run_id"], row["intervention_id"], row["workflow_id"])

    def relevant(self, *, goal_id: str | None = None,
                 workflow_id: str | None = None) -> list[Memory]:
        clauses, values = [], []
        if goal_id:
            clauses.append("(goal_id=? OR scope='owner')")
            values.append(goal_id)
        if workflow_id:
            clauses.append("(workflow_id=? OR workflow_id IS NULL)")
            values.append(workflow_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM core_memory" + where + " ORDER BY created_at DESC", values)]
        return [self.get(item) for item in ids]
