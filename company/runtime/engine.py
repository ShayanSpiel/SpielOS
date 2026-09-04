"""The clean adaptive Goal loop and restart-safe scheduler boundary."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from ..agents.core import AgentExecutor
from ..context import GoalContext
from ..evidence import EvidenceRepository
from ..goals import Goal, GoalRepository
from ..memory import MemoryRepository
from ..resolution import ResolutionCycle, ResolutionOutcome
from ..resolution.core import InterventionRepository
from ..state import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# After this many consecutive ESCALATE_TO_GOAL outcomes the goal parks for
# the owner instead of churning another run (a deterministic controller
# that re-decides the same failing intervention would otherwise livelock).
ESCALATION_PARK_THRESHOLD = 3
ESCALATION_PARK_MESSAGE = (
    "goal-level decision keeps failing after repeated escalations; "
    "owner input required")


class GoalStage(str, Enum):
    OBSERVE = "OBSERVE"
    DECIDE = "DECIDE"
    ACT = "ACT"
    EVALUATE = "EVALUATE"


@dataclass(frozen=True)
class Decision:
    kind: str
    description: str
    workflow_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evaluation:
    goal_complete: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    strategy_learning: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GoalRun:
    id: str
    goal_id: str
    sequence: int
    stage: GoalStage
    status: str
    observation: dict | None = None
    decision: Decision | None = None
    evaluation: Evaluation | None = None


class GoalController(Protocol):
    def observe(self, context: GoalContext) -> dict: ...
    def decide(self, context: GoalContext, observation: dict) -> Decision: ...
    def evaluate(self, context: GoalContext, decision: Decision,
                 evidence: tuple) -> Evaluation: ...


class RunRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, goal_id: str) -> GoalRun:
        with self.database.connect() as connection:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM core_runs WHERE goal_id=?",
                (goal_id,),
            ).fetchone()[0]
            run_id = f"run-{uuid.uuid4().hex[:12]}"
            stamp = _now()
            connection.execute("""INSERT INTO core_runs
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (run_id, goal_id, sequence, GoalStage.OBSERVE.value, "ready",
                 None, None, None, stamp, stamp))
        return self.get(run_id)

    def get(self, run_id: str) -> GoalRun:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM core_runs WHERE id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown run: {run_id}")
        decision_data = json.loads(row["decision_json"]) if row["decision_json"] else None
        evaluation_data = json.loads(row["evaluation_json"]) if row["evaluation_json"] else None
        return GoalRun(
            row["id"], row["goal_id"], row["sequence"], GoalStage(row["stage"]),
            row["status"],
            json.loads(row["observation_json"]) if row["observation_json"] else None,
            Decision(**decision_data) if decision_data else None,
            Evaluation(**{**evaluation_data,
                          "evidence_ids": tuple(evaluation_data.get("evidence_ids") or ())})
            if evaluation_data else None,
        )

    def current(self, goal_id: str) -> GoalRun:
        with self.database.connect() as connection:
            row = connection.execute("""SELECT id FROM core_runs WHERE goal_id=?
                ORDER BY sequence DESC LIMIT 1""", (goal_id,)).fetchone()
        if row is None:
            raise KeyError(f"goal has no run: {goal_id}")
        return self.get(row[0])

    def update(self, run_id: str, *, stage: GoalStage | None = None,
               status: str | None = None, observation=None, decision=None,
               evaluation=None) -> GoalRun:
        current = self.get(run_id)
        values = {
            "stage": (stage or current.stage).value,
            "status": status or current.status,
            "observation": current.observation if observation is None else observation,
            "decision": current.decision if decision is None else decision,
            "evaluation": current.evaluation if evaluation is None else evaluation,
        }
        def encode(value):
            if value is None:
                return None
            if hasattr(value, "__dict__"):
                value = value.__dict__
            return json.dumps(value)
        with self.database.connect() as connection:
            connection.execute("""UPDATE core_runs SET stage=?,status=?,
                observation_json=?,decision_json=?,evaluation_json=?,updated_at=? WHERE id=?""",
                (values["stage"], values["status"], encode(values["observation"]),
                 encode(values["decision"]), encode(values["evaluation"]), _now(), run_id))
        return self.get(run_id)

    def ready(self) -> list[GoalRun]:
        with self.database.connect() as connection:
            ids = [row[0] for row in connection.execute("""SELECT r.id
                FROM core_runs r JOIN core_goals g ON g.id=r.goal_id
                LEFT JOIN core_goal_metadata m ON m.goal_id=g.id
                WHERE g.status='active' AND r.status IN ('ready','running')
                  AND r.sequence=(SELECT MAX(r2.sequence) FROM core_runs r2
                                  WHERE r2.goal_id=r.goal_id)
                  AND NOT EXISTS (
                    SELECT 1 FROM core_goal_edges e
                    JOIN core_goals prerequisite ON prerequisite.id=e.source_goal_id
                    WHERE e.target_goal_id=g.id AND e.relation='blocks'
                      AND prerequisite.status!='complete')
                ORDER BY CASE json_extract(m.config_json,'$.priority')
                    WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3 WHEN 'deferred' THEN 4 ELSE 2 END,
                    CASE WHEN m.deadline IS NULL THEN 1 ELSE 0 END,m.deadline,
                    r.updated_at,r.id""")]
        return [self.get(item) for item in ids]


class GoalRuntime:
    """Composes isolated repositories; owns only Goal control and scheduling."""

    def __init__(self, path: str | Path, controller: GoalController,
                 executor: AgentExecutor, *, agents=None, max_local_iterations: int = 50,
                 readonly: bool = False):
        self.database = Database(path, readonly=readonly)
        self.controller = controller
        self.goals = GoalRepository(self.database)
        self.runs = RunRepository(self.database)
        self.evidence = EvidenceRepository(self.database)
        self.memory = MemoryRepository(self.database, self.evidence)
        self.resolution = ResolutionCycle(
            self.database, executor, agents=agents,
            max_local_iterations=max_local_iterations)
        self.interventions = InterventionRepository(self.database)

    def create_goal(self, name: str, metric: str, operator: str, target: Any, *,
                    parent_id: str | None = None, goal_id: str | None = None,
                    owner_id: str = "goal-runtime", deadline: str | None = None,
                    config: dict[str, Any] | None = None) -> Goal:
        return self.goals.create_with_initial_run(
            name, metric, operator, target, parent_id=parent_id, goal_id=goal_id,
            owner_id=owner_id, deadline=deadline, config=config)

    def advance(self, goal_id: str) -> dict:
        goal = self.goals.get(goal_id)
        run = self.runs.current(goal_id)
        if goal.status != "active":
            return self.status(goal_id)
        if run.status == "complete":
            # Recover databases written by the pre-1.1 runtime, where a crash
            # could complete a Run before completing its Goal or creating the
            # next Run.
            if run.evaluation and run.evaluation.goal_complete:
                self.goals.set_status(goal.id, "complete")
            else:
                self.runs.create(goal.id)
            return self.status(goal_id)
        context = self._context(goal, run)
        if run.stage == GoalStage.OBSERVE:
            observation = self.controller.observe(context)
            self.runs.update(run.id, stage=GoalStage.DECIDE, status="running",
                             observation=observation)
        elif run.stage == GoalStage.DECIDE:
            decision = self.controller.decide(context, run.observation or {})
            if not isinstance(decision, Decision):
                raise TypeError("GoalController.decide must return Decision")
            self.runs.update(run.id, stage=GoalStage.ACT, status="running",
                             decision=decision)
        elif run.stage == GoalStage.ACT:
            if run.decision is None:
                raise RuntimeError("ACT requires a persisted Goal decision")
            intervention = self.interventions.active_for_run(run.id)
            if intervention is None:
                intervention_context = dict(run.decision.context)
                if run.decision.workflow_id:
                    intervention_context["workflow_id"] = run.decision.workflow_id
                intervention = self.interventions.create(
                    goal_id=goal.id, run_id=run.id, kind=run.decision.kind,
                    description=run.decision.description, context=intervention_context)
            result = self.resolution.resolve(intervention.id)
            self._commit_resolution(goal, run, result)
        else:
            if run.decision is None:
                raise RuntimeError("EVALUATE requires a persisted Goal decision")
            evidence = tuple(self.evidence.for_run(run.id))
            evaluation = self.controller.evaluate(context, run.decision, evidence)
            if not isinstance(evaluation, Evaluation):
                raise TypeError("GoalController.evaluate must return Evaluation")
            if evaluation.strategy_learning and not evaluation.evidence_ids:
                raise ValueError("strategy learning requires evidence from this Run")
            self._commit_evaluation(goal, run, evaluation)
        return self.status(goal_id)

    def _commit_resolution(self, goal: Goal, run: GoalRun, result) -> None:
        stamp = _now()
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT context_json FROM core_interventions WHERE id=?",
                (result.intervention.id,)).fetchone()
            if row is None:
                raise RuntimeError("Resolution Intervention disappeared")
            context = json.loads(row[0])
            context["resolution_message"] = result.message
            if result.outcome == ResolutionOutcome.RETURN_TO_GOAL:
                intervention_status, stage, run_status = "complete", GoalStage.EVALUATE, "running"
            elif result.outcome == ResolutionOutcome.CONTINUE_LOCAL:
                intervention_status, stage, run_status = "running", GoalStage.ACT, "ready"
            elif result.outcome == ResolutionOutcome.ASK_USER:
                intervention_status, stage, run_status = "waiting", GoalStage.ACT, "waiting"
            else:
                intervention_status, stage, run_status = "escalated", GoalStage.ACT, "complete"
            connection.execute("""UPDATE core_interventions
                SET status=?,resolution_outcome=?,context_json=?,updated_at=? WHERE id=?""",
                (intervention_status, result.outcome.value, json.dumps(context), stamp,
                 result.intervention.id))
            if result.outcome == ResolutionOutcome.ESCALATE_TO_GOAL:
                consecutive = self._consecutive_escalations(
                    connection, goal.id, run.sequence) + 1
                if consecutive >= ESCALATION_PARK_THRESHOLD:
                    # Stop the churn: park the run in the ASK_USER shape
                    # (run waiting, no follow-up run) until the owner
                    # answers, instead of opening a fresh run that a
                    # deterministic controller would fail the same way.
                    connection.execute("""UPDATE core_interventions
                        SET status='waiting',context_json=?,updated_at=? WHERE id=?""",
                        (json.dumps(context), stamp, result.intervention.id))
                    connection.execute("""UPDATE core_runs SET status='waiting',
                        updated_at=? WHERE id=?""", (stamp, run.id))
                    connection.execute("""INSERT INTO core_notifications
                        (id,goal_id,run_id,intervention_id,kind,payload_json,status,
                         created_at,acknowledged_at) VALUES (?,?,?,?,?,?,?,?,NULL)
                        ON CONFLICT(intervention_id,kind) DO UPDATE SET
                          payload_json=excluded.payload_json,status='pending',
                          acknowledged_at=NULL""",
                        (f"notification-{uuid.uuid4().hex[:12]}", goal.id, run.id,
                         result.intervention.id, "owner_input_required",
                         json.dumps({"message": ESCALATION_PARK_MESSAGE,
                                     "required_user_action": ESCALATION_PARK_MESSAGE}),
                         "pending", stamp))
                else:
                    evaluation = Evaluation(False, {}, result.message)
                    connection.execute("""UPDATE core_runs SET status='complete',
                        evaluation_json=?,updated_at=? WHERE id=?""",
                        (json.dumps(evaluation.__dict__), stamp, run.id))
                    sequence = connection.execute(
                        "SELECT COALESCE(MAX(sequence),0)+1 FROM core_runs WHERE goal_id=?",
                        (goal.id,)).fetchone()[0]
                    connection.execute("INSERT INTO core_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (f"run-{uuid.uuid4().hex[:12]}", goal.id, sequence,
                         GoalStage.OBSERVE.value, "ready", None, None, None, stamp, stamp))
            else:
                connection.execute("""UPDATE core_runs SET stage=?,status=?,updated_at=?
                    WHERE id=?""", (stage.value, run_status, stamp, run.id))
            if result.outcome == ResolutionOutcome.ASK_USER:
                connection.execute("""INSERT INTO core_notifications
                    (id,goal_id,run_id,intervention_id,kind,payload_json,status,
                     created_at,acknowledged_at) VALUES (?,?,?,?,?,?,?,?,NULL)
                    ON CONFLICT(intervention_id,kind) DO UPDATE SET
                      payload_json=excluded.payload_json,status='pending',
                      acknowledged_at=NULL""",
                    (f"notification-{uuid.uuid4().hex[:12]}", goal.id, run.id,
                     result.intervention.id, "owner_input_required",
                     json.dumps({"message": result.message,
                                 "required_user_action": result.message}),
                     "pending", stamp))

    @staticmethod
    def _consecutive_escalations(connection, goal_id: str, sequence: int) -> int:
        """Count consecutive earlier runs of this goal that ended escalated.

        An escalated run is terminal in ACT (stage never reaches
        EVALUATE): stage='ACT' AND status='complete'. Any run that ended
        another way — an evaluated completion (stage EVALUATE) or a park
        for the owner (status waiting) — breaks the streak, so only
        back-to-back ESCALATE_TO_GOAL completions accumulate.
        """
        rows = connection.execute("""SELECT stage,status FROM core_runs
            WHERE goal_id=? AND sequence<? ORDER BY sequence DESC""",
            (goal_id, sequence)).fetchall()
        streak = 0
        for row in rows:
            if row["stage"] == "ACT" and row["status"] == "complete":
                streak += 1
            else:
                break
        return streak

    def _commit_evaluation(self, goal: Goal, run: GoalRun,
                           evaluation: Evaluation) -> None:
        stamp = _now()
        with self.database.connect() as connection:
            if evaluation.strategy_learning:
                marks = ",".join("?" for _ in evaluation.evidence_ids)
                rows = connection.execute(
                    f"SELECT id FROM core_evidence WHERE run_id=? AND id IN ({marks})",
                    (run.id, *evaluation.evidence_ids)).fetchall()
                if len(rows) != len(evaluation.evidence_ids):
                    raise ValueError("strategy learning evidence must belong to this Run")
                connection.execute("""INSERT INTO core_memory
                    (id,scope,claim,goal_id,run_id,intervention_id,workflow_id,
                     evidence_ids_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (f"memory-{uuid.uuid4().hex[:12]}", "strategy",
                     evaluation.strategy_learning, goal.id, run.id, None, None,
                     json.dumps(evaluation.evidence_ids), stamp))
            connection.execute("""UPDATE core_runs SET status='complete',
                evaluation_json=?,updated_at=? WHERE id=?""",
                (json.dumps(evaluation.__dict__), stamp, run.id))
            if evaluation.goal_complete:
                connection.execute("UPDATE core_goals SET status='complete',updated_at=? WHERE id=?",
                                   (stamp, goal.id))
            else:
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM core_runs WHERE goal_id=?",
                    (goal.id,)).fetchone()[0]
                connection.execute("INSERT INTO core_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"run-{uuid.uuid4().hex[:12]}", goal.id, sequence,
                     GoalStage.OBSERVE.value, "ready", None, None, None, stamp, stamp))

    def resume(self, goal_id: str) -> dict:
        run = self.runs.current(goal_id)
        if run.status == "waiting":
            self.runs.update(run.id, status="ready")
        return self.advance(goal_id)

    def tick(self, max_advances: int = 100) -> dict:
        advanced = []
        for _ in range(max_advances):
            ready = self.runs.ready()
            if not ready:
                break
            progress = False
            for run in ready:
                before = (run.stage, run.status, run.sequence)
                state = self.advance(run.goal_id)
                current = self.runs.current(run.goal_id)
                after = (current.stage, current.status, current.sequence)
                if after != before:
                    progress = True
                    advanced.append(state)
            if not progress:
                break
        return {"advanced": advanced, "quiescent": not self.runs.ready()}

    def status(self, goal_id: str) -> dict:
        goal = self.goals.get(goal_id)
        run = self.runs.current(goal_id)
        intervention = self.interventions.active_for_run(run.id)
        return {"goal": goal, "run": run, "intervention": intervention,
                "evidence": self.evidence.for_run(run.id)}

    def _context(self, goal: Goal, run: GoalRun) -> GoalContext:
        workflow_id = run.decision.workflow_id if run.decision else None
        return GoalContext(
            goal, run.id, tuple(self.evidence.for_goal(goal.id)),
            tuple(self.memory.relevant(goal_id=goal.id, workflow_id=workflow_id)))
