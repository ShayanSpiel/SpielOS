"""Auto-installed Department Lego package: videography."""

from ...runtime.evidence_department import EvidenceDepartment
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


class VideographyDepartment(EvidenceDepartment, Department):
    id = department_id = 'videography'
    version = '1.0.0'
    description = 'Records authentic, human-paced browser demos of delivered Client Delivery workflows and renders them into showcase MP4s via the four-module resolve/author/record/render pipeline under scripts/videography.'
    agent_ids = ('videography-operator', 'videography-specialist')
    workflows = (
        WorkflowSpec(
            'record_demo',
            'Resolve a delivered order, author/select a humanistic scenario, run a real humanized browser session, render the capture to MP4, and file evidence.',
            ('author_scenario', 'record_render'),
            ('videography-specialist', 'videography-operator'),
            ('videography',),
            (),
            ('showcase_video',),
            (),
            graph=(
                WorkflowStep('author_scenario', 'agent', 'videography-specialist', produces=('demo_scenario',), requires=(), skill_ids=('videography',), connection_ids=()),
                WorkflowStep('record_render', 'agent', 'videography-operator', produces=('showcase_video',), requires=('demo_scenario',), skill_ids=('videography',), connection_ids=()),
            ),
        ),
    )
    goal_schema = {
        "metrics": ["showcase_videos"],
        "config": {"required_count": {"type": "integer"}, "workflow": {"enum": ["record_demo"]}},
    }
    evidence_metrics = {
        'showcase_videos': ('showcase_video',),
    }
    workflow_agents = {
        'record_demo': 'videography-specialist'
    }
