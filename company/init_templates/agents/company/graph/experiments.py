"""One isolated graph edit, frozen benchmarks, actual executions, no promotion."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .model import Graph, pointer
from .runtime import GraphRunner
from ..home import write_json
from ..workflows.runs import digest, stamp


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def candidate_graph(baseline, modification):
    """Edit only a candidate document; never edit source, benchmarks or a live graph."""
    if not isinstance(modification, dict) or set(modification) != {'operation', 'source', 'target'} or modification['operation'] != 'remove_ordering_edge':
        raise ValueError('Version 1 permits one ordering-edge removal per experiment')
    edge = {'source': modification['source'], 'target': modification['target'], 'relationship': 'requires'}
    document = deepcopy(baseline.document)
    if edge not in document['edges']:
        raise ValueError('Candidate must remove an existing ordering edge')
    document['edges'].remove(edge)
    next(n for n in document['nodes'] if n['id'] == edge['target'])['dependencies'].remove(edge['source'])
    document['version'] = digest({'baseline': baseline.digest, 'modification': modification})
    candidate = Graph(document)
    if baseline.compare(candidate)['lost_capabilities']:
        raise ValueError('Capability removal requires separate owner approval')
    return candidate


def validate_benchmarks(document):
    if not isinstance(document, dict) or set(document) != {'version', 'cases', 'acceptance', 'qualification'}:
        raise ValueError('Invalid protected benchmark fields')
    cases = document['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError('Need one to one hundred protected tasks')
    seen = set()
    for case in cases:
        if set(case) != {'id', 'input', 'checks', 'purpose'} or not isinstance(case['id'], str) or not case['id'] or case['id'] in seen or not case['purpose'] or not isinstance(case['input'], dict):
            raise ValueError('Cases need distinct identities and actual input/purpose')
        seen.add(case['id'])
        if not isinstance(case['checks'], list) or not case['checks']:
            raise ValueError('Benchmarks require behavioral output checks')
        for check in case['checks']:
            if not isinstance(check, dict) or set(check) != {'path', 'equals'} or not isinstance(check['path'], str):
                raise ValueError('Benchmark checks need a pointer and expected value')
    policy = document['acceptance']
    if not isinstance(policy, dict) or set(policy) != {'max_latency_ratio', 'max_token_ratio', 'require_token_evidence', 'min_complexity_reduction'}:
        raise ValueError('Explicit frozen acceptance thresholds required')
    for key in ('max_latency_ratio', 'max_token_ratio', 'min_complexity_reduction'):
        value = policy[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Acceptance thresholds must be finite and nonnegative')
    if not isinstance(policy['require_token_evidence'], bool):
        raise ValueError('Token evidence policy must be explicit')


class Experiments:
    def __init__(self, directory, *, source_root, runtime=None):
        self.runner = GraphRunner(directory, source_root=source_root, runtime=runtime)
        self.directory = self.runner.directory

    def prepare(self, baseline, benchmark_path, modification, *, request_key):
        benchmarks = json.loads(Path(benchmark_path).read_text())
        validate_benchmarks(benchmarks)
        candidate = candidate_graph(baseline, modification)
        baseline.verify_sources(self.runner.source_root)
        candidate.verify_sources(self.runner.source_root)
        if not isinstance(request_key, str) or not request_key.strip():
            raise ValueError('Experiment needs a stable request key')
        identity = digest({'request': request_key, 'directory': str(self.directory)})
        folder = self.directory / 'experiments' / identity
        with self.runner._lock(identity):
            if (folder / 'manifest.json').exists():
                prior = json.loads((folder / 'manifest.json').read_text())
                if prior['baseline_digest'] != baseline.digest or prior['modification'] != modification or prior['benchmarks_digest'] != digest(benchmarks):
                    raise ValueError('Experiment identity reused with different content')
                self._verify(folder)
                return identity
            # Freeze the implementations of the graph, runtime and evaluator as well.
            protected = {str(Path(path).resolve()): file_digest(path) for path in
                         (Path(benchmark_path), Path(__file__), Path(__file__).with_name('model.py'), Path(__file__).with_name('runtime.py'))}
            from ..evals import contracts, standard
            from ..workflows import runs
            for module in (contracts, standard, runs):
                protected[str(Path(module.__file__).resolve())] = file_digest(module.__file__)
            for node in [*baseline.nodes.values(), *candidate.nodes.values()]:
                for ref in [node['implementation'], *[e['implementation'] for e in node['evaluation_requirements']]]:
                    source = self.runner.source_root / ref['path']
                    protected[str(source.resolve())] = file_digest(source)
            write_json(folder / 'baseline.json', baseline.document)
            write_json(folder / 'candidate.json', candidate.document)
            write_json(folder / 'benchmarks.json', benchmarks)
            protected.update({str(folder / name): file_digest(folder / name) for name in ('baseline.json', 'candidate.json', 'benchmarks.json')})
            manifest = {'id': identity, 'created_at': stamp(), 'baseline_digest': baseline.digest,
                        'candidate_digest': candidate.digest, 'benchmarks_digest': digest(benchmarks),
                        'modification': modification, 'protected': protected}
            write_json(folder / 'manifest.json', {**manifest, 'integrity': digest(manifest)})
        return identity

    def _folder(self, identity):
        self.runner._path(identity)
        return self.directory / 'experiments' / identity

    def _verify(self, folder):
        manifest = json.loads((folder / 'manifest.json').read_text())
        integrity = manifest.pop('integrity', None)
        if digest(manifest) != integrity:
            raise ValueError('Protected experiment manifest changed')
        for path, expected in manifest['protected'].items():
            if file_digest(path) != expected:
                raise ValueError('Protected benchmark, evaluator, policy or candidate changed: ' + path)
        return manifest

    @staticmethod
    def _tokens(trace):
        total = 0
        for entry in trace['nodes'].values():
            usage = entry.get('usage', {})
            if usage.get('status') == 'not_applicable':
                continue
            # Unknown/estimated/provider-specific fields cannot become measured totals.
            values = [usage.get('input_tokens'), usage.get('output_tokens')]
            if usage.get('status') != 'actual' or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values):
                return None
            total += sum(values)
        return total

    def run(self, identity):
        folder = self._folder(identity)
        with self.runner._lock(identity):
            manifest = self._verify(folder)
            benchmarks = json.loads((folder / 'benchmarks.json').read_text())
            results, complete = {}, True
            for variant in ('baseline', 'candidate'):
                graph = Graph.load(folder / (variant + '.json'))
                graph.verify_sources(self.runner.source_root)
                cases = []
                for case in benchmarks['cases']:
                    self._verify(folder)
                    trace = self.runner.run(graph, case['input'], request_key=identity + ':' + variant + ':' + case['id'])
                    self._verify(folder)
                    matched = []
                    if trace['status'] == 'completed':
                        for check in case['checks']:
                            try:
                                matched.append(pointer(trace['outputs'], check['path']) == check['equals'])
                            except (KeyError, IndexError, TypeError, ValueError):
                                matched.append(False)
                    else:
                        complete = complete and trace['status'] == 'failed'
                    cases.append({'id': case['id'], 'run_id': trace['id'], 'status': trace['status'],
                                  'passed': len(matched) == len(case['checks']) and all(matched),
                                  'checks': matched, 'seconds': trace['elapsed_seconds'], 'tokens': self._tokens(trace)})
                results[variant] = {'cases': cases, 'correct': all(row['passed'] for row in cases),
                                    'quality': sum(row['passed'] for row in cases) / len(cases),
                                    'seconds': sum(row['seconds'] for row in cases),
                                    'tokens': None if any(row['tokens'] is None for row in cases) else sum(row['tokens'] for row in cases),
                                    'complexity': len(graph.nodes) + len(graph.edges)}
            left, right = results['baseline'], results['candidate']
            policy = benchmarks['acceptance']
            latency = right['seconds'] / left['seconds'] if left['seconds'] else None
            token_ratio = (right['tokens'] / left['tokens'] if left['tokens'] else 1.0 if left['tokens'] == right['tokens'] == 0 else None)
            reasons = []
            if not left['correct'] or not right['correct']:
                reasons.append('Baseline and candidate must pass the same protected output checks')
            if latency is None or latency > policy['max_latency_ratio']:
                reasons.append('Latency threshold not met')
            if policy['require_token_evidence'] and token_ratio is None:
                reasons.append('Measured token evidence is required and unavailable')
            if token_ratio is not None and token_ratio > policy['max_token_ratio']:
                reasons.append('Token threshold not met')
            if left['complexity'] - right['complexity'] < policy['min_complexity_reduction']:
                reasons.append('Complexity reduction threshold not met')
            report = {'id': identity, 'baseline_digest': manifest['baseline_digest'],
                      'candidate_digest': manifest['candidate_digest'], 'benchmarks_digest': manifest['benchmarks_digest'],
                      'results': results, 'latency_ratio': latency, 'token_ratio': token_ratio,
                      'decision': 'incomplete' if not complete else 'rejected' if reasons else 'eligible_for_independent_review',
                      'reasons': reasons, 'applied': False, 'production_change': 'requires separate owner approval',
                      'qualification': benchmarks['qualification'],
                      'limitations': 'One local paired run; no statistically supported performance or business-impact claim'}
            self._verify(folder)
            write_json(folder / 'results' / (digest(report) + '.json'), report)
            write_json(folder / 'result.json', report)
            return report
