"""Production Analytics Department — declarative Lego package."""

from __future__ import annotations

from typing import Any

from .._evidence import EvidenceDepartment
from ..campaign_contract import funnel_metrics, validate_campaign
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


def campaign_funnel_report(manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Attach canonical funnel math only when delivery identity is complete.

    The per-template `template_breakdown` from the report is forwarded
    as-is (no math change); website funnel events stay batch-level only.
    """
    errors = validate_campaign(manifest, "delivered")
    if errors:
        raise ValueError("Analytics requires a valid delivered campaign: " + "; ".join(errors))
    required_identity = {rendition["content_id"]
                         for item in manifest["items"]
                         for rendition in (item["renditions"][platform] for platform in ("threads", "youtube"))}
    observed_identity = set(report.get("content_ids") or [])
    if observed_identity != required_identity:
        raise ValueError("Analytics report content_ids must exactly match the delivered campaign")
    experiment = manifest.get("experiment") or {}
    cells = list(report.get("experiment_cells") or [])
    minimum = experiment.get("minimum_evidence_per_cell") or 1
    evidence_sufficient = bool(report.get("evidence_complete")) and bool(cells) and all(
        isinstance(cell.get("sample_size"), int) and cell["sample_size"] >= minimum
        for cell in cells if isinstance(cell, dict)
    ) and len(cells) == len(experiment.get("cells") or [])
    experiment_evidence = {
        "experiment_id": experiment.get("id"),
        "cells": cells,
        "evidence_sufficient": evidence_sufficient,
        "analysis": {
            "method": experiment.get("analysis_method"),
            "effects": list(report.get("effects") or []),
        },
    }
    return {"schema_version": manifest["schema_version"],
            "campaign_id": manifest["campaign_id"], "batch_id": manifest["batch_id"],
            "evidence_complete": bool(report.get("evidence_complete")),
            "evidence_window": report.get("evidence_window"),
            "join_keys": list((manifest.get("measurement") or {}).get("join_keys") or []),
            "content_ids": sorted(observed_identity),
            "experiment_evidence": experiment_evidence,
            "template_breakdown": report.get("template_breakdown"),
            **funnel_metrics(report)}


class AnalyticsDepartment(EvidenceDepartment, Department):
    id = department_id = "analytics"
    version = "3.3.0"
    description = "Joins full-funnel evidence by campaign identity: refreshed Buffer per-post engagement plus read-only PostHog warehouse events per batch, with evidence-scaled one-to-three-variable decisions and explicit cells, thresholds, and effect analysis."
    agent_ids = ("analytics-operator", "cro-optimizer")
    production_ready = True
    workflows = (
        WorkflowSpec(
            "company-scorecard",
            "Report canonical business and Department metrics.",
            ("collect", "validate", "calculate", "report"), ("analytics-operator",), ("analytics",), (),
            ("posthog_query", "department_evidence"), ("posthog",),
            graph=(WorkflowStep("report", "employee", "analytics-operator",
                                produces=("company_scorecard",), skill_ids=("analytics",),
                                connection_ids=("posthog",)),),
        ),
        WorkflowSpec(
            "funnel-analysis",
            "Measure one delivered campaign from platform view through attributed lead using refreshed Buffer per-post metrics and read-only PostHog warehouse events on its preserved join keys.",
            ("validate", "query", "segment", "diagnose", "report"), ("analytics-operator",),
            ("analytics",), (), ("publication_receipt", "buffer_metrics", "posthog_query", "funnel_report", "optimization_decision"), ("posthog",),
            graph=(WorkflowStep("report", "employee", "analytics-operator",
                                produces=("funnel_report",), skill_ids=("analytics",),
                                connection_ids=("posthog",)),),
        ),
        WorkflowSpec(
            "cro-experiment",
            "Propose and evaluate one bounded single-variable, A/B, factorial, or funnel experiment.",
            ("diagnose", "hypothesis", "approve", "run", "evaluate"), ("cro-optimizer",),
            ("analytics", "copywriting-en", "spielos-ui"), ("start_experiment",),
            ("funnel_report", "cro_experiment"), ("website",),
            graph=(
                WorkflowStep("approve", "approval"),
                WorkflowStep("run", "employee", "cro-optimizer",
                             produces=("cro_experiment",),
                             skill_ids=("analytics", "copywriting-en", "spielos-ui")),
            ),
        ),
        WorkflowSpec(
            "department-insight",
            "Feed validated metrics to another Department goal.",
            ("request", "query", "validate", "attach"), ("analytics-operator",), ("analytics",), (),
            ("department_evidence",), ("posthog",),
            graph=(WorkflowStep("attach", "employee", "analytics-operator",
                                produces=("department_evidence",), skill_ids=("analytics",)),),
        ),
    )
    goal_schema = {"metrics": ["scorecards", "funnel_reports", "cro_experiments", "attributed_conversions"],
                   "config": {"workflow": {"enum": [w.id for w in workflows]},
                              "required_count": {"type": "integer"},
                              "connection": {"enum": ["posthog"]}}}
    evidence_metrics = {"scorecards": ("company_scorecard",),
                        "funnel_reports": ("funnel_report",),
                        "cro_experiments": ("cro_experiment",),
                        "attributed_conversions": ("attributed_conversion",)}
    workflow_agents = {"company-scorecard": "analytics-operator", "funnel-analysis": "analytics-operator",
                       "cro-experiment": "cro-optimizer", "department-insight": "analytics-operator"}
