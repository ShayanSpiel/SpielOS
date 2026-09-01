"""Auto-installed Department Lego package: client_delivery."""

from ...runtime.evidence_department import EvidenceDepartment
from ...runtime.models import Department, WorkflowSpec, WorkflowStep


class ClientDeliveryDepartment(EvidenceDepartment, Department):
    id = department_id = 'client_delivery'
    version = '1.1.0'
    description = 'Takes workflow orders (real client builds) and demo workflow orders (client presentations), builds them on ActivePieces via the host MCP, and keeps every order organized in a lean folder plus Drive/Sheets registry with provider abstraction for later Zapier/n8n.'
    agent_ids = ('delivery-manager', 'workflow-builder')
    workflows = (
        WorkflowSpec(
            'client_workflow_build',
            'Real client workflow order: intake -> scope -> approval -> build on ActivePieces -> verify & archive.',
            ('intake', 'scope', 'approve', 'build', 'verify_archive'),
            ('delivery-manager', 'workflow-builder'),
            ('client-delivery',),
            ('order_scope_approved',),
            ('workflow_delivery_record',),
            ('activepieces', 'google-drive', 'google-sheets'),
            graph=(
                WorkflowStep('intake', 'agent', 'delivery-manager', produces=('order_brief',), requires=(), skill_ids=(), connection_ids=()),
                WorkflowStep('scope', 'agent', 'delivery-manager', produces=('workflow_spec',), requires=('order_brief',), skill_ids=('client-delivery',), connection_ids=()),
                WorkflowStep('order_scope_approved', 'approval', None, produces=(), requires=('workflow_spec',), skill_ids=(), connection_ids=()),
                WorkflowStep('build', 'connection', 'workflow-builder', produces=('flow_receipt',), requires=('workflow_spec',), skill_ids=('client-delivery',), connection_ids=('activepieces',)),
                WorkflowStep('verify_archive', 'agent', 'delivery-manager', produces=('workflow_delivery_record',), requires=('flow_receipt',), skill_ids=('client-delivery',), connection_ids=('google-drive', 'google-sheets')),
            ),
        ),
        WorkflowSpec(
            'demo_workflow_build',
            'Demo workflow order for client presentations: labeled demo data, built on ActivePieces, archived under demos.',
            ('intake', 'scope', 'approve', 'build', 'verify_archive'),
            ('delivery-manager', 'workflow-builder'),
            ('client-delivery',),
            ('order_scope_approved',),
            ('demo_delivery_record',),
            ('activepieces', 'google-drive', 'google-sheets'),
            graph=(
                WorkflowStep('intake', 'agent', 'delivery-manager', produces=('order_brief',), requires=(), skill_ids=(), connection_ids=()),
                WorkflowStep('scope', 'agent', 'delivery-manager', produces=('workflow_spec',), requires=('order_brief',), skill_ids=('client-delivery',), connection_ids=()),
                WorkflowStep('order_scope_approved', 'approval', None, produces=(), requires=('workflow_spec',), skill_ids=(), connection_ids=()),
                WorkflowStep('build', 'connection', 'workflow-builder', produces=('flow_receipt',), requires=('workflow_spec',), skill_ids=('client-delivery',), connection_ids=('activepieces',)),
                WorkflowStep('verify_archive', 'agent', 'delivery-manager', produces=('demo_delivery_record',), requires=('flow_receipt',), skill_ids=('client-delivery',), connection_ids=('google-drive', 'google-sheets')),
            ),
        ),
    )
    goal_schema = {
        "metrics": ["workflows_delivered", "demos_delivered"],
        "config": {"workflow": {"enum": ["client_workflow_build", "demo_workflow_build"]}, "required_count": {"type": "integer"}},
    }
    evidence_metrics = {
        'workflows_delivered': ('workflow_delivery_record',),
        'demos_delivered': ('demo_delivery_record',),
    }
    workflow_agents = {
        'client_workflow_build': 'delivery-manager',
        'demo_workflow_build': 'delivery-manager'
    }
