"""Client Delivery Department — clean migrated declaration (legacy 1.0.0 → clean core).

Migration notes (2026-09-03):
- Legacy five-label steps became real agent-bound steps; the approval
  step ``order_scope_approved`` became an explicit per-step approval key.
- Provider abstraction preserved: every order spec carries a ``provider``
  (today ``activepieces`` via the host MCP; Zapier/n8n/Make later means one
  new Connection + one provider section, never restructuring orders).
- Registry change per the owner's Supabase single-source-of-truth directive
  (2026-09-02): the order registry is the Supabase ``orders`` table (one row
  per order), replacing ``registry.csv``. The lean per-order local folders
  under ``assets/client-delivery/orders/`` remain the artifact archive.
- The 100% verify-before-delivery hard rule is carried into the
  ``verify_archive`` step instruction and its requirements.
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


_ORDER_STEPS = (
    _step("intake", "delivery-manager",
          "Take the order (real client build or labeled demo) and write the "
          "order brief: what was asked, order type, demo-data note if demo. "
          "Record evidence {'order_brief': {...}}.",
          evidence_kind="order_brief",
          skill_ids=("client-delivery",)),
    _step("scope", "delivery-manager",
          "Scope the workflow: trigger, steps, connections, provider "
          "(default activepieces), naming (wf-YYYYMMDD-slug or "
          "demo-YYYYMMDD-slug). Record evidence {'workflow_spec': {...}} "
          "with the provider field.",
          evidence_kind="workflow_spec",
          skill_ids=("client-delivery",)),
    _step("order_scope_approved", "delivery-manager",
          "Park for owner scope approval before any external build action "
          "(approval key 'order_scope_approved').",
          approval_key="order_scope_approved"),
    _step("build", "workflow-builder",
          "Build the flow on the provider (Activepieces MCP): create the "
          "flow, configure steps, validate before publish. Demos stay "
          "unpublished unless the order explicitly asks for a live link. "
          "Record evidence {'flow_receipt': {...}}.",
          evidence_kind="flow_receipt",
          skill_ids=("client-delivery",),
          connection_ids=("activepieces",)),
    _step("verify_archive", "delivery-manager",
          "HARD RULE — verify 100% before delivery: run the flow end-to-end "
          "through the real input path (or an equivalent real sample for "
          "UI-only triggers, then restore the live reference); confirm any "
          "save/persist step actually writes (capture file/row/link). A "
          "step that reaches the provider but fails on permissions is NOT "
          "verified — fix the connection and re-run. Then archive: local "
          "order folder, Drive mirror, and the Supabase ``orders`` registry "
          "row must all exist and agree. Record evidence "
          "{'workflow_delivery_record': {...}} (real) or "
          "{'demo_delivery_record': {...}} (demo).",
          evidence_kind="workflow_delivery_record",
          skill_ids=("client-delivery",),
          connection_ids=("supabase", "activepieces"),
          requirements={"verify_100_percent": [
              "run end-to-end through the real input path",
              "confirm every save/persist step actually writes",
              "capture run receipt + save artifact into delivery-record.md",
              "local folder + Drive mirror + Supabase registry row all agree"]}),
)


class ClientDeliveryDepartment:
    """Declarative client-delivery capability; execution belongs to GoalRuntime."""

    department_id = "client_delivery"
    id = "client_delivery"
    version = "1.1.0"
    description = (
        "Takes workflow orders (real client builds) and demo workflow "
        "orders (client presentations), builds them on ActivePieces via the "
        "host MCP, and keeps every order organized in a lean folder archive "
        "plus a Supabase order registry with provider abstraction for later "
        "Zapier/n8n."
    )
    agent_ids = ("delivery-manager", "workflow-builder")
    production_ready = True

    workflows = (
        Workflow(
            "client_workflow_build",
            "Real client workflow order: intake -> scope -> approval -> "
            "build on ActivePieces -> verify & archive.",
            _ORDER_STEPS,
            department_id="client_delivery",
        ),
        Workflow(
            "demo_workflow_build",
            "Demo workflow order for client presentations: labeled demo "
            "data, built on ActivePieces, archived under demos.",
            _ORDER_STEPS,
            department_id="client_delivery",
        ),
    )

    evidence_metrics = {
        "workflows_delivered": ("workflow_delivery_record",),
        "demos_delivered": ("demo_delivery_record",),
    }

    goal_schema = {
        "metrics": ["workflows_delivered", "demos_delivered"],
        "config": {
            "workflow": {"enum": ["client_workflow_build",
                                  "demo_workflow_build"]},
            "required_count": {"type": "integer"},
        },
    }

    workflow_agents = {
        "client_workflow_build": "delivery-manager",
        "demo_workflow_build": "delivery-manager",
    }
