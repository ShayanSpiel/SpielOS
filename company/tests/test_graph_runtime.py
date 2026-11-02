"""Actual graph execution, durable runtime delegation and failure/recovery tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

from company.graph.model import Graph
from company.graph.runtime import GraphRunner
from company.graph.__main__ import explorer
from company.home import write_json
from company.workflows.runs import WorkflowRuntime, LocalAdapter
from company.tests.test_bounded_workflow_runs import accepted_release, identity, manifest
from company.tests.test_graph_architecture import ROOT, inspection_graph


def checked_manifest():
    spec = manifest()
    spec['evaluation']['criteria'][0].update(evaluator='check', check={'kind': 'pattern', 'path': '/text', 'pattern': 'one|two'})
    return spec


def workflow_graph(release):
    document = inspection_graph()
    schema = manifest()['input_schema']
    node = document['nodes'][0]
    node.update(id='first', type='workflow', dependencies=[], input_schema=schema, output_schema=schema,
                execution={'kind': 'workflow', 'release': release}, bindings={'text': {'input': '/text'}}, capabilities=['identity'])
    second = deepcopy(node)
    second.update(id='second', dependencies=['first'], bindings={'text': {'node': 'first', 'path': '/text'}})
    document.update(nodes=[node, second], input_schema=schema, output_schema=schema, entrypoints=['first'],
                    edges=[{'source': 'first', 'target': 'second', 'relationship': 'data'}],
                    outputs={'text': {'node': 'second', 'path': '/text'}}, required_capabilities=['identity'])
    return Graph(document)


class GraphRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.runner = GraphRunner(self.directory / 'graph', source_root=ROOT)

    def test_real_source_inspection_persists_trace_artifacts_and_timing(self):
        graph = Graph(inspection_graph())
        trace = self.runner.run(graph, {}, request_key='inspect')
        self.assertEqual(trace['status'], 'completed')
        self.assertTrue(trace['outputs']['result']['verified'])
        self.assertEqual(trace['outputs']['result']['path'], 'company/graph/model.py')
        self.assertTrue(trace['critical_path']['available'])
        for entry in trace['nodes'].values():
            self.assertEqual(json.loads(Path(entry['artifact']).read_text()), entry['output'])
            self.assertGreaterEqual(entry['seconds'], 0)
        self.assertEqual(self.runner.resume(trace['id'])['nodes'], trace['nodes'])

    def test_failure_propagates_and_safe_retry_preserves_history(self):
        graph = Graph(inspection_graph())
        with patch('company.graph.runtime.implementation', side_effect=OSError('temporary read failure')):
            trace = self.runner.run(graph, {}, request_key='failure')
        self.assertEqual(trace['nodes']['a']['status'], 'failed')
        self.assertEqual(trace['nodes']['c']['status'], 'blocked')
        retried = self.runner.retry(trace['id'], 'a')
        self.assertEqual(retried['status'], 'completed')
        self.assertEqual(len(retried['nodes']['a']['history']), 1)
        self.assertEqual(retried['nodes']['a']['attempt'], 2)

    def test_request_changes_trace_tampering_and_source_destination_are_rejected(self):
        graph = Graph(inspection_graph())
        trace = self.runner.run(graph, {}, request_key='identity')
        document = deepcopy(graph.document)
        document['version'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'identity reused'):
            self.runner.run(Graph(document), {}, request_key='identity')
        path = self.runner._path(trace['id'])
        value = json.loads(path.read_text())
        value['nodes']['a']['output']['verified'] = False
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.runner.resume(trace['id'])
        with self.assertRaisesRegex(ValueError, 'source repository'):
            GraphRunner(ROOT / '.spielos/graph', source_root=ROOT)

    def test_workflow_nodes_use_real_runtime_and_wait_for_independent_review(self):
        adapter = LocalAdapter(identity)
        runtime = WorkflowRuntime(self.directory / 'workflow.sqlite', adapters={'local': adapter})
        release = accepted_release(runtime, checked_manifest())
        runner = GraphRunner(self.directory / 'delegated', source_root=ROOT, runtime=runtime)
        graph = workflow_graph(release)
        trace = runner.run(graph, {'text': 'one'}, request_key='two-steps')
        self.assertEqual(trace['status'], 'waiting')
        self.assertEqual(trace['nodes']['first']['workflow_status'], 'awaiting_review')
        self.assertEqual(trace['nodes']['second']['attempt'], 0)
        first = trace['nodes']['first']['workflow_run_id']
        runtime.review(first, reviewer='synthetic-reviewer', decision='accept')
        trace = runner.resume(trace['id'])
        runtime.review(trace['nodes']['second']['workflow_run_id'], reviewer='synthetic-reviewer', decision='accept')
        trace = runner.resume(trace['id'])
        self.assertEqual(trace['status'], 'completed')
        self.assertEqual(trace['outputs'], {'text': 'one'})
        self.assertEqual(adapter.dispatch_count, 5)  # three qualifying cases, two graph nodes
        self.assertEqual(trace['nodes']['first']['usage']['status'], 'unknown')

    def test_uncertain_dispatch_resume_reuses_committed_invocation(self):
        adapter = LocalAdapter(identity)
        runtime = WorkflowRuntime(self.directory / 'uncertain.sqlite', adapters={'local': adapter})
        release = accepted_release(runtime, checked_manifest())
        runner = GraphRunner(self.directory / 'uncertain', source_root=ROOT, runtime=runtime)
        original = runtime.run
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('Coordinator lost the response after committed dispatch')
        with patch.object(runtime, 'run', side_effect=interrupted):
            trace = runner.run(workflow_graph(release), {'text': 'one'}, request_key='uncertain')
        self.assertEqual(trace['nodes']['first']['status'], 'waiting')
        trace = runner.resume(trace['id'])
        self.assertEqual(adapter.dispatch_count, 4)
        self.assertIn('workflow_run_id', trace['nodes']['first'])

    def test_failed_workflow_blocks_downstream_and_cannot_implicitly_retry(self):
        runtime = WorkflowRuntime(self.directory / 'failure.sqlite', adapters={'local': LocalAdapter(identity)})
        release = accepted_release(runtime, checked_manifest())
        runner = GraphRunner(self.directory / 'failed-workflow', source_root=ROOT, runtime=runtime)
        trace = runner.run(workflow_graph(release), {'text': 'bad'}, request_key='wrong-output')
        self.assertEqual(trace['nodes']['first']['status'], 'failed')
        self.assertEqual(trace['nodes']['second']['status'], 'blocked')
        with self.assertRaises(ValueError):
            runner.retry(trace['id'], 'first')

    def test_unreleased_workflow_never_executes(self):
        adapter = LocalAdapter(identity)
        runtime = WorkflowRuntime(self.directory / 'draft.sqlite', adapters={'local': adapter})
        release = runtime.candidate(manifest())
        runner = GraphRunner(self.directory / 'draft', source_root=ROOT, runtime=runtime)
        trace = runner.run(workflow_graph(release), {'text': 'one'}, request_key='draft')
        self.assertNotEqual(trace['status'], 'completed')
        self.assertEqual(adapter.dispatch_count, 0)

    def test_explorer_embeds_exact_graph_and_escapes_script_content(self):
        document = inspection_graph()
        document['nodes'][0]['group'] = '</script><script>alert(1)</script>'
        graph = Graph(document)
        path = self.directory / 'explorer.html'
        explorer(graph, output=path, source_root=ROOT)
        content = path.read_text()
        self.assertNotIn('</script><script>alert(1)</script>', content)
        self.assertIn('\\u003c/script', content)
        self.assertIn(graph.digest, content)

    def test_source_update_templates_ship_graph_to_a_synthetic_home(self):
        from company.runtime.bootstrap import scaffold
        home = self.directory / 'installed'
        scaffold(home)
        owner_file = home / 'company/profile.md'
        before = owner_file.read_bytes()
        scaffold(home, force=True)
        self.assertEqual(owner_file.read_bytes(), before)
        target = home / '.agents/company/graph'
        for name in ('model.py', 'runtime.py', 'experiments.py', 'explorer.html', 'architecture.json', 'schema.json'):
            self.assertEqual((ROOT / 'company/graph' / name).read_bytes(), (target / name).read_bytes())
        result = subprocess.run([sys.executable, '-B', '-m', 'company.graph', 'validate'], cwd=home,
                                env={**__import__('os').environ, 'PYTHONPATH': str(home / '.agents'), 'PYTHONDONTWRITEBYTECODE': '1'},
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['valid'])
