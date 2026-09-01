from dataclasses import dataclass

from ..agents.core import Agent, AgentExecutor, AgentResult
from ..work_orders import WorkOrder


@dataclass
class Host:
    """Named adapter. Replacing its executor does not affect Goal semantics."""

    id: str
    executor: AgentExecutor

    def execute(self, agent: Agent, order: WorkOrder) -> AgentResult:
        return self.executor.execute(agent, order)
