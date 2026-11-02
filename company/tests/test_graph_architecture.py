"""Synthetic structural cases plus integrity of the actual repository inventory."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from company.graph.model import Graph, compatible, implementation, schema_contract

ROOT = Path(__file__).resolve().parents[2]
EMPTY = {'type': 'object', 'properties': {}, 'required': []}
INSPECTION = {'type': 'object', 'properties': {'path': {'type': 'string'}, 'sha256': {'type': 'string'},
              'bytes': {'type': 'integer'}, 'verified': {'type': 'boolean'}},
              'required': ['path', 'sha256', 'bytes', 'verified']}


def inspection_graph():
    nodes = []
    for identity, parents in [('a', []), ('b', ['a']), ('c', ['a', 'b'])]:
        nodes.append({'id': identity, 'type': 'runtime', 'version': '1', 'input_schema': EMPTY,
                      'output_schema': INSPECTION, 'dependencies': parents, 'status': 'pending',
                      'evaluation_requirements': [{'id': 'source', 'question': 'Does the actual source symbol exist?',
                          'implementation': {'path': 'company/tests/test_graph_architecture.py', 'symbol': 'GraphArchitectureTests.test_catalog_sources_exist'}}],
                      'implementation': {'path': 'company/graph/model.py', 'symbol': 'Graph'},
                      'execution': {'kind': 'inspect', 'retry_safe': True}, 'bindings': {},
                      'capabilities': ['synthetic.' + identity], 'group': 'synthetic', 'availability': 'implemented'})
    return {'schema_version': 1, 'id': 'synthetic-integrity', 'version': '1', 'input_schema': EMPTY,
            'output_schema': {'type': 'object', 'properties': {'result': INSPECTION}, 'required': ['result']},
            'nodes': nodes, 'edges': [{'source': a, 'target': b, 'relationship': 'requires'} for a, b in [('a', 'b'), ('b', 'c'), ('a', 'c')]],
            'entrypoints': ['a'], 'outputs': {'result': {'node': 'c', 'path': ''}},
            'required_capabilities': ['synthetic.c']}


class GraphArchitectureTests(unittest.TestCase):
    def test_catalog_sources_exist(self):
        graph = Graph.load(ROOT / 'company/graph/architecture.json')
        checked = graph.verify_sources(ROOT)
        self.assertEqual(set(checked), set(graph.nodes))
        self.assertGreater(len(checked), 15)
        self.assertTrue(all(row['implementation']['verified'] for row in checked.values()))

    def test_roundtrip_order_reachability_impact_and_redundancy(self):
        graph = Graph(inspection_graph())
        restored = Graph(json.loads(json.dumps(graph.document)))
        self.assertEqual(graph.digest, restored.digest)
        self.assertEqual(graph.order, ['a', 'b', 'c'])
        self.assertEqual(graph.reachability('a'), {'b', 'c'})
        self.assertEqual(graph.reachability('c', reverse=True), {'a', 'b'})
        self.assertEqual(graph.impact(['b'])['nodes'], ['b', 'c'])
        self.assertEqual(graph.findings()['redundant_ordering_edges'], [{'source': 'a', 'target': 'c', 'relationship': 'requires'}])

    def test_cycles_missing_and_duplicate_dependencies_are_rejected(self):
        for failure in ('cycle', 'missing', 'duplicate', 'disagreement'):
            document = inspection_graph()
            if failure == 'cycle':
                document['edges'].append({'source': 'c', 'target': 'a', 'relationship': 'requires'})
                document['nodes'][0]['dependencies'] = ['c']
            elif failure == 'missing':
                document['edges'][0]['source'] = 'absent'
            elif failure == 'duplicate':
                document['edges'].append(deepcopy(document['edges'][0]))
            else:
                document['nodes'][1]['dependencies'] = []
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                Graph(document)

    def test_contracts_are_checked_even_without_input_values(self):
        for schema in ({'type': 'object', 'properties': {'optional': {'type': 'invented'}}},
                       {'type': 'object', 'required': ['missing']}, {'type': 'array'},
                       {'type': 'number', 'minimum': 2}, {'type': 'integer', 'enum': [True]}):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                schema_contract(schema)
        self.assertFalse(compatible({'type': 'string'}, {'type': 'integer'}))
        self.assertTrue(compatible({'type': 'integer'}, {'type': 'number'}))

    def test_unreachable_and_uncovered_capabilities_fail_validation(self):
        document = inspection_graph()
        document['entrypoints'] = ['b']
        with self.assertRaises(ValueError):
            Graph(document)
        document = inspection_graph()
        document['nodes'][1]['evaluation_requirements'] = []
        with self.assertRaisesRegex(ValueError, 'evaluation'):
            Graph(document)
        document = inspection_graph()
        document['required_capabilities'] = ['absent']
        with self.assertRaisesRegex(ValueError, 'capability'):
            Graph(document)

    def test_data_mapping_requires_dependency_guaranteed_path_and_type(self):
        document = inspection_graph()
        document['nodes'][1]['input_schema'] = {'type': 'object', 'properties': {'verified': {'type': 'boolean'}}, 'required': ['verified']}
        document['nodes'][1]['bindings'] = {'verified': {'node': 'a', 'path': '/verified'}}
        with self.assertRaisesRegex(ValueError, 'data/context'):
            Graph(document)
        document['edges'][0]['relationship'] = 'data'
        self.assertEqual(Graph(document).order, ['a', 'b', 'c'])
        document['nodes'][1]['bindings']['verified']['path'] = '/sha256'
        with self.assertRaisesRegex(ValueError, 'Incompatible'):
            Graph(document)
        document['nodes'][1]['bindings']['verified']['path'] = '/missing'
        with self.assertRaisesRegex(ValueError, 'guaranteed'):
            Graph(document)

    def test_critical_path_requires_complete_measured_timings(self):
        graph = Graph(inspection_graph())
        self.assertEqual(graph.critical_path({'a': 1, 'b': 2, 'c': 3})['seconds'], 6)
        self.assertFalse(graph.critical_path({'a': 1})['available'])
        self.assertFalse(graph.critical_path({'a': 1, 'b': float('nan'), 'c': 3})['available'])

    def test_removal_cannot_silently_delete_required_capability(self):
        original = Graph(inspection_graph())
        candidate = inspection_graph()
        candidate['nodes'][2]['capabilities'] = []
        with self.assertRaisesRegex(ValueError, 'capability'):
            Graph(candidate)
        candidate['required_capabilities'] = []
        self.assertEqual(original.compare(Graph(candidate))['lost_capabilities'], ['synthetic.c'])

    def test_version_capture_and_source_tamper_detection(self):
        graph = Graph(inspection_graph()).capture(ROOT)
        graph.verify_sources(ROOT)
        document = deepcopy(graph.document)
        document['nodes'][0]['implementation']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            Graph(document).verify_sources(ROOT)
        with self.assertRaises(ValueError):
            implementation(ROOT, {'path': '../private'})

    def test_orphan_finding_does_not_delete_optional_nodes(self):
        document = inspection_graph()
        node = deepcopy(document['nodes'][0])
        node.update(id='optional', dependencies=[], capabilities=[])
        document['nodes'].append(node)
        document['entrypoints'].append('optional')
        graph = Graph(document)
        self.assertEqual(graph.findings()['orphaned'], ['optional'])
        self.assertIn('optional', graph.nodes)
