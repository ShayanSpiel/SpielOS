"""Owner-selected workflow structure takes precedence over learned history."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from company.commands.goal_runtime import CleanCommandRuntime
from company.runtime.engine import Decision
from company.workflows import Workflow, WorkflowStep


class ExplicitWorkflowTests(unittest.TestCase):
    def test_explicit_workflow_beats_learned_history(self):
        with tempfile.TemporaryDirectory() as directory:
            command = CleanCommandRuntime(Path(directory) / 'state.sqlite')
            flow = Workflow('current', 'Current selected procedure', (
                WorkflowStep('execute', 'owner', 'Produce bounded evidence'),),
                department_id='example')
            controller = command.runtime.controller
            controller.departments = {'example': SimpleNamespace(workflows=(flow,))}
            for selection in ['current', 'example:current']:
                goal = command.create_goal(name='Use the selected procedure', owner_id='example',
                    metric='outcome', operator='ge', target=1, config={'workflow': selection})
                with patch.object(controller, '_crystallized_workflow', return_value=Decision(
                        'execute_workflow', 'Stale learned history', 'learned:old')) as learned:
                    decision = controller.decide(SimpleNamespace(goal=command.goals.get(goal['id'])), {})
                self.assertEqual(decision.workflow_id, 'example:current')
                learned.assert_not_called()
