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
    confidence: float = 1.0
    status: str = "active"
    supersedes_id: str | None = None


class MemoryRepository:
    def __init__(self, database: Database, evidence: EvidenceRepository):
        self.database = database
        self.evidence = evidence

    def remember(self, scope: str, claim: str, *, evidence_ids=(), goal_id=None,
                 run_id=None, intervention_id=None, workflow_id=None,
                 confidence: float = 1.0, supersedes_id: str | None = None) -> Memory:
        if scope not in {"owner", "workflow", "strategy"}:
            raise ValueError(f"invalid memory scope: {scope}")
        ids = tuple(dict.fromkeys(evidence_ids))
        if scope != "owner" and not ids:
            raise ValueError(f"{scope} memory requires evidence")
        if scope != "owner" and (not goal_id or not run_id):
            raise ValueError(f"{scope} memory requires Goal and Run lineage")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("memory confidence must be between 0.0 and 1.0")
        superseded = self.get(supersedes_id) if supersedes_id else None
        if superseded is not None and superseded.scope != scope:
            raise ValueError("memory can supersede only the same scope")
        records = [self.evidence.get(item) for item in ids]
        if goal_id and any(item.goal_id != goal_id for item in records):
            raise ValueError("memory evidence must belong to its causal Goal")
        if run_id and any(item.run_id != run_id for item in records):
            raise ValueError("memory evidence must belong to its causal run")
        if intervention_id and any(
                item.intervention_id != intervention_id for item in records):
            raise ValueError("memory evidence must belong to its causal Intervention")
        memory_id = f"memory-{uuid.uuid4().hex[:12]}"
        with self.database.connect() as connection:
            if superseded is not None:
                connection.execute("""UPDATE core_memory SET status='superseded'
                    WHERE id=? AND status='active'""", (superseded.id,))
            connection.execute("""INSERT INTO core_memory
                (id,scope,claim,goal_id,run_id,intervention_id,workflow_id,
                 evidence_ids_json,created_at,confidence,status,supersedes_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (memory_id, scope, claim, goal_id, run_id, intervention_id,
                 workflow_id, json.dumps(ids), datetime.now(timezone.utc).isoformat(),
                 confidence, "active", supersedes_id))
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
                      row["run_id"], row["intervention_id"], row["workflow_id"],
                      row["confidence"], row["status"], row["supersedes_id"])

    def relevant(self, *, limit: int = 20, scope: str | None = None,
                 goal_id: str | None = None,
                 workflow_id: str | None = None) -> list[Memory]:
        if limit < 1:
            return []
        if scope is not None and scope not in {"owner", "workflow", "strategy"}:
            raise ValueError(f"invalid memory scope: {scope}")
        clauses, values = ["status='active'"], []
        applicable = ["scope='owner'"]
        if goal_id:
            applicable.append("(scope='strategy' AND goal_id=?)")
            values.append(goal_id)
        if workflow_id:
            applicable.append("(scope='workflow' AND workflow_id=?)")
            values.append(workflow_id)
        clauses.append("(" + " OR ".join(applicable) + ")")
        if scope:
            clauses.append("scope=?")
            values.append(scope)
        values.append(limit)
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                """SELECT id FROM core_memory WHERE """ + " AND ".join(clauses) + """
                ORDER BY CASE scope WHEN 'owner' THEN 0 WHEN 'workflow' THEN 1 ELSE 2 END,
                         created_at DESC LIMIT ?""", values)]
        return [self.get(item) for item in ids]
