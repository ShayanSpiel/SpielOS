'Synthetic product acceptance fixture; never installed or executed as owner work.'

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
          'Exercise this step using synthetic input; record fixture evidence only.',
          evidence_kind="order_brief",
          skill_ids=()),
    _step("scope", "delivery-manager",
          'Exercise this step using synthetic input; record fixture evidence only.',
          evidence_kind="workflow_spec",
          skill_ids=()),
    _step("order_scope_approved", "delivery-manager",
          'Exercise this step using synthetic input; record fixture evidence only.',
          approval_key="order_scope_approved"),
    _step("build", "workflow-builder",
          'Exercise this step using synthetic input; record fixture evidence only.',
          evidence_kind="flow_receipt",
          skill_ids=(),
          connection_ids=()),
    _step("verify_archive", "delivery-manager",
          'Exercise this step using synthetic input; record fixture evidence only.',
          evidence_kind="workflow_delivery_record",
          skill_ids=(),
          connection_ids=(),
          requirements={}),
)


class ClientDeliveryDepartment:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "client_delivery"
    id = "client_delivery"
    version = "1.1.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("delivery-manager", "workflow-builder")
    production_ready = False

    workflows = (
        Workflow(
            "client_workflow_build",
            'Synthetic workflow shape; no production implementation.',
            _ORDER_STEPS,
            department_id="client_delivery",
        ),
        Workflow(
            "demo_workflow_build",
            'Synthetic workflow shape; no production implementation.',
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
