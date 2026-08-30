"""Small, stable contract for the one Goal loop and Worker-owned Workgroups."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


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
      employee   — open a durable work order for an employee
      approval   — park until runtime approval key "execute"
      connection — host/connection handoff that must record evidence
      machine    — optional pure code hook on the Workgroup adapter
    """

    id: str
    kind: str = "employee"
    employee_id: str | None = None
    produces: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    skill_ids: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkflowSpec:
    """A named playbook inside a Workgroup; never a second runtime loop.

    `steps` remains the human-readable playbook labels.
    `graph` is the optional executable Lego chain; when empty the interpreter
    synthesizes one employee shortfall from agents + evidence_sources.
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


@dataclass(frozen=True)
class AgentSpec:
    """A bounded executor identity used by one or more workflow steps."""

    id: str
    description: str
    skill_ids: tuple[str, ...]
    permissions: tuple[str, ...]
    produces: tuple[str, ...]


@dataclass(frozen=True)
class WorkerSpec(AgentSpec):
    """A Worker owns executable workflows inside one Workgroup.

    ``AgentSpec`` remains the compatibility name for older installed rosters.
    New package code should use WorkerSpec: an identity, its workbook methods,
    its workkit permissions, and the workflows for which it is the lead.
    """

    workgroup_id: str = ""
    workflows: tuple[WorkflowSpec, ...] = ()


@dataclass(frozen=True)
class WorkgroupSpec:
    """Human-facing grouping and routing metadata; never an executor itself."""

    id: str
    version: str
    description: str
    workers: tuple[WorkerSpec, ...]
    metrics: tuple[str, ...] = ()
    config_schema: dict[str, Any] = field(default_factory=dict)
    evidence_metrics: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectionSpec:
    """Logical access to an external system, resolved by the active host."""

    id: str
    description: str
    capabilities: tuple[str, ...]
    hosts: tuple[str, ...] = ("codex", "opencode")
    unattended: bool = False
    required_environment: tuple[str, ...] = ()


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


class WorkgroupHandlerBase(GoalHandler):
    """Internal loop adapter for one declarative Workgroup package.

    A Workgroup package declares:
      - workflows (WorkflowSpec + optional graph)
      - agent_ids / workflow_agents
      - evidence_metrics (metric → accepted evidence kinds)
      - goal_schema (metrics + config enums)

    Execution is supplied by ``runtime.interpreter.InterpretedWorkgroup``.
    """

    workgroup_id = ""
    workflows: tuple[WorkflowSpec, ...] = ()
    agent_ids: tuple[str, ...] = ()
    evidence_metrics: dict = {}
    workflow_agents: dict = {}
