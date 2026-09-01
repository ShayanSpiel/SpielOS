"""Production Outbound Department over the single company runtime."""

from .email_workflow import EmailWorkflow
from ...runtime.interpreter import InterpretedDepartment
from ...runtime.models import Department, WorkflowSpec, WorkflowStep

BESPOKE_STAGE_EXCEPTIONS = {
    "email-outreach": (
        "EmailWorkflow remains the unattended send path: provider delivery, "
        "approval, inbound evidence windows, and reply measurement."
    ),
}


class OutboundDepartment(EmailWorkflow, Department):
    id = "outbound"
    department_id = "outbound"
    version = "3.3.0"
    description = "Finds and researches qualified prospects, prepares email or social outreach, and measures buyer outcomes."
    deprecated = False
    agent_ids = ("lead-researcher", "social-researcher", "outreach-writer")
    workflows = (
        WorkflowSpec("lead-research", "Discover, qualify, research, and verify ICP-matched prospects.",
                     ("discover", "qualify", "research", "verify", "record"),
                     ("lead-researcher",), ("outbound-email",), (),
                     ("lead_dossier", "verification_result"), ("web-research",),
                     graph=(WorkflowStep("record", "agent", "lead-researcher",
                                         produces=("lead_dossier",),
                                         skill_ids=("outbound-email",),
                                         connection_ids=("web-research",)),)),
        WorkflowSpec("email-outreach", "Compose, validate, approve, send, and measure personalized email.",
                     ("select", "compose", "validate", "approve", "send", "measure"),
                     ("lead-researcher", "outreach-writer"), ("outbound-email", "copywriting"),
                     ("send",), ("provider_events", "reply", "booked_call"),
                     ("email-delivery", "cal-booking", "attio"),
                     graph=(
                         WorkflowStep("send", "connection", "outreach-writer",
                                      produces=("provider_events",),
                                      skill_ids=("outbound-email",),
                                      connection_ids=("email-delivery",)),
                         WorkflowStep("measure", "agent", "lead-researcher",
                                      requires=("provider_events",),
                                      produces=("reply", "booked_call"),
                                      skill_ids=("outbound-email",),
                                      connection_ids=("email-delivery", "cal-booking", "attio")),
                     )),
        WorkflowSpec("social-lead-research", "Research qualified LinkedIn and X prospects from authorized public sources.",
                     ("discover", "qualify", "research", "validate", "record"),
                     ("social-researcher",), ("outbound-email", "outbound"), (),
                     ("social_prospect", "social_signal"), ("web-research",),
                     graph=(WorkflowStep("record", "agent", "social-researcher",
                                         produces=("social_prospect",),
                                         skill_ids=("outbound-email", "outbound"),
                                         connection_ids=("web-research",)),)),
        WorkflowSpec("social-dm", "Create and validate personalized LinkedIn and X DM drafts.",
                     ("select", "draft", "validate", "approve", "export", "measure"),
                     ("social-researcher", "outreach-writer"),
                     ("outbound-email", "copywriting", "copywriting"),
                     ("external_send",), ("dm_draft", "reply", "booked_call"), (),
                     graph=(WorkflowStep("draft", "agent", "outreach-writer",
                                         produces=("dm_draft",),
                                         skill_ids=("outbound-email", "copywriting",
                                                    "copywriting")),)),
    )
    workflow_agents = {
        "lead-research": "lead-researcher",
        "email-outreach": "outreach-writer",
        "social-lead-research": "social-researcher",
        "social-dm": "outreach-writer",
    }
    evidence_metrics = {
        "qualified_social_leads": ("social_prospect",),
        "approved_dm_drafts": ("dm_draft",),
    }
    goal_schema = {
        "metrics": ["reply_rate", "positive_reply_rate", "booked_calls", "sales",
                    "qualified_social_leads", "approved_dm_drafts"],
        "config": {
            **{key: value for key, value in EmailWorkflow.goal_schema["config"].items()
               if key != "execution_mode"},
            "execution_mode": {"enum": ["dry_run", "live"],
                               "required_when": {"workflow": "email-outreach"}},
            "workflow": {"enum": ["email-outreach", "social-lead-research", "social-dm",
                                  "lead-research"]},
            "required_count": {"type": "integer"},
        },
    }

    @staticmethod
    def uses_email_exception(ctx) -> bool:
        return ctx.goal.config.get("workflow", "email-outreach") == "email-outreach"

    def observe(self, ctx):
        if self.uses_email_exception(ctx):
            return EmailWorkflow.observe(self, ctx)
        return InterpretedDepartment.observe(self, ctx)

    def decide(self, ctx, observation):
        if self.uses_email_exception(ctx):
            return EmailWorkflow.decide(self, ctx, observation)
        return InterpretedDepartment.decide(self, ctx, observation)

    def act(self, ctx, decision):
        if self.uses_email_exception(ctx):
            return EmailWorkflow.act(self, ctx, decision)
        return InterpretedDepartment.act(self, ctx, decision)

    def evaluate(self, ctx, action_result):
        if self.uses_email_exception(ctx):
            return EmailWorkflow.evaluate(self, ctx, action_result)
        return InterpretedDepartment.evaluate(self, ctx, action_result)
