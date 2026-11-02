"""File-journaled DAG execution. WorkflowRuntime retains all workflow authority."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from ..platform import acquire_lock,release_lock
import json
import os
from pathlib import Path
import time

from .model import Graph, implementation, pointer
from ..home import write_json
from ..runtime.boundary import require_runtime_destination
from ..workflows.runs import canonical, digest, stamp, validate, LocalFileAdapter


class GraphRunner:
    def __init__(self, directory, *, source_root, runtime=None):
        self.directory = Path(directory).expanduser().resolve()
        require_runtime_destination(self.directory)
        self.source_root = Path(source_root).resolve()
        self.runtime = runtime
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id):
        if not isinstance(run_id, str) or len(run_id) != 64 or any(c not in '0123456789abcdef' for c in run_id):
            raise ValueError('Invalid graph run identity')
        return self.directory / 'runs' / (run_id + '.json')

    @contextmanager
    def _lock(self, run_id):
        path = self._path(run_id).with_suffix('.lock')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as stream:
            try:
                acquire_lock(stream.fileno(),blocking=False)
            except BlockingIOError as exc:
                raise RuntimeError('Another coordinator owns this graph run') from exc
            try:
                yield
            finally:
                release_lock(stream.fileno())

    def _read(self, path):
        value = json.loads(path.read_text())
        expected = value.pop('integrity', None)
        if expected != digest(value):
            raise ValueError('Graph trace integrity check failed')
        return value

    def _save(self, trace):
        trace['updated_at'] = stamp()
        write_json(self._path(trace['id']), {**trace, 'integrity': digest(trace)})

    def show(self, run_id):
        return self._read(self._path(run_id))

    def _runtime_identity(self):
        return str(self.runtime.path.resolve()) if self.runtime is not None else None

    def run(self, graph, inputs, *, request_key):
        if not isinstance(request_key, str) or not request_key.strip():
            raise ValueError('Graph run needs a stable request key')
        validate(graph.document['input_schema'], inputs)
        # Request key binds content rather than silently making another run on change.
        run_id = digest({'request': request_key, 'directory': str(self.directory)})
        with self._lock(run_id):
            path = self._path(run_id)
            if path.exists():
                trace = self._read(path)
                if trace['graph_digest'] != graph.digest or trace['inputs'] != inputs or trace['runtime'] != self._runtime_identity() or trace['source_root'] != str(self.source_root):
                    raise ValueError('Request identity reused with different graph, input or runtime')
            else:
                trace = {'id': run_id, 'graph': graph.document, 'graph_digest': graph.digest,
                         'request_key': request_key, 'inputs': deepcopy(inputs), 'status': 'pending',
                         'source_root': str(self.source_root), 'runtime': self._runtime_identity(),
                         'created_at': stamp(), 'nodes': {key: {'status': 'pending', 'attempt': 0, 'history': []} for key in graph.nodes},
                         'outputs': None, 'elapsed_seconds': 0.0}
                self._save(trace)
            return self._advance(graph, trace)

    def resume(self, run_id):
        with self._lock(run_id):
            trace = self.show(run_id)
            if trace['runtime'] != self._runtime_identity() or trace['source_root'] != str(self.source_root):
                raise ValueError('Resume needs the original runtime and source root')
            graph = Graph(trace['graph'])
            if graph.digest != trace['graph_digest']:
                raise ValueError('Graph version changed')
            return self._advance(graph, trace)

    @staticmethod
    def _mapped(mapping, trace):
        result = {}
        for name, ref in mapping.items():
            if 'value' in ref:
                value = ref['value']
            elif 'input' in ref:
                value = pointer(trace['inputs'], ref['input'])
            else:
                value = pointer(trace['nodes'][ref['node']]['output'], ref['path'])
            result[name] = deepcopy(value)
        return result

    def _workflow(self, node, entry, request_key):
        if self.runtime is None:
            raise ValueError('Workflow node requires an explicitly selected runtime')
        release = node['execution']['release']
        manifest = self.runtime.manifest(release)
        if manifest['input_schema'] != node['input_schema'] or manifest['output_schema'] != node['output_schema']:
            raise ValueError('Graph contracts differ from pinned workflow release')
        if manifest['execution']['provider'] == 'local' and self.runtime.home:
            self.runtime.adapters['local'] = LocalFileAdapter(self.runtime.home, manifest)
        entry['dispatch_intent'] = True
        run = self.runtime.run(release, entry['inputs'], request_key=request_key)
        entry['workflow_run_id'] = run['id']
        if run['status'] in {'dispatching', 'awaiting_provider', 'awaiting_reconciliation'}:
            run = self.runtime.reconcile(run['id'])
        if run['status'] == 'awaiting_evaluation':
            run = self.runtime.evaluate_run(run['id'])
        entry['workflow_status'] = run['status']
        entry['evaluation'] = run['evaluation']
        entry['usage'] = run['usage'] or {'status': 'unknown'}
        entry['qualification_state'] = run['qualification_state']
        if run['status'] in {'failed', 'cancelled'}:
            entry['error'] = run.get('error') or 'Workflow failed its contract'
            return None, 'failed'
        if run['status'] != 'completed':
            return None, 'waiting'
        return run['output'], 'completed'

    def _advance(self, graph, trace):
        if trace['status'] == 'completed':
            return trace
        started = time.monotonic()
        for key in graph.order:
            node, entry = graph.nodes[key], trace['nodes'][key]
            if entry['status'] in {'completed', 'failed', 'unavailable'}:
                continue
            parents = [trace['nodes'][p]['status'] for p in graph.parents[key]]
            if any(status in {'failed', 'blocked', 'unavailable'} for status in parents):
                entry.update(status='blocked', error='A required predecessor did not complete')
                continue
            if any(status != 'completed' for status in parents):
                continue
            if node['execution']['kind'] == 'unavailable':
                entry.update(status='unavailable', error='Capability is ' + node['availability'])
                continue
            if entry['status'] == 'blocked':
                entry['status'] = 'pending'
            prior_status = entry['status']
            if prior_status == 'pending':
                entry.update(attempt=entry['attempt'] + 1, started_at=stamp(), seconds=0.0)
            entry.update(status='running', inputs=self._mapped(node['bindings'], trace))
            request = trace['id'] + ':' + key + ':' + str(entry['attempt'])
            # Commit intent before dispatch. Runtime request identity handles a crash here.
            self._save(trace)
            tick = time.monotonic()
            try:
                validate(node['input_schema'], entry['inputs'])
                source = implementation(self.source_root, node['implementation'])
                checks = [implementation(self.source_root, e['implementation']) for e in node['evaluation_requirements']]
                if node['execution']['kind'] == 'inspect':
                    output, status = source, 'completed'
                    entry['evaluation'] = {'state': 'pass', 'scope': 'source reference integrity only',
                                           'checks': checks, 'behavioral_quality': 'not evaluated'}
                    entry['usage'] = {'status': 'not_applicable', 'source': 'local source inspection'}
                else:
                    output, status = self._workflow(node, entry, request)
                entry['status'] = status
                if status == 'completed':
                    validate(node['output_schema'], output)
                    entry.update(output=output, output_digest=digest(output), finished_at=stamp())
                    entry['duration_seconds'] = (datetime.fromisoformat(entry['finished_at']) - datetime.fromisoformat(entry['started_at'])).total_seconds()
                    artifact = self.directory / 'artifacts' / trace['id'] / (digest(key) + '-' + str(entry['attempt']) + '.json')
                    write_json(artifact, output)
                    entry['artifact'] = str(artifact)
            except Exception as exc:
                # A workflow API exception may follow committed dispatch; don't replay it.
                if node['execution']['kind'] == 'workflow' and entry.get('dispatch_intent'):
                    entry.update(status='waiting', error=type(exc).__name__ + ': ' + str(exc))
                else:
                    entry.update(status='failed', error=type(exc).__name__ + ': ' + str(exc), finished_at=stamp())
            entry['seconds'] = entry.get('seconds', 0.0) + time.monotonic() - tick
            self._save(trace)
        states = {row['status'] for row in trace['nodes'].values()}
        trace['elapsed_seconds'] += time.monotonic() - started
        trace['wall_seconds'] = (datetime.fromisoformat(stamp()) - datetime.fromisoformat(trace['created_at'])).total_seconds()
        if states == {'completed'}:
            trace['outputs'] = self._mapped(graph.document['outputs'], trace)
            validate(graph.document['output_schema'], trace['outputs'])
            trace['status'] = 'completed'
        else:
            trace['status'] = 'failed' if states & {'failed', 'unavailable'} else 'waiting'
        trace['critical_path'] = graph.critical_path({key: row['duration_seconds'] for key, row in trace['nodes'].items() if row['status'] == 'completed'})
        self._save(trace)
        return trace

    def retry(self, run_id, node_id):
        """Explicit bounded retry of pure work only; uncertain work uses resume."""
        with self._lock(run_id):
            trace = self.show(run_id)
            graph = Graph(trace['graph'])
            node, entry = graph.nodes[node_id], trace['nodes'][node_id]
            if entry['status'] != 'failed' or not node['execution'].get('retry_safe'):
                raise ValueError('Only explicitly safe failed nodes may be retried')
            budget = 1
            if node['execution']['kind'] == 'workflow':
                manifest = self.runtime.manifest(node['execution']['release'])
                if manifest['execution']['provider'] != 'local' or manifest['execution']['effect_permissions']:
                    raise PermissionError('Effectful or host work cannot be blindly retried')
                budget = manifest['execution']['retry_budget']
            if entry['attempt'] > budget or any(trace['nodes'][key]['status'] == 'completed' for key in graph.reachability(node_id)):
                raise ValueError('Retry budget exhausted or dependent outputs already committed')
            history = entry['history'] + [{k: v for k, v in entry.items() if k != 'history'}]
            trace['nodes'][node_id] = {'status': 'pending', 'attempt': entry['attempt'], 'history': history}
            for key in graph.reachability(node_id):
                if trace['nodes'][key]['status'] == 'blocked':
                    trace['nodes'][key]['status'] = 'pending'
            trace['status'] = 'pending'
            self._save(trace)
        return self.resume(run_id)
