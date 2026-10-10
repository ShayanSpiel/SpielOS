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


_REMOTION = "departments/videography/remotion"
_SKILL = ("videography",)


class VideographyDepartment:
    'Synthetic product acceptance fixture; never installed or executed as owner work.'

    department_id = "videography"
    id = "videography"
    version = "3.0.0"
    description = (
        'Synthetic Department for runtime acceptance checks.'
    )
    agent_ids = ("videography-specialist", "videography-operator")
    production_ready = False

    workflows = (
        Workflow(
            "record-demo",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("resolve", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="resolved_order",
                      skill_ids=(),
                      requirements={}),
                _step("author_scenario", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="demo_scenario",
                      skill_ids=()),
                _step("record", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      approval_key="record_browser_session",
                      requirements={}),
                _step("render", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=()),
                _step("verify", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="showcase_video",
                      skill_ids=(),
                      requirements={}),
            ),
            department_id="videography",
        ),
        Workflow(
            "remotion-motion-film",
            'Synthetic workflow shape; no production implementation.',
            (
                _step("brief", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="motion_brief",
                      skill_ids=(),
                      requirements={}),
                _step("write", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="idea",
                      skill_ids=(),
                      requirements={}),
                _step("approve_idea", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="idea_pending",
                      skill_ids=(),
                      approval_key="idea_lock",
                      requirements={}),
                _step("storyboard", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="storyboard",
                      skill_ids=(),
                      requirements={}),
                _step("approve_frames", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="frames_pending",
                      skill_ids=(),
                      approval_key="frame_lock",
                      requirements={}),
                _step("build", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      requirements={}),
                _step("sound", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="audio_mix",
                      skill_ids=(),
                      requirements={}),
                _step("preview", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="preview",
                      skill_ids=(),
                      requirements={}),
                _step("eval", "videography-specialist",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="eval",
                      skill_ids=(),
                      requirements={}),
                _step("fix", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      skill_ids=(),
                      requirements={}),
                _step("final_render", "videography-operator",
                      'Exercise this step using synthetic input; record fixture evidence only.',
                      evidence_kind="motion_film",
                      skill_ids=(),
                      requirements={}),
            ),
            department_id="videography",
        ),
    )

    evidence_metrics = {
        "showcase_videos": ("showcase_video",),
        "demo_scenarios": ("demo_scenario",),
        "motion_films": ("motion_film",),
        "creative_plans": ("storyboard",),
    }

    goal_schema = {
        "metrics": ["showcase_videos", "demo_scenarios", "motion_films"],
        "config": {
            "workflow": {"enum": ["record-demo", "remotion-motion-film"]},
            "required_count": {"type": "integer"},
        },
    }

    workflow_agents = {
        "record-demo": "videography-specialist",
        "remotion-motion-film": "videography-specialist",
    }