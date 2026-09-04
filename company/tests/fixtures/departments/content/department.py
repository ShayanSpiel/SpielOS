"""Content Department — clean migrated declaration (legacy v4.3.0 → clean core).

Migration notes (2026-09-03):
- Legacy ``campaign_contract`` (schema 1.2, shared with Design/Analytics)
  stays a shared department-layer module at ``departments/campaign_contract.py``.
- Legacy machine step ``quality_gate`` becomes a real agent step bound to
  the content-strategist that runs the campaign-contract validation and the
  two eval suites mechanically (the validation code is pure functions in
  ``content/gates.py``; no runtime loop).
- ``platform_edit`` → ``campaign_manifest``/``design_order`` handoff and
  the Buffer dispatch with publication-receipt contract are preserved.
- Evidence kinds and metric names are unchanged so measurement stays
  comparable across the migration.
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


class ContentDepartment:
    """Declarative content capability; execution belongs to GoalRuntime."""

    department_id = "content"
    id = "content"
    version = "4.4.0"
    description = (
        "Preserves simulated work scenes and discoveries through drafting, "
        "editorial gate, Design handoff, approval, and delivery."
    )
    agent_ids = ("content-strategist", "content-writer", "publisher",
                 "video-producer")
    eval_suites = ("content-copy-top10", "content-story-whole")
    production_ready = True

    workflows = (
        Workflow(
            "content-package",
            "Coordinate one evidence-backed topic idea across formats.",
            (
                _step("evidence", "content-strategist",
                      "Collect the company evidence (live record, delivered "
                      "work, funnel facts) the idea will stand on; no "
                      "invented facts.",
                      evidence_kind="company_evidence",
                      skill_ids=("copywriting",)),
                _step("idea_lock", "content-strategist",
                      "Lock one buyer-relevant idea and its ICP reader "
                      "before any copy is written.",
                      skill_ids=("copywriting",)),
                _step("brief", "content-strategist",
                      "Write the brief (reader, moment, idea, proof, CTA) "
                      "from the locked idea.",
                      skill_ids=("copywriting",)),
                _step("produce", "content-writer",
                      "Produce the drafts for the chosen formats from the "
                      "brief.",
                      skill_ids=("copywriting",)),
                _step("review", "content-strategist",
                      "Editorial review against copywriting + voice rules.",
                      skill_ids=("copywriting",)),
                _step("package", "content-strategist",
                      "Package the approved content and record evidence "
                      "{'content_package': {...}, 'content_packages': <int>}.",
                      evidence_kind="content_package",
                      skill_ids=("copywriting",)),
            ),
            department_id="content",
        ),
        Workflow(
            "social-post",
            "Create a one-idea platform-native post from approved evidence.",
            (
                _step("idea_lock", "content-writer",
                      "Lock the one idea and its reader moment.",
                      skill_ids=("copywriting",)),
                _step("brief", "content-writer",
                      "Write the platform-native brief.",
                      skill_ids=("copywriting",)),
                _step("draft", "content-writer",
                      "Draft the post and record evidence "
                      "{'content_draft': {...}}.",
                      evidence_kind="content_draft",
                      skill_ids=("copywriting",)),
                _step("edit", "content-writer",
                      "Edit for platform fit and brevity.",
                      skill_ids=("copywriting",)),
                _step("approve", "content-writer",
                      "Final self-review against voice and ICP; the "
                      "publish workflow still parks for owner approval.",
                      skill_ids=("copywriting",)),
            ),
            department_id="content",
        ),
        Workflow(
            "article",
            "Create one evidence-backed, search-aware argument.",
            (
                _step("idea_lock", "content-writer",
                      "Lock the argument's one idea and search intent.",
                      skill_ids=("copywriting", "seo")),
                _step("brief", "content-writer",
                      "Write the article brief (claim, proof structure, "
                      "target query).",
                      skill_ids=("copywriting", "seo")),
                _step("draft", "content-writer",
                      "Draft the article and record evidence "
                      "{'article_draft': {...}}.",
                      evidence_kind="article_draft",
                      skill_ids=("copywriting", "seo")),
                _step("edit", "content-writer",
                      "Edit for clarity, flow, and voice.",
                      skill_ids=("copywriting",)),
                _step("seo_review", "content-writer",
                      "SEO review per the SEO skill invariants (title, "
                      "description, internal links, intent match).",
                      skill_ids=("seo",)),
                _step("approve", "content-writer",
                      "Final review; publishing still parks for owner "
                      "approval in the publish workflow.",
                      skill_ids=("copywriting",)),
            ),
            department_id="content",
        ),
        Workflow(
            "content-campaign",
            "Preserve the work scene and discovery before drafting, then "
            "edit for platform, Design, approval, delivery, and measurement. "
            "publication_receipt is final; scheduled or sent is a commitment.",
            (
                _step("simulation", "content-strategist",
                      "Record the reader, situation, mechanism, consequence, "
                      "proof, and discovery before any copy exists.",
                      evidence_kind="simulation",
                      skill_ids=("copywriting",)),
                _step("human_reality", "content-strategist",
                      "Preserve the human scene: what the person checks, "
                      "copies, switches between, waits for, fixes, and "
                      "remembers.",
                      evidence_kind="human_reality",
                      skill_ids=("copywriting",)),
                _step("discovery", "content-strategist",
                      "Add the derived insight without replacing or "
                      "compressing the simulation or human reality.",
                      evidence_kind="discovery",
                      skill_ids=("copywriting",)),
                _step("draft", "content-writer",
                      "Draft from the simulation + human reality + "
                      "discovery as separate inputs; the first paragraph "
                      "comes from the preserved scene.",
                      evidence_kind="content_draft",
                      skill_ids=("copywriting",)),
                _step("platform_edit", "content-writer",
                      "Edit for Threads/YouTube platform fit: length, "
                      "pacing, formatting — never rewrite into a generic "
                      "hook/proof/CTA sequence. Produce the "
                      "campaign_manifest and design_order handoff.",
                      evidence_kind="campaign_manifest",
                      skill_ids=("copywriting",)),
                _step("quality_gate", "content-strategist",
                      "Mechanical gate: validate the campaign package "
                      "against departments/campaign_contract.py (schema 1.2) "
                      "and require passing eval reports for suites "
                      "'content-copy-top10' and 'content-story-whole' "
                      "(payload_id must equal batch_id). On success record "
                      "evidence {'content_ready': ..., 'campaign_ready': ...}.",
                      evidence_kind="campaign_ready",
                      skill_ids=("copywriting",),
                      requirements={"gate": "campaign_contract + eval suites"}),
                _step("render_handoff", "video-producer",
                      "Hand the design_order to Design/rendering without "
                      "changing the copy's substance; record the "
                      "render_report.",
                      evidence_kind="render_report",
                      skill_ids=("videography",),
                      requirements={"requires": ["content_ready", "design_order"]}),
                _step("approve", "content-strategist",
                      "Park for owner approval before dispatch "
                      "(approval key 'publish').",
                      approval_key="publish"),
                _step("dispatch", "publisher",
                      "Dispatch the approved package through the buffer "
                      "Connection (social: threads/youtube-shorts) and record "
                      "the publication_receipt (scheduled or sent is a "
                      "commitment). Regular 16:9 YouTube publishes with "
                      "custom thumbnails go through the youtube Connection "
                      "(owner-authorized OAuth, scope youtube.upload only) "
                      "instead of Buffer.",
                      evidence_kind="publication_receipt",
                      skill_ids=("devto-publisher",),
                      connection_ids=("buffer", "youtube")),
                _step("measure", "publisher",
                      "Measure the campaign through the posthog/analytics "
                      "evidence (funnel metrics from campaign_contract).",
                      skill_ids=("analytics",),
                      connection_ids=("posthog",)),
                _step("evaluate", "content-strategist",
                      "Evaluate: apply the funnel report and record the "
                      "optimization decision (one to three "
                      "evidence-supported next changes).",
                      skill_ids=("copywriting", "analytics")),
            ),
            department_id="content",
        ),
        Workflow(
            "publish",
            "Publish or schedule an approved package through a Connection.",
            (
                _step("select", "publisher",
                      "Select the approved content_package to publish.",
                      skill_ids=("devto-publisher",)),
                _step("validate", "publisher",
                      "Validate the package against the publication "
                      "contract (campaign phase, asset URLs, tracked "
                      "destinations).",
                      skill_ids=("devto-publisher",)),
                _step("approve", "publisher",
                      "Park for owner approval before anything goes live "
                      "(approval key 'publish').",
                      approval_key="publish"),
                _step("dispatch", "publisher",
                      "Dispatch through the buffer, website, or youtube "
                      "Connection (regular 16:9 YouTube publishes use the "
                      "youtube OAuth connection with custom 1280x720 "
                      "thumbnails) and record the publication_receipt.",
                      evidence_kind="publication_receipt",
                      skill_ids=("devto-publisher",),
                      connection_ids=("buffer", "website", "youtube")),
                _step("verify", "publisher",
                      "Verify the published/scheduled state on the "
                      "platform and report links and timestamps.",
                      skill_ids=("devto-publisher",),
                      connection_ids=("buffer", "website", "youtube")),
            ),
            department_id="content",
        ),
    )

    evidence_metrics = {
        "content_packages": ("content_package",),
        "approved_drafts": ("content_draft", "article_draft"),
        "published_items": ("publication_receipt",),
    }

    goal_schema = {
        "metrics": ["content_packages", "approved_drafts", "published_items"],
        "config": {
            "workflow": {"enum": ["content-package", "social-post", "article",
                                  "content-campaign", "publish"]},
            "required_count": {"type": "integer"},
            "connection": {"enum": ["buffer", "website"]},
            "execution_mode": {"enum": ["dry_run", "live"]},
        },
    }

    workflow_agents = {
        "content-package": "content-strategist",
        "content-campaign": "content-strategist",
        "social-post": "content-writer",
        "article": "content-writer",
        "publish": "publisher",
    }
