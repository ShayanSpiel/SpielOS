"""Outbound domain data contracts shared by workflows and reporting.

Domain-free: nothing here knows about email, content, or any channel. The
loop vocabulary (Phase) and the workflow vocabulary (Lead, Action, Goal)
live in one place so the Department and its workflows never disagree.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Phase(str, Enum):
    """The loop's state machine.

    OBSERVE -> DECIDE -> ACT (PREPARE -> VALIDATE -> GATE -> REVIEW ->
    EXECUTE) -> EVALUATE closes one batch cycle; HOLD parks the loop for a
    human or an external condition; GOAL_MET / STOPPED are terminal.
    """

    OBSERVE = "observe"
    DECIDE = "decide"
    PREPARE = "prepare"
    VALIDATE = "validate"
    GATE = "gate"
    REVIEW = "review"
    EXECUTE = "execute"
    EVALUATE = "evaluate"
    HOLD = "hold"
    GOAL_MET = "goal_met"
    STOPPED = "stopped"


class LeadState(str, Enum):
    DISCOVERED = "discovered"
    QUALIFIED = "qualified"
    RESEARCHED = "researched"
    READY = "ready"
    ACTION_PENDING = "action_pending"
    ACTIONED = "actioned"
    REPLIED = "replied"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    DO_NOT_CONTACT = "do_not_contact"


class Action(str, Enum):
    RESEARCH = "research"
    QUALIFY = "qualify"
    DRAFT = "draft"
    SEND_EMAIL = "send_email"
    SEND_DM = "send_dm"
    SEND_CONNECTION = "send_connection"
    PUBLISH = "publish"
    RECORD_REPLY = "record_reply"


@dataclass
class Lead:
    lead_id: str
    name: str
    company: str
    role: str = ""
    location: str = ""
    channels: list[str] = field(default_factory=list)
    profile_url: str = ""
    company_url: str = ""
    state: LeadState = LeadState.DISCOVERED
    icp_score: int = 0
    research_fact: str = ""
    operational_consequence: str = ""
    message: str = ""
    source_urls: list[str] = field(default_factory=list)
    exclusion_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowGoal:
    workflow_id: str
    channel: str
    action: str
    target: int
    min_icp_score: int = 75
    queue_target: int = 100
    enabled: bool = True
