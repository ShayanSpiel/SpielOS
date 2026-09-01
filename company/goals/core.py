"""Goal records plus separate parent, support, and blocking relationships."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..state import Database


METRIC_AGGREGATIONS = frozenset({
    "count", "sum", "latest", "max", "min", "boolean_all", "boolean_any",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Goal:
    id: str
    name: str
    metric: str
    operator: str
    target: Any
    parent_id: str | None = None
    status: str = "active"
    owner_id: str = "goal-runtime"
    deadline: str | None = None
    config: dict[str, Any] | None = None
    aggregation: str = "latest"


@dataclass(frozen=True)
class GoalEdge:
    source_goal_id: str
    target_goal_id: str
    relation: str = "supports"


class GoalRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, name: str, metric: str, operator: str, target: Any, *,
               parent_id: str | None = None, goal_id: str | None = None,
               owner_id: str = "goal-runtime", deadline: str | None = None,
               config: dict[str, Any] | None = None) -> Goal:
        goal_id = goal_id or f"goal-{uuid.uuid4().hex[:12]}"
        config = dict(config or {})
        aggregation = config.get("aggregation", "latest")
        if aggregation not in METRIC_AGGREGATIONS:
            raise ValueError(f"invalid Goal metric aggregation: {aggregation}")
        if parent_id:
            self.get(parent_id)
        stamp = _now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO core_goals VALUES (?,?,?,?,?,?,?,?,?)",
                (goal_id, name, metric, operator, json.dumps(target), parent_id,
                 "active", stamp, stamp),
            )
            connection.execute(
                "INSERT INTO core_goal_metadata VALUES (?,?,?,?)",
                (goal_id, owner_id, deadline, json.dumps(config)),
            )
        return self.get(goal_id)

    def create_with_initial_run(self, name: str, metric: str, operator: str,
                                target: Any, *, parent_id: str | None = None,
                                goal_id: str | None = None,
                                owner_id: str = "goal-runtime",
                                deadline: str | None = None,
                                config: dict[str, Any] | None = None) -> Goal:
        """Create a Goal and its first ready Run in one transaction."""

        goal_id = goal_id or f"goal-{uuid.uuid4().hex[:12]}"
        config = dict(config or {})
        aggregation = config.get("aggregation", "latest")
        if aggregation not in METRIC_AGGREGATIONS:
            raise ValueError(f"invalid Goal metric aggregation: {aggregation}")
        if parent_id:
            self.get(parent_id)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        stamp = _now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO core_goals VALUES (?,?,?,?,?,?,?,?,?)",
                (goal_id, name, metric, operator, json.dumps(target), parent_id,
                 "active", stamp, stamp),
            )
            connection.execute(
                "INSERT INTO core_goal_metadata VALUES (?,?,?,?)",
                (goal_id, owner_id, deadline, json.dumps(config)),
            )
            connection.execute("""INSERT INTO core_runs
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (run_id, goal_id, 1, "OBSERVE", "ready", None, None, None,
                 stamp, stamp),
            )
        return self.get(goal_id)

    def get(self, goal_id: str) -> Goal:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT g.*,m.owner_id,m.deadline,m.config_json
                FROM core_goals g LEFT JOIN core_goal_metadata m ON m.goal_id=g.id
                WHERE g.id=?""", (goal_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown goal: {goal_id}")
        config = json.loads(row["config_json"] or "{}")
        aggregation = config.get("aggregation", "latest")
        if aggregation not in METRIC_AGGREGATIONS:
            raise ValueError(f"invalid Goal metric aggregation: {aggregation}")
        return Goal(row["id"], row["name"], row["metric"], row["operator"],
                    json.loads(row["target_json"]), row["parent_id"], row["status"],
                    row["owner_id"] or "goal-runtime", row["deadline"], config,
                    aggregation)

    def list(self) -> list[Goal]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM core_goals ORDER BY created_at, id")]
        return [self.get(goal_id) for goal_id in ids]

    def set_status(self, goal_id: str, status: str) -> Goal:
        if status not in {"active", "complete", "paused", "abandoned"}:
            raise ValueError(f"invalid goal status: {status}")
        with self.database.connect() as connection:
            changed = connection.execute(
                "UPDATE core_goals SET status=?,updated_at=? WHERE id=?",
                (status, _now(), goal_id),
            ).rowcount
        if not changed:
            raise KeyError(f"unknown goal: {goal_id}")
        return self.get(goal_id)

    def set_parent(self, goal_id: str, parent_id: str | None) -> Goal:
        self.get(goal_id)
        if parent_id:
            self.get(parent_id)
            if goal_id == parent_id or goal_id in self._ancestors(parent_id):
                raise ValueError("goal parent would create a tree cycle")
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE core_goals SET parent_id=?,updated_at=? WHERE id=?",
                (parent_id, _now(), goal_id),
            )
        return self.get(goal_id)

    def add_support(self, source_goal_id: str, target_goal_id: str) -> GoalEdge:
        return self._add_edge(source_goal_id, target_goal_id, "supports")

    def add_block(self, source_goal_id: str, target_goal_id: str) -> GoalEdge:
        return self._add_edge(source_goal_id, target_goal_id, "blocks")

    def _add_edge(self, source_goal_id: str, target_goal_id: str,
                  relation: str) -> GoalEdge:
        self.get(source_goal_id)
        self.get(target_goal_id)
        if relation not in {"supports", "blocks"}:
            raise ValueError(f"invalid Goal edge relation: {relation}")
        if (source_goal_id == target_goal_id
                or source_goal_id in self._reachable(target_goal_id, relation)):
            raise ValueError(f"{relation} edge would create a Goal DAG cycle")
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO core_goal_edges VALUES (?,?,?,?)",
                (source_goal_id, target_goal_id, relation, _now()),
            )
        return GoalEdge(source_goal_id, target_goal_id, relation)

    def supports(self, goal_id: str) -> list[Goal]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                """SELECT target_goal_id FROM core_goal_edges
                   WHERE source_goal_id=? AND relation='supports'""",
                (goal_id,),
            )]
        return [self.get(item) for item in ids]

    def supporters(self, goal_id: str) -> list[Goal]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                """SELECT source_goal_id FROM core_goal_edges
                   WHERE target_goal_id=? AND relation='supports'""",
                (goal_id,),
            )]
        return [self.get(item) for item in ids]

    def blocks(self, goal_id: str) -> list[Goal]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                """SELECT target_goal_id FROM core_goal_edges
                   WHERE source_goal_id=? AND relation='blocks'""",
                (goal_id,),
            )]
        return [self.get(item) for item in ids]

    def blockers(self, goal_id: str) -> list[Goal]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute(
                """SELECT source_goal_id FROM core_goal_edges
                   WHERE target_goal_id=? AND relation='blocks'""",
                (goal_id,),
            )]
        return [self.get(item) for item in ids]

    def _ancestors(self, goal_id: str) -> set[str]:
        found: set[str] = set()
        current = self.get(goal_id)
        while current.parent_id:
            if current.parent_id in found:
                break
            found.add(current.parent_id)
            current = self.get(current.parent_id)
        return found

    def _reachable(self, goal_id: str, relation: str) -> set[str]:
        found: set[str] = set()
        frontier = {goal_id}
        with self.database.connect() as connection:
            while frontier:
                marks = ",".join("?" for _ in frontier)
                rows = connection.execute(
                    f"SELECT target_goal_id FROM core_goal_edges "
                    f"WHERE relation=? AND source_goal_id IN ({marks})",
                    (relation, *frontier)
                ).fetchall()
                next_frontier = {row[0] for row in rows} - found
                found |= next_frontier
                frontier = next_frontier
        return found
