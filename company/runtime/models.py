"""Small, stable contract for the one Goal loop and its Departments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ..agents.core import AgentSpec
from ..connections.core import ConnectionSpec


class Stage(str, Enum):
    OBSERVE = "OBSERVE"
    DECIDE = "DECIDE"
    ACT = "ACT"
    EVALUATE = "EVALUATE"


class GoalStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


class RunStatus(str, Enum):
    RUNNING = "running"
    WAITING = "waiting"
    AWAITING_APPROVAL = "awaiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
    IDLE = "idle"
    COMPLETED = "completed"


class RunType(str, Enum):
    BUSINESS_EXPERIMENT = "business_experiment"
    EXECUTION = "execution"
    DIAGNOSTIC = "diagnostic"
    SYSTEM_IMPROVEMENT = "system_improvement"
    EVALUATION = "evaluation"
    SYSTEM_TEST = "system_test"


class ApprovalPolicy(str, Enum):
    """Per-Goal approval mode, stored in ``goal.config["approval_policy"]``.

    - ``PER_ACTION``           — today's behavior: every guarded execute action
                                parks at AWAITING_APPROVAL until approved.
    - ``PER_RUN``              — after the FIRST approval of a Run (cycle),
                                every remaining approval key of that Run reads
                                as "approved"; a new Run starts unapproved.
    - ``EVERYTHING_APPROVED``  — guarded execute actions never park; every key
                                reads as "approved" for the Goal.

    ``per_action`` is the default when the config key is absent.
    """

    PER_ACTION = "per_action"
    PER_RUN = "per_run"
    EVERYTHING_APPROVED = "everything_approved"


class EvidenceValidity(str, Enum):
    BUSINESS = "business"
    TECHNICAL_ONLY = "technical_only"
    CONTAMINATED = "contaminated"
    INVALID = "invalid"


@dataclass(frozen=True)
class RetryPolicy:
    """Per-goal automatic retry for transient ACT failures, from
    ``goal.config["retry_policy"]``.

    - ``max_retries``  — retries AFTER the first failure (total attempts is
                         max_retries + 1).
    - ``backoff_seconds`` — scheduled delay (resume_at) before each retry;
                         never slept through in-process.

    ``from_config`` returns None (no auto-retry) when the key is absent or
    malformed; those goals keep the legacy manual-retry world.
    """

    max_retries: int
    backoff_seconds: float

    @classmethod
    def from_config(cls, config: dict | None) -> "RetryPolicy | None":
        raw = (config or {}).get("retry_policy")
        if not isinstance(raw, dict):
            return None
        try:
            max_retries = int(raw.get("max_retries"))
            backoff_seconds = float(raw.get("backoff_seconds"))
        except (TypeError, ValueError):
            return None
        if max_retries < 0 or backoff_seconds < 0:
            return None
        return cls(max_retries=max_retries, backoff_seconds=backoff_seconds)


@dataclass(frozen=True)
class Goal:
    id: str
    name: str
    owner_id: str
    metric: str
    operator: str
    target: Any
    deadline: str | None
    parent_id: str | None
    goal_status: str
    config: dict[str, Any]


@dataclass(frozen=True)
class GoalContext:
    goal: Goal
    cycle: dict[str, Any]
    memory: tuple[dict[str, Any], ...]
    approval_status: Callable[[str], str | None]
    dispatch_goal: Callable[[str], dict[str, Any]] | None = None
    create_child_goal: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    create_change_task: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    update_change_task: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None
    strategy: dict[str, Any] = field(default_factory=dict)
    directives: tuple[dict[str, Any], ...] = ()


@dataclass
class StageResult:
    step: str
    payload: dict[str, Any] = field(default_factory=dict)
    run_status: RunStatus = RunStatus.RUNNING
    next_stage: Stage | None = None
    goal_status: GoalStatus | None = None
    resume_at: str | None = None
    message: str = ""
    learnings: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    decision: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    next_run: dict[str, Any] | None = None
    attention: dict[str, Any] | None = None


@dataclass(frozen=True)
class WorkflowStep:
    """One Lego node inside a WorkflowSpec graph.

    kind:
      agent      — open a durable work order for an Agent
      approval   — park until runtime approval key "execute"
      connection — host/connection handoff that must record evidence
      machine    — optional pure code hook on the Department
    """

    id: str
    kind: str = "agent"
    agent_id: str | None = None
    produces: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowSpec:
    """A named playbook inside a Department; never a second runtime loop.

    `steps` remains the human-readable playbook labels.
    `graph` is the optional executable Lego chain; when empty the interpreter
    synthesizes one Agent shortfall from agent_ids + evidence_sources.
    """

    id: str
    description: str
    steps: tuple[str, ...]
    agent_ids: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    approval_points: tuple[str, ...] = ()
    evidence_sources: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()
    graph: tuple[WorkflowStep, ...] = ()


class GoalHandler:
    """Internal protocol used by the loop; not a public company building block."""

    id = "base"
    description = ""
    goal_schema: dict[str, Any] = {}
    version = "1.0.0"

    def observe(self, ctx: GoalContext) -> StageResult:
        raise NotImplementedError

    def decide(self, ctx: GoalContext, observation: dict[str, Any]) -> StageResult:
        raise NotImplementedError

    def act(self, ctx: GoalContext, decision: dict[str, Any]) -> StageResult:
        raise NotImplementedError

    def evaluate(self, ctx: GoalContext, action_result: dict[str, Any]) -> StageResult:
        raise NotImplementedError


class Department(GoalHandler):
    """Durable business capability plugged into the one company runtime.

    A portable Department declares:
      - workflows (WorkflowSpec + optional graph)
      - agent_ids / workflow_agents
      - evidence_metrics (metric → accepted evidence kinds)
      - goal_schema (metrics + config enums)

    Execution is supplied by ``runtime.interpreter.InterpretedDepartment``
    unless the Department owns a proven special path.
    """

    department_id = ""
    workflows: tuple[WorkflowSpec, ...] = ()
    agent_ids: tuple[str, ...] = ()
    evidence_metrics: dict = {}
    workflow_agents: dict = {}
