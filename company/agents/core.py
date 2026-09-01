"""Replaceable Agent execution contract for the clean core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..work_orders import WorkOrder


@dataclass(frozen=True)
class Agent:
    id: str
    description: str = ""
    skill_ids: tuple[str, ...] = ()
    capability_ids: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    connection_ids: tuple[str, ...] = ()


# One Agent identity contract. The old name remains an import alias while
# compatibility modules are retired; it is not a second model.
AgentSpec = Agent


@dataclass(frozen=True)
class AgentResult:
    status: str
    evidence_kind: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    workflow_learning: str | None = None


class AgentExecutor(Protocol):
    """Hosts implement this boundary; business semantics stay unchanged."""

    def execute(self, agent: Agent, order: WorkOrder) -> AgentResult: ...


class FunctionExecutor:
    def __init__(self, functions):
        self.functions = dict(functions)

    def execute(self, agent: Agent, order: WorkOrder) -> AgentResult:
        function = self.functions.get(agent.id)
        if function is None:
            return AgentResult("ask_user", message=f"no executor for Agent {agent.id}")
        result = function(order)
        return result if isinstance(result, AgentResult) else AgentResult(
            "completed", payload=result)
