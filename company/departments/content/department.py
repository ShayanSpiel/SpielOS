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


class ContentDepartment(EvidenceDepartment, Department):
    id = department_id = "content"
    version = "4.0.0"
    description = "Writes and evaluates one customer message before Design renders it."
    agent_ids = ("content-strategist", "content-writer", "publisher")
    eval_suites = ("content-copy-top10", "content-story-whole")
    production_ready = True
    workflows = (
        WorkflowSpec(
            "content-package", "Coordinate one idea across formats.",
            ("evidence", "idea_lock", "brief", "produce", "review", "package"),
            ("content-strategist", "content-writer"), ("copywriting-en", "copywriting-fa"),
            (), ("company_evidence", "content_package"), (),
            graph=(WorkflowStep("package", "employee", "content-strategist", produces=("content_package",),
                                skill_ids=("copywriting-en", "copywriting-fa")),),
        ),
        WorkflowSpec(
            "social-post", "Create one native post from approved evidence.",
            ("idea_lock", "brief", "draft", "edit", "approve"), ("content-writer",),
            ("copywriting-en", "copywriting-fa"), (), ("content_draft",), (),
            graph=(WorkflowStep("draft", "employee", "content-writer", produces=("content_draft",),
                                skill_ids=("copywriting-en", "copywriting-fa")),),
        ),
        WorkflowSpec(
            "article", "Create one evidence-backed argument.",
            ("idea_lock", "brief", "draft", "edit", "seo_review", "approve"),
            ("content-writer",), ("copywriting-en", "seo"), (), ("article_draft", "seo_brief"), (),
            graph=(WorkflowStep("draft", "employee", "content-writer", produces=("article_draft",),
                                skill_ids=("copywriting-en", "seo")),),
        ),
        WorkflowSpec(
            "content-campaign", "Write, evaluate, render, then publish one campaign.",
            ("draft", "editorial_review", "design_handoff", "approval", "publish"),
            ("content-strategist", "video-producer", "publisher"), ("copywriting-en", "video-creation"),
            ("publish",), ("campaign_manifest", "content_ready", "render_report", "publication_receipt"), ("buffer",),
            graph=(
                WorkflowStep("draft", "employee", "content-strategist", produces=("campaign_manifest",),
                             skill_ids=("copywriting-en",)),
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
                              "connection": {"enum": ["buffer", "website"]},
                              "execution_mode": {"enum": ["dry_run", "live"]}}}
    evidence_metrics = {"content_packages": ("content_package",),
                        "approved_drafts": ("content_draft", "article_draft"),
                        "published_items": ("publication_receipt",)}
    workflow_agents = {"content-package": "content-strategist", "content-campaign": "content-strategist",
                       "social-post": "content-writer", "article": "content-writer", "publish": "publisher"}

    def run_machine_step(self, ctx, decision):
        if decision.get("step_id") != "quality_gate":
            return {"run_status": "blocked", "message": "Unknown content machine step"}
        evidence = list(ctx.cycle.get("evidence") or ())
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
