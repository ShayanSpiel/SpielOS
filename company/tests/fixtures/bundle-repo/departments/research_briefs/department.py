"""Research Briefs Department — turns live customer research into weekly
insight briefs the whole company can act on.

Evidence rules: a brief counts only when it was delivered to the research
store; missing signals stay missing, never zero.
"""

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


class ResearchBriefsDepartment:
    """Declarative research-briefs capability; execution belongs to GoalRuntime."""

    department_id = "research_briefs"
    id = "research_briefs"
    version = "1.0.0"
    description = (
        "Turns live customer research into weekly insight briefs: collects "
        "the week's research signals, writes one decision-ready brief, and "
        "delivers it to the research store."
    )
    agent_ids = ("research-analyst", "brief-writer")
    production_ready = True

    workflows = (
        Workflow(
            "weekly-brief",
            "Produce one delivered weekly insight brief from live research.",
            (
                WorkflowStep(
                    id="collect", agent_id="research-analyst",
                    instruction="Collect this week's research signals "
                                "(interviews, tickets, survey verbatims) "
                                "through the research-store Connection; "
                                "missing signals stay labeled missing, never "
                                "zero. Record {'research_signals': {...}} as "
                                "evidence.",
                    evidence_kind="research_signals",
                    skill_ids=("research_method",),
                    connection_ids=("research_store",)),
                WorkflowStep(
                    id="write", agent_id="brief-writer",
                    instruction="Write one decision-ready brief from the "
                                "collected signals using skills/brief_writing "
                                "and the tone in strategy/brief-voice.md; "
                                "every claim cites its signal. Record "
                                "{'brief_draft': {...}} as evidence.",
                    evidence_kind="brief_draft",
                    skill_ids=("brief_writing",),
                    requirements={"capabilities": ("export_render",)}),
                WorkflowStep(
                    id="deliver", agent_id="brief-writer",
                    instruction="Render the approved brief to markdown with "
                                "the export-render capability and deliver it "
                                "to the research store through the "
                                "research-store Connection. Record "
                                "{'briefs': 1, 'brief_delivered': {...}} as "
                                "evidence.",
                    evidence_kind="brief_delivered",
                    skill_ids=("brief_writing",),
                    connection_ids=("research_store",),
                    requirements={"capabilities": ("export_render",)}),
            ),
            department_id="research_briefs"),
    )

    evidence_metrics = {"briefs": ("brief_delivered",)}
    goal_schema = {
        "metrics": ["briefs"],
        "config": {"workflow": {"enum": ["weekly-brief"]},
                   "required_count": {"type": "integer"}},
    }
    workflow_agents = {"weekly-brief": "brief-writer"}
