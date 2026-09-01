from dataclasses import dataclass

from ..evidence import Evidence
from ..goals import Goal
from ..memory import Memory


@dataclass(frozen=True)
class GoalContext:
    goal: Goal
    run_id: str
    evidence: tuple[Evidence, ...] = ()
    memory: tuple[Memory, ...] = ()
