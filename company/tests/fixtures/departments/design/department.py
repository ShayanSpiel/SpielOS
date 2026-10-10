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


class DesignDepartment:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "design"
    id = "design"
    version = "3.5.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("designer", "video-producer")
    production_ready = False

    workflows = (
        Workflow(
            "social-visual",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("idea_lock", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("brief", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="design_brief",
                      skill_ids=()),
                _step("compose", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("render", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="approved_design",
                      skill_ids=()),
                _step("qa", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="design",
        ),
        Workflow(
            "rendition-pack",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("accept_design_order", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="design_order",
                      skill_ids=(),
                      requirements={}),
                _step("compose", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("render_sizes", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="render_report",
                      skill_ids=()),
                _step("visual_qa", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("handoff", "designer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="design",
        ),
        Workflow(
            "video-render",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("idea_lock", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("brief", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("script", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("animate", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("render", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="video_render",
                      skill_ids=()),
                _step("audio_mix", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("qa", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="design",
        ),
        Workflow(
            "video-order",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("intake", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("idea_lock", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("scenario_script", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("tts_chain", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      connection_ids=(),
                      skill_ids=()),
                _step("narration_mix", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      connection_ids=()),
                _step("render", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="video_render",
                      skill_ids=()),
                _step("qa", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("deliverable", "video-producer",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
            ),
            department_id="design",
        ),
    )

    eval_suites = ("video-cta-link", "video-text-sync", "video-media-qa")

    evidence_metrics = {
        "approved_designs": ("approved_design",),
        "rendition_count": ("render_report",),
        "video_renders": ("video_render",),
        "video_orders": ("video_render",),
    }

    goal_schema = {
        "metrics": ["approved_designs", "rendition_count", "video_renders",
                     "video_orders"],
        "config": {
            "workflow": {"enum": ["social-visual", "rendition-pack",
                                  "video-render", "video-order"]},
            "required_count": {"type": "integer"},
        },
    }

    workflow_agents = {
        "social-visual": "designer",
        "rendition-pack": "designer",
        "video-render": "video-producer",
        "video-order": "video-producer",
    }
