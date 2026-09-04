"""Outbound Department — clean migrated declaration (legacy v3.2.1 → clean core).

Migration notes (2026-09-03):

- The legacy OutboundDepartment mixed a bespoke GoalHandler loop
  (EmailWorkflow: observe/decide/act/evaluate) with declarations. In the
  clean core the GoalRuntime owns the loop; the email engine's domain
  operations (providers, compose, validators, policy gates, batches,
  submissions ledger, reply measurement) survive as the ``engine/`` library
  executed by agent-bound steps. The loop code itself is retired with the
  legacy runtime.
- Supabase is the single source of truth for leads (owner directive
  2026-09-02): the master lead list moves from the Desktop ``leads.xlsx``
  (EMAIL_LIST_PATH) to the Supabase ``leads`` table via
  ``company.connections.supabase``. Send/reply/bounce events append to
  ``email_events``; lead flags roll up on the same row.
- Live sends always park for owner approval (approval key ``send``); the
  provider pool (Resend/Mailgun/Postmark/Brevo/EmailOctopus) runs behind
  the ``email-delivery`` Connection.
- ``crm_sync`` (Attio) and ``calcom_sync`` (Cal.com) survive as library
  adapters behind the ``attio`` / ``cal-booking`` Connections.
"""

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


def _step(step_id: str, agent_id: str, instruction: str, *,
          evidence_kind: str | None = None, approval_key: str | None = None,
          skill_ids: tuple[str, ...] = (), connection_ids: tuple[str, ...] = (),
          requirements: dict | None = None) -> WorkflowStep:
    return WorkflowStep(
        id=step_id, agent_id=agent_id, instruction=instruction,
        evidence_kind=evidence_kind, approval_key=approval_key,
        skill_ids=skill_ids, connection_ids=connection_ids,
        requirements=requirements or {})


class OutboundDepartment:
    """Declarative outbound capability; execution belongs to GoalRuntime."""

    department_id = "outbound"
    id = "outbound"
    version = "4.0.0"
    description = (
        "Finds and researches qualified prospects, prepares email or social "
        "outreach, and measures buyer outcomes."
    )
    agent_ids = ("lead-researcher", "social-researcher", "outreach-writer")
    production_ready = True

    workflows = (
        Workflow(
            "lead-research",
            "Discover, qualify, research, and verify ICP-matched prospects.",
            (
                _step("discover", "lead-researcher",
                      "Discover candidate prospects from permitted public "
                      "sources (web-research); never scrape gated data.",
                      skill_ids=("outbound-email",),
                      connection_ids=("web-research",)),
                _step("qualify", "lead-researcher",
                      "Qualify each candidate against the canonical ICP "
                      "(strategy/icp.md); reject non-ICP with reasons.",
                      skill_ids=("outbound-email",)),
                _step("research", "lead-researcher",
                      "Research one operative fact per lead and its "
                      "operational consequence (the personalization hook "
                      "must be evidence, not invention).",
                      skill_ids=("outbound-email",),
                      connection_ids=("web-research",)),
                _step("verify", "lead-researcher",
                      "Verify the lead identity (email/domain validity, "
                      "role, company).",
                      evidence_kind="verification_result",
                      skill_ids=("outbound-email",)),
                _step("record", "lead-researcher",
                      "Record the lead in Supabase: upsert on lead_key "
                      "(email > company_domain > normalized company) into "
                      "the ``leads`` table with research fields; record "
                      "evidence {'lead_dossier': {...}}. No CSVs, no local "
                      "lead lists.",
                      evidence_kind="lead_dossier",
                      skill_ids=("outbound-email", "crm"),
                      connection_ids=("supabase",)),
            ),
            department_id="outbound",
        ),
        Workflow(
            "email-outreach",
            "Compose, validate, approve, send, and measure personalized email.",
            (
                _step("select", "lead-researcher",
                      "Select eligible leads from the Supabase ``leads`` "
                      "table (sequence_status, outreach_tier, email_status, "
                      "12h submission cooldown, per-goal cohort filters).",
                      skill_ids=("outbound-email",),
                      connection_ids=("supabase",)),
                _step("compose", "outreach-writer",
                      "Compose personalized email per lead from its research "
                      "fact and pain hypothesis (engine/compose rules; "
                      "hook + pain + earned CTA, no invented claims).",
                      skill_ids=("outbound-email", "copywriting")),
                _step("validate", "outreach-writer",
                      "Run the engine validators (address parse, forbidden "
                      "content, template fit) and the policy gate "
                      "(policy_rules on fresh data right before send).",
                      skill_ids=("outbound-email",)),
                _step("approve", "outreach-writer",
                      "Park for owner approval before any live send "
                      "(approval key 'send'; dry_run bypasses nothing — "
                      "live mode still parks).",
                      approval_key="send"),
                _step("send", "outreach-writer",
                      "Execute the approved batch through the provider "
                      "pool (email-delivery Connection: block size, "
                      "throttle, per-provider daily caps) and record the "
                      "provider_events evidence + append ``sent`` events to "
                      "Supabase email_events.",
                      evidence_kind="provider_events",
                      skill_ids=("outbound-email",),
                      connection_ids=("email-delivery", "supabase")),
                _step("measure", "lead-researcher",
                      "Measure through the evidence window (opens, clicks, "
                      "delivery, replies via gmail-inbox capture; bounces) "
                      "and append events to Supabase; roll up lead flags; "
                      "record evidence {'reply': ..., 'booked_call': ...} "
                      "and the batch metrics.",
                      evidence_kind="reply",
                      skill_ids=("outbound-email", "analytics"),
                      connection_ids=("gmail-inbox", "supabase")),
            ),
            department_id="outbound",
        ),
        Workflow(
            "social-lead-research",
            "Research qualified LinkedIn and X prospects from authorized "
            "public sources.",
            (
                _step("discover", "social-researcher",
                      "Discover public LinkedIn/X signals for ICP-matched "
                      "prospects.",
                      skill_ids=("outbound-email", "outbound"),
                      connection_ids=("web-research",)),
                _step("qualify", "social-researcher",
                      "Qualify against the canonical ICP.",
                      skill_ids=("outbound",)),
                _step("research", "social-researcher",
                      "Collect the social signal (visible problem, buying "
                      "signal) with source URLs.",
                      skill_ids=("outbound",),
                      connection_ids=("web-research",)),
                _step("validate", "social-researcher",
                      "Validate the evidence chain (public sources only).",
                      skill_ids=("outbound",)),
                _step("record", "social-researcher",
                      "Upsert the social prospect into Supabase ``leads`` "
                      "(profile_url, buying_signals) and record evidence "
                      "{'social_prospect': {...}}.",
                      evidence_kind="social_prospect",
                      skill_ids=("outbound", "crm"),
                      connection_ids=("supabase",)),
            ),
            department_id="outbound",
        ),
        Workflow(
            "social-dm",
            "Create and validate personalized LinkedIn and X DM drafts.",
            (
                _step("select", "social-researcher",
                      "Select the lead for a DM from Supabase (channel, "
                      "sequence status).",
                      skill_ids=("outbound",),
                      connection_ids=("supabase",)),
                _step("draft", "outreach-writer",
                      "Draft the personalized DM (one idea, human, "
                      "platform-native).",
                      evidence_kind="dm_draft",
                      skill_ids=("outbound-email", "copywriting")),
                _step("validate", "outreach-writer",
                      "Validate the draft (length, tone, claims, ICP fit).",
                      skill_ids=("outbound",)),
                _step("approve", "outreach-writer",
                      "Park for owner approval before any external send "
                      "(approval key 'external_send').",
                      approval_key="external_send"),
                _step("export", "outreach-writer",
                      "Export the approved DM draft for manual/browser "
                      "delivery (never auto-send on social platforms).",
                      skill_ids=("outbound",)),
                _step("measure", "outreach-writer",
                      "Record replies/booked calls as evidence and in "
                      "Supabase events.",
                      evidence_kind="reply",
                      skill_ids=("outbound",),
                      connection_ids=("supabase",)),
            ),
            department_id="outbound",
        ),
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
        "lead_dossiers": ("lead_dossier",),
        "email_batches_sent": ("provider_events",),
        "replies": ("reply",),
    }

    goal_schema = {
        "metrics": ["reply_rate", "positive_reply_rate", "booked_calls",
                    "sales", "qualified_social_leads", "approved_dm_drafts",
                    "lead_dossiers", "email_batches_sent", "replies"],
        "config": {
            "execution_mode": {"enum": ["dry_run", "live"],
                               "required_when": {"workflow": "email-outreach"}},
            "workflow": {"enum": ["email-outreach", "social-lead-research",
                                   "social-dm", "lead-research"]},
            "required_count": {"type": "integer"},
            "batch_size": {"type": "integer",
                           "description": "Required eligible leads for one "
                                          "complete run"},
            "evidence_window_hours": {"type": "number",
                                      "required_when": {"execution_mode": "live"}},
            "knobs": {"type": "object",
                      "description": "Per-goal overrides of Outbound "
                                     "campaign knobs"},
            "audience_type": {"enum": ["business", "test_inbox"]},
            "test_recipients": {"type": "array",
                                "required_when": {"audience_type": "test_inbox"}},
            "reply_capture": {"enum": ["manual_inbox", "resend_inbound",
                                       "gmail_inbox"]},
        },
    }
