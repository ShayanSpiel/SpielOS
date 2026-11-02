"""Protected comparisons run real graphs; negative controls inject labeled faults."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from company.graph.experiments import Experiments, candidate_graph, validate_benchmarks
from company.graph.model import Graph
from company.tests.test_graph_architecture import ROOT, inspection_graph

MODIFICATION = {'operation': 'remove_ordering_edge', 'source': 'a', 'target': 'c'}


def benchmark():
    return {'version': 'synthetic-integrity-v1', 'qualification': 'Visible deterministic infrastructure cases; no protected model holdout or business-quality claim',
            'cases': [{'id': 'actual-source', 'input': {}, 'purpose': 'Inspect actual source and its declared symbol through a three-node execution',
                       'checks': [{'path': '/result/verified', 'equals': True}, {'path': '/result/path', 'equals': 'company/graph/model.py'}]}],
            'acceptance': {'max_latency_ratio': 1000, 'max_token_ratio': 1,
                           'require_token_evidence': False, 'min_complexity_reduction': 1}}


class GraphExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / 'benchmarks.json'
        self.path.write_text(json.dumps(benchmark()))
        self.experiments = Experiments(self.directory / 'store', source_root=ROOT)
        self.graph = Graph(inspection_graph())

    def prepare(self):
        return self.experiments.prepare(self.graph, self.path, MODIFICATION, request_key='bounded-test')

    def test_one_isolated_candidate_preserves_capabilities_and_original(self):
        candidate = candidate_graph(self.graph, MODIFICATION)
        self.assertEqual(len(candidate.edges), 2)
        self.assertEqual(len(self.graph.edges), 3)
        self.assertEqual(self.graph.compare(candidate)['lost_capabilities'], [])
        self.assertEqual(self.graph.compare(candidate)['removed_nodes'], [])
        self.assertEqual(self.graph.order, candidate.order)

    def test_same_protected_tasks_run_and_produce_review_evidence_without_promotion(self):
        identity = self.prepare()
        report = self.experiments.run(identity)
        self.assertEqual(report['decision'], 'eligible_for_independent_review')
        self.assertTrue(report['results']['baseline']['correct'])
        self.assertTrue(report['results']['candidate']['correct'])
        self.assertFalse(report['applied'])
        self.assertEqual(report['results']['baseline']['complexity'] - report['results']['candidate']['complexity'], 1)
        self.assertTrue((self.directory / 'store/experiments' / identity / 'result.json').is_file())
        self.assertEqual(self.prepare(), identity)

    def test_negative_fault_control_rejects_candidate_behavior(self):
        identity = self.prepare()
        original = self.experiments.runner.run
        def faulty(graph, *args, **kwargs):
            trace = original(graph, *args, **kwargs)
            if len(graph.edges) == 2:
                trace = deepcopy(trace)
                trace['outputs']['result']['verified'] = False  # explicit candidate-output fault
            return trace
        with patch.object(self.experiments.runner, 'run', side_effect=faulty):
            report = self.experiments.run(identity)
        self.assertTrue(report['results']['baseline']['correct'])
        self.assertFalse(report['results']['candidate']['correct'])
        self.assertEqual(report['decision'], 'rejected')
        self.assertFalse(report['applied'])
        self.assertEqual(len(self.graph.edges), 3)

    def test_benchmark_threshold_or_candidate_tampering_stops_comparison(self):
        identity = self.prepare()
        self.path.write_text(json.dumps({**benchmark(), 'version': 'tampered'}))
        with self.assertRaisesRegex(ValueError, 'Protected'):
            self.experiments.run(identity)
        self.path.write_text(json.dumps(benchmark()))
        frozen = self.directory / 'store/experiments' / identity / 'benchmarks.json'
        value = json.loads(frozen.read_text())
        value['acceptance']['max_latency_ratio'] = 99999
        frozen.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Protected'):
            self.experiments.run(identity)

    def test_protection_is_checked_again_after_actual_execution(self):
        identity = self.prepare()
        original = self.experiments.runner.run
        def tamper(*args, **kwargs):
            trace = original(*args, **kwargs)
            self.path.write_text('{}')
            return trace
        with patch.object(self.experiments.runner, 'run', side_effect=tamper), self.assertRaisesRegex(ValueError, 'Protected'):
            self.experiments.run(identity)

    def test_unknown_tokens_are_not_zero_and_can_block_acceptance(self):
        value = {'nodes': {'x': {'usage': {'status': 'unknown'}}}}
        self.assertIsNone(Experiments._tokens(value))
        self.assertEqual(Experiments._tokens({'nodes': {'x': {'usage': {'status': 'actual', 'input_tokens': 2, 'output_tokens': 3}}}}), 5)
        policy = benchmark()
        policy['acceptance']['require_token_evidence'] = True
        self.path.write_text(json.dumps(policy))
        identity = self.prepare()
        with patch.object(Experiments, '_tokens', return_value=None):
            report = self.experiments.run(identity)
        self.assertEqual(report['decision'], 'rejected')
        self.assertTrue(any('token evidence' in x for x in report['reasons']))

    def test_dependency_installation_capability_deletion_and_multiple_edits_are_not_supported(self):
        for modification in ({'operation': 'delete_node', 'source': 'a', 'target': 'c'},
                             {'operation': 'install_dependency', 'source': 'a', 'target': 'c'},
                             {**MODIFICATION, 'second_change': True}):
            with self.subTest(modification=modification), self.assertRaises(ValueError):
                candidate_graph(self.graph, modification)

    def test_invalid_benchmarks_cannot_establish_baseline(self):
        value = benchmark()
        value['cases'][0]['checks'] = []
        with self.assertRaises(ValueError):
            validate_benchmarks(value)
        value = benchmark()
        value['acceptance']['max_latency_ratio'] = float('nan')
        with self.assertRaises(ValueError):
            validate_benchmarks(value)
