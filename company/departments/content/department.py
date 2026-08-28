"""Content workflow package."""

from __future__ import annotations

from typing import Any

from .._evidence import EvidenceDepartment
from ..campaign_contract import COMPATIBLE_SCHEMA_VERSIONS, SCHEMA_VERSION, validate_campaign
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


def validate_campaign_package(package: dict[str, Any], prior_packages: list[dict[str, Any]] | None = None) -> list[str]:
    """Validate the current campaign manifest; retired shapes are rejected."""
    if package.get("schema_version") in COMPATIBLE_SCHEMA_VERSIONS:
        return validate_campaign(package, str(package.get("phase") or "strategy"))
    return [f"legacy campaign package is retired; migrate to campaign_contract schema {SCHEMA_VERSION}"]


def _eval_gate_errors(evidence: list[dict[str, Any]], package: dict[str, Any],
                      suite_ids: tuple[str, ...] = ()) -> list[str]:
    """Require one passing report per declared Content suite."""
    errors: list[str] = []
    reports = [item.get("payload") or {} for item in evidence if item.get("kind") == "eval_report"]
    for suite_id in suite_ids:
        matches = [report for report in reports if report.get("suite_id") == suite_id]
        if not matches:
            errors.append(f"eval_report for suite '{suite_id}' is required before content_ready")
            continue
        report = matches[-1]
        if report.get("payload_id") != package.get("batch_id"):
            errors.append(f"eval_report '{suite_id}' payload_id must match batch_id {package.get('batch_id')}")
        if not report.get("overall"):
            failed = [
                f"{item_id}:{criterion_id}"
                for item_id, verdicts in (report.get("per_item") or {}).items()
                for criterion_id, verdict in (verdicts or {}).items()
                if isinstance(verdict, dict) and not verdict.get("pass")
            ]
            errors.append(f"eval_report '{suite_id}' failed: {', '.join(failed[:12]) or 'no criteria passed'}")
    return errors


# Content is the first customer-facing Department in the chain.  It therefore
# opts into a complete, bounded strategy view instead of relying on a worker to
# infer the buyer from a goal name.
CONTENT_STRATEGY_CONTEXT = {
    # The kernel is bounded to eight sections. These topics deliberately keep
    # buyer, category context, voice, and safety in the selected window together.
    "topics": ["buyer", "product", "content", "voice", "writing", "claims", "safety"],
    "scopes": ["content", "all"],
    "layers": ["intent", "model", "policy", "constitution"],
}

_CONTENT_REQUEST_FIELDS = ("icp", "reader", "intent", "topic")
_PLACEHOLDER_STRATEGY_TEXT = (
    "Describe the single buyer",
    "List the audiences you deliberately exclude",
    "Name the category you compete in",
    "One sentence: what changes for the buyer",
)


def _content_request_errors(config: dict[str, Any]) -> list[str]:
    request = config.get("content_request")
    if not isinstance(request, dict):
        return ["content_request is required; include icp, reader, intent, and topic"]
    errors = [f"content_request.{field} is required" for field in _CONTENT_REQUEST_FIELDS
              if not isinstance(request.get(field), str) or not request[field].strip()]
    platforms = request.get("platforms")
    formats = request.get("formats")
    if not isinstance(platforms, list) or not platforms:
        errors.append("content_request.platforms must name at least one platform")
    if not isinstance(formats, list) or not formats:
        errors.append("content_request.formats must name at least one format")
    if request.get("cta_policy", "none") not in {"none", "soft", "conversion"}:
        errors.append("content_request.cta_policy must be none, soft, or conversion")
    if request.get("link_policy", "none") not in {"none", "contextual"}:
        errors.append("content_request.link_policy must be none or contextual")
    return errors


def _strategy_errors(strategy: dict[str, Any]) -> list[str]:
    if not isinstance(strategy, dict):
        return ["selected Strategy context is missing"]
    errors: list[str] = []
    if not strategy.get("state_hash"):
        errors.append("selected Strategy context has no state hash")
    sections = strategy.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("selected Strategy context has no sections")
        return errors
    section_ids = {section.get("id") for section in sections if isinstance(section, dict)}
    for required in ("model.icp.buyer", "policy.voice.one_idea", "policy.voice.copy_shape"):
        if required not in section_ids:
            errors.append(f"selected Strategy context is missing {required}")
    for section in sections:
        text = section.get("content", "") if isinstance(section, dict) else ""
        if any(marker in text for marker in _PLACEHOLDER_STRATEGY_TEXT):
            errors.append("canonical ICP/positioning sources are still placeholders")
            break
    return errors


def _writing_graph(final_kind: str) -> tuple[WorkflowStep, ...]:
    return (
        WorkflowStep("strategy_intake", "machine", produces=("content_intake",)),
        WorkflowStep("worldview", "employee", "content-strategist",
                      requires=("content_intake",), produces=("content_worldview",),
                      skill_ids=("copywriting-en", "copywriting-fa")),
        WorkflowStep("brief", "employee", "content-strategist",
                      requires=("content_worldview",), produces=("content_brief",),
                      skill_ids=("copywriting-en", "copywriting-fa")),
        WorkflowStep("copy", "employee", "content-writer",
                      requires=("content_brief",), produces=("content_copy",),
                      skill_ids=("copywriting-en", "copywriting-fa")),
        WorkflowStep("editorial_review", "machine", requires=("content_copy",),
                      produces=(final_kind, "content_ready", "editorial_report")),
    )


class ContentDepartment(EvidenceDepartment, Department):
    id = department_id = "content"
    version = "4.1.0"
    description = "Reasons from the canonical ICP, writes customer copy, and evaluates it before Design renders it."
    agent_ids = ("content-strategist", "content-writer", "publisher")
    eval_suites = ("content-copy-top10", "content-story-whole")
    production_ready = True
    default_strategy_context = CONTENT_STRATEGY_CONTEXT
    workflows = (
        WorkflowSpec(
            "content-package", "Coordinate one idea across formats.",
            ("strategy", "worldview", "brief", "copy", "editorial_review"),
            ("content-strategist", "content-writer"), ("copywriting-en", "copywriting-fa"),
            (), ("content_intake", "content_worldview", "content_brief", "content_copy",
                 "editorial_report", "content_package", "content_ready"), (),
            graph=_writing_graph("content_package"),
        ),
        WorkflowSpec(
            "social-post", "Create one native post from approved evidence.",
            ("strategy", "worldview", "brief", "copy", "editorial_review"), ("content-writer",),
            ("copywriting-en", "copywriting-fa"), (), ("content_intake", "content_worldview",
             "content_brief", "content_copy", "editorial_report", "content_draft", "content_ready"), (),
            graph=_writing_graph("content_draft"),
        ),
        WorkflowSpec(
            "article", "Create one evidence-backed argument.",
            ("strategy", "worldview", "brief", "copy", "editorial_review"),
            ("content-writer",), ("copywriting-en", "seo"), (), ("content_intake", "content_worldview",
             "content_brief", "content_copy", "editorial_report", "article_draft", "seo_brief"), (),
            graph=_writing_graph("article_draft"),
        ),
        WorkflowSpec(
            "content-campaign", "Write, evaluate, render, then publish one campaign.",
            ("strategy", "worldview", "brief", "copy", "editorial_review", "design_handoff", "approval", "publish"),
            ("content-strategist", "content-writer", "video-producer", "publisher"),
            ("copywriting-en", "copywriting-fa", "video-creation"),
            ("publish",), ("campaign_manifest", "content_ready", "render_report", "publication_receipt"), ("buffer",),
            graph=(
                *(_writing_graph("campaign_manifest")),
                WorkflowStep("quality_gate", "machine", requires=("campaign_manifest",),
                             produces=("content_ready",)),
                WorkflowStep("render_handoff", "employee", "video-producer", requires=("content_ready",),
                             produces=("render_report",), skill_ids=("video-creation",)),
                WorkflowStep("approve", "approval", requires=("render_report",)),
                WorkflowStep("dispatch", "connection", requires=("render_report",), produces=("publication_receipt",),
                             connection_ids=("buffer",)),
            ),
        ),
        WorkflowSpec(
            "publish", "Publish an approved package through a Connection.",
            ("select", "validate", "approve", "dispatch", "verify"), ("publisher",), (),
            ("publish",), ("content_package", "publication_receipt"), ("buffer", "website"),
            graph=(
                WorkflowStep("approve", "approval", requires=("content_package",)),
                WorkflowStep("dispatch", "connection", requires=("content_package",),
                             produces=("publication_receipt",), connection_ids=("buffer", "website")),
            ),
        ),
    )
    goal_schema = {"metrics": ["content_packages", "approved_drafts", "published_items"],
                   "config": {"workflow": {"enum": [w.id for w in workflows]},
                              "required_count": {"type": "integer"},
                              "content_request": {"type": "object"},
                              "strategy_context": {"type": "object"},
                              "connection": {"enum": ["buffer", "website"]},
                              "execution_mode": {"enum": ["dry_run", "live"]}}}
    evidence_metrics = {"content_packages": ("content_package",),
                        "approved_drafts": ("content_draft", "article_draft"),
                        "published_items": ("publication_receipt",)}
    workflow_agents = {"content-package": "content-strategist", "content-campaign": "content-strategist",
                       "social-post": "content-writer", "article": "content-writer", "publish": "publisher"}

    def run_machine_step(self, ctx, decision):
        evidence = list(ctx.cycle.get("evidence") or ())
        step_id = decision.get("step_id")
        if step_id == "strategy_intake":
            errors = _content_request_errors(ctx.goal.config)
            errors.extend(_strategy_errors(ctx.strategy))
            if errors:
                return {
                    "run_status": "blocked",
                    "message": "Content Strategy intake blocked; generic copy is not allowed",
                    "attention": {"errors": errors},
                }
            request = dict(ctx.goal.config["content_request"])
            return {"message": "Content Strategy intake passed", "evidence": [{
                "kind": "content_intake", "source": "content-strategy-intake", "validity": "business",
                "payload": {
                    "icp": request["icp"], "reader": request["reader"],
                    "intent": request["intent"], "topic": request["topic"],
                    "content_request": request,
                    "strategy_state_hash": ctx.strategy.get("state_hash"),
                    "strategy_section_ids": [item.get("id") for item in ctx.strategy.get("sections", [])],
                },
            }]}

        if step_id == "editorial_review":
            copies = [item.get("payload") or {} for item in evidence if item.get("kind") == "content_copy"]
            copy = copies[-1] if copies else {}
            request = ctx.goal.config.get("content_request") or {}
            errors = []
            if not copy:
                errors.append("content_copy is required before editorial review")
            if copy.get("icp") != request.get("icp"):
                errors.append("content_copy must carry the requested ICP exactly")
            if copy.get("reader") != request.get("reader"):
                errors.append("content_copy must carry the requested reader exactly")
            if not isinstance(copy.get("renditions"), dict) or not copy["renditions"]:
                errors.append("content_copy must contain at least one platform rendition")
            if errors:
                return {"run_status": "blocked", "message": "Content editorial review blocked; copy is not ICP-bound",
                        "attention": {"errors": errors}}
            final_kind = {"content-package": "content_package", "social-post": "content_draft",
                          "article": "article_draft", "content-campaign": "campaign_manifest"}.get(
                              decision.get("workflow_id"), "content_package")
            package = {**copy, "content_request": request,
                       "strategy_state_hash": ctx.strategy.get("state_hash"),
                       "editorial_status": "passed"}
            return {"message": "Content editorial review passed", "evidence": [
                {"kind": "editorial_report", "source": "content-editorial-review", "validity": "business",
                 "payload": {"status": "passed", "icp": request.get("icp"), "reader": request.get("reader")}},
                {"kind": final_kind, "source": "content-editorial-review", "validity": "business",
                 "payload": package},
                {"kind": "content_ready", "source": "content-editorial-review", "validity": "business",
                 "payload": {"artifact": package, "strategy_state_hash": ctx.strategy.get("state_hash")}},
            ]}

        if step_id != "quality_gate":
            return {"run_status": "blocked", "message": "Unknown content machine step"}
        packages = [item.get("payload") or {} for item in evidence
                    if item.get("kind") in {"campaign_manifest", "content_package"}]
        package = packages[-1] if packages else {}
        errors = validate_campaign_package(package, packages[:-1])
        errors.extend(_eval_gate_errors(evidence, package, self.eval_suites))
        if errors:
            return {"run_status": "blocked", "message": "Campaign quality gate needs changes", "attention": {"errors": errors}}
        return {"message": "Content editorial review passed", "evidence": [{
            "kind": "content_ready", "source": "content-quality-gate", "validity": "business",
            "payload": {"campaign_id": package.get("campaign_id"), "batch_id": package.get("batch_id"),
                        "campaign_manifest": package, "quality_gate": "passed"},
        }]}
