"""Strict graph contracts and deterministic dependency analysis, using only stdlib."""
from copy import deepcopy
import ast
import hashlib
import json
import math
from pathlib import Path
import re

from ..workflows.runs import canonical, digest, validate

KINDS = {'agent', 'skill', 'tool', 'workflow', 'runtime', 'memory', 'evaluation',
         'artifact', 'input', 'output', 'connection', 'improvement'}
RELATIONS = {'requires', 'data', 'context', 'evaluates', 'records'}
STATES = {'implemented', 'compatibility', 'held', 'planned'}
NODE_FIELDS = {'id', 'type', 'version', 'input_schema', 'output_schema', 'dependencies',
               'status', 'evaluation_requirements', 'implementation', 'execution',
               'bindings', 'capabilities', 'group', 'availability'}


def reference_contract(ref):
    if not isinstance(ref, dict) or set(ref) - {'path', 'symbol', 'sha256'} or not isinstance(ref.get('path'), str) or not ref['path']:
        raise ValueError('Implementation requires a contained relative path')
    path = Path(ref['path'])
    if path.is_absolute() or '..' in path.parts or path.as_posix() != ref['path']:
        raise ValueError('Invalid implementation path')
    if 'symbol' in ref and (not isinstance(ref['symbol'], str) or not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', ref['symbol'])):
        raise ValueError('Invalid implementation symbol')
    if 'sha256' in ref and (not isinstance(ref['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', ref['sha256'])):
        raise ValueError('Invalid source digest')


def schema_contract(schema):
    """Validate the entire schema, including absent optional properties."""
    allowed = {'type', 'properties', 'required', 'additionalProperties', 'items', 'enum'}
    if not isinstance(schema, dict) or set(schema) - allowed:
        raise ValueError('Unsupported contract keyword')
    kind = schema.get('type')
    if kind not in {'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'}:
        raise ValueError('Contract needs a supported type')
    if 'enum' in schema:
        if not isinstance(schema['enum'], list) or not schema['enum']:
            raise ValueError('Contract enum must be nonempty')
        for item in schema['enum']:
            validate({k: v for k, v in schema.items() if k != 'enum'}, item)
    if kind == 'object':
        props, required = schema.get('properties', {}), schema.get('required', [])
        if not isinstance(props, dict) or not isinstance(required, list) or any(not isinstance(x, str) for x in required):
            raise ValueError('Invalid object contract')
        if len(required) != len(set(required)) or set(required) - set(props):
            raise ValueError('Required fields must name distinct declared properties')
        if not isinstance(schema.get('additionalProperties', False), bool):
            raise ValueError('additionalProperties must be boolean')
        for value in props.values():
            schema_contract(value)
    elif {'properties', 'required', 'additionalProperties'} & set(schema):
        raise ValueError('Object keywords on a non-object contract')
    if kind == 'array':
        schema_contract(schema.get('items', {}))
    elif 'items' in schema:
        raise ValueError('Array keyword on a non-array contract')
    canonical(schema)


def pointer_parts(path):
    if not isinstance(path, str) or (path and not path.startswith('/')) or re.search(r'~(?![01])', path):
        raise ValueError('Invalid JSON pointer')
    return [] if path == '' else [part.replace('~1', '/').replace('~0', '~') for part in path[1:].split('/')]


def pointer(value, path):
    for key in pointer_parts(path):
        value = value[int(key)] if isinstance(value, list) and key.isdecimal() else value[key]
    return value


def pointer_schema(schema, path):
    for part in pointer_parts(path):
        if schema['type'] == 'object' and part in schema.get('properties', {}):
            # Optional fields cannot guarantee a downstream value.
            if part not in schema.get('required', []):
                raise ValueError('Mapping references an optional field')
            schema = schema['properties'][part]
        else:
            raise ValueError('Mapping needs a guaranteed object field')
    return schema


def compatible(source, target):
    """Whether every value guaranteed by source satisfies target (small vocabulary)."""
    if source['type'] != target['type'] and (source['type'], target['type']) != ('integer', 'number'):
        return False
    if 'enum' in target and ('enum' not in source or any(x not in target['enum'] for x in source['enum'])):
        return False
    if source['type'] == 'object':
        sp, tp = source.get('properties', {}), target.get('properties', {})
        if set(target.get('required', [])) - set(source.get('required', [])):
            return False
        if not target.get('additionalProperties', False) and (source.get('additionalProperties', False) or set(sp) - set(tp)):
            return False
        if source.get('additionalProperties', False) and set(tp) - set(sp):
            return False
        return all(compatible(sp[k], tp[k]) for k in sp.keys() & tp.keys())
    if source['type'] == 'array':
        return compatible(source['items'], target['items'])
    return True


def implementation(root, ref):
    """Read contained source as data; never import graph-supplied code."""
    reference_contract(ref)
    name = Path(ref['path'])
    root = Path(root).resolve()
    path = root / name
    if name.is_absolute() or '..' in name.parts or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Implementation escapes source root')
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if ref.get('sha256') and ref['sha256'] != actual:
        raise ValueError('Implementation bytes changed: ' + str(name))
    symbol = ref.get('symbol')
    if symbol:
        tree = ast.parse(raw)
        for part in symbol.split('.'):
            tree = next((x for x in tree.body if isinstance(x, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == part), None)
            if tree is None:
                raise ValueError('Missing implementation symbol: ' + symbol)
    return {'path': name.as_posix(), 'sha256': actual, 'bytes': len(raw), 'verified': True}


class Graph:
    def __init__(self, document):
        self.document = deepcopy(document)
        required = {'schema_version', 'id', 'version', 'input_schema', 'output_schema',
                    'nodes', 'edges', 'entrypoints', 'outputs', 'required_capabilities'}
        if not isinstance(document, dict) or set(document) != required or document['schema_version'] != 1:
            raise ValueError('Invalid graph document fields/version')
        if any(not isinstance(document[x], str) or not document[x] for x in ('id', 'version')):
            raise ValueError('Graph identity and version are required')
        for key in ('input_schema', 'output_schema'):
            schema_contract(document[key])
            if document[key]['type'] != 'object':
                raise ValueError('Graph boundary contracts must be objects')
        if not isinstance(document['nodes'], list) or not 1 <= len(document['nodes']) <= 1000:
            raise ValueError('Graph needs one to one thousand nodes')
        self.nodes = {}
        for node in self.document['nodes']:
            if not isinstance(node, dict) or set(node) != NODE_FIELDS:
                raise ValueError('Invalid node fields')
            identity = node['id']
            if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', identity) or identity in self.nodes:
                raise ValueError('Node identities must be distinct safe names')
            if node['type'] not in KINDS or node['availability'] not in STATES or node['status'] != 'pending':
                raise ValueError('Invalid node type, availability or initial execution status')
            if any(not isinstance(node[k], str) or not node[k] for k in ('version', 'group')):
                raise ValueError('Node version/group are required')
            for key in ('dependencies', 'capabilities'):
                if not isinstance(node[key], list) or any(not isinstance(x, str) or not x for x in node[key]) or len(set(node[key])) != len(node[key]):
                    raise ValueError('Node lists must contain distinct names')
            for key in ('input_schema', 'output_schema'):
                schema_contract(node[key])
            if node['input_schema']['type'] != 'object':
                raise ValueError('Node input must be an object')
            reference_contract(node['implementation'])
            execution = node['execution']
            if not isinstance(execution, dict) or set(execution) - {'kind', 'release', 'retry_safe'} or execution.get('kind') not in {'inspect', 'workflow', 'unavailable'}:
                raise ValueError('Unsupported execution binding')
            if 'retry_safe' in execution and not isinstance(execution['retry_safe'], bool):
                raise ValueError('retry_safe must be explicit boolean')
            if execution['kind'] == 'workflow' and (not isinstance(execution.get('release'), str) or not execution['release']):
                raise ValueError('Workflow nodes need a pinned release')
            if node['availability'] in {'held', 'planned', 'compatibility'} and execution['kind'] != 'unavailable':
                raise ValueError('Held, planned and compatibility nodes cannot dispatch')
            evaluations = node['evaluation_requirements']
            if not isinstance(evaluations, list) or (execution['kind'] != 'unavailable' and not evaluations):
                raise ValueError('Executable nodes require evaluation coverage')
            seen = set()
            for evaluation in evaluations:
                if not isinstance(evaluation, dict) or set(evaluation) != {'id', 'question', 'implementation'} or not evaluation['question'] or not evaluation['id'] or evaluation['id'] in seen:
                    raise ValueError('Invalid evaluation requirement')
                seen.add(evaluation['id'])
                reference_contract(evaluation['implementation'])
            if not isinstance(node['bindings'], dict):
                raise ValueError('Bindings must explicitly map input fields')
            self.nodes[identity] = node
        self.edges = self.document['edges']
        if not isinstance(self.edges, list):
            raise ValueError('Edges must be a list')
        self.parents = {key: set() for key in self.nodes}
        self.children = {key: set() for key in self.nodes}
        seen = set()
        for edge in self.edges:
            if not isinstance(edge, dict) or set(edge) != {'source', 'target', 'relationship'}:
                raise ValueError('Invalid edge fields')
            a, b, relation = edge['source'], edge['target'], edge['relationship']
            if a not in self.nodes or b not in self.nodes or relation not in RELATIONS:
                raise ValueError('Missing dependency or unsupported relationship')
            if (a, b) in seen:
                raise ValueError('Duplicate dependency edge')
            seen.add((a, b))
            self.parents[b].add(a)
            self.children[a].add(b)
        for key, node in self.nodes.items():
            if set(node['dependencies']) != self.parents[key]:
                raise ValueError('Dependencies and edges disagree: ' + key)
        self.order = self.topological()
        roots = document['entrypoints']
        if not isinstance(roots, list) or not roots or any(x not in self.nodes for x in roots) or len(set(roots)) != len(roots):
            raise ValueError('Entrypoints must name distinct nodes')
        if any(self.parents[key] for key in roots):
            raise ValueError('Entrypoints must be roots')
        reachable = set(roots)
        for key in roots:
            reachable.update(self.reachability(key))
        if set(self.nodes) - reachable:
            raise ValueError('Unreachable nodes: ' + ', '.join(sorted(set(self.nodes) - reachable)))
        for key, node in self.nodes.items():
            props = node['input_schema'].get('properties', {})
            if set(node['bindings']) - set(props) or set(node['input_schema'].get('required', [])) - set(node['bindings']):
                raise ValueError('Input bindings do not fulfill contract: ' + key)
            for name, ref in node['bindings'].items():
                self._binding(ref, props[name], target=key)
        outputs = document['outputs']
        props = document['output_schema'].get('properties', {})
        if not isinstance(outputs, dict) or set(outputs) != set(props):
            raise ValueError('Graph outputs must map all declared fields')
        for name, ref in outputs.items():
            self._binding(ref, props[name])
        required_caps = document['required_capabilities']
        if not isinstance(required_caps, list) or any(not isinstance(x, str) for x in required_caps) or len(set(required_caps)) != len(required_caps):
            raise ValueError('Invalid required capability population')
        available = {c for n in self.nodes.values() if n['availability'] == 'implemented' for c in n['capabilities']}
        if set(required_caps) - available:
            raise ValueError('Required capability is absent or unavailable')

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    @property
    def digest(self):
        return digest(self.document)

    def _binding(self, ref, expected, target=None):
        if not isinstance(ref, dict):
            raise ValueError('Binding must be a reference object')
        if set(ref) == {'value'}:
            validate(expected, ref['value'])
            return
        if set(ref) == {'input'}:
            source = pointer_schema(self.document['input_schema'], ref['input'])
        elif set(ref) == {'node', 'path'} and ref['node'] in self.nodes:
            if target is not None and ref['node'] not in self.parents[target]:
                raise ValueError('Data reference needs a direct dependency')
            if target is not None and not any(e['source'] == ref['node'] and e['target'] == target and e['relationship'] in {'data', 'context'} for e in self.edges):
                raise ValueError('Data reference needs a data/context edge')
            source = pointer_schema(self.nodes[ref['node']]['output_schema'], ref['path'])
        else:
            raise ValueError('Invalid or missing binding reference')
        if not compatible(source, expected):
            raise ValueError('Incompatible data-flow contracts')

    def topological(self):
        remaining = {key: set(value) for key, value in self.parents.items()}
        order = []
        while remaining:
            ready = sorted(key for key, parents in remaining.items() if not parents)
            if not ready:
                raise ValueError('Dependency cycle rejected')
            order.extend(ready)
            for key in ready:
                del remaining[key]
            for parents in remaining.values():
                parents.difference_update(ready)
        return order

    def reachability(self, identity, *, reverse=False):
        if identity not in self.nodes:
            raise KeyError(identity)
        links = self.parents if reverse else self.children
        visited, pending = set(), list(links[identity])
        while pending:
            key = pending.pop()
            if key not in visited:
                visited.add(key)
                pending.extend(links[key] - visited)
        return visited

    def impact(self, identities):
        affected = set(identities)
        for identity in identities:
            affected.update(self.reachability(identity))
        return {'nodes': sorted(affected), 'capabilities': sorted({c for key in affected for c in self.nodes[key]['capabilities']})}

    def findings(self):
        useful = {ref['node'] for ref in self.document['outputs'].values() if 'node' in ref}
        for key in list(useful):
            useful.update(self.reachability(key, reverse=True))
        redundant = []
        for edge in self.edges:
            if edge['relationship'] == 'requires' and any(edge['target'] in self.reachability(other) for other in self.children[edge['source']] - {edge['target']}):
                redundant.append(deepcopy(edge))
        return {'orphaned': sorted(k for k in self.nodes if not self.parents[k] and not self.children[k] and k not in useful),
                'outside_output_paths': sorted(set(self.nodes) - useful), 'redundant_ordering_edges': redundant,
                'unavailable': sorted(k for k, n in self.nodes.items() if n['execution']['kind'] == 'unavailable')}

    def critical_path(self, durations):
        if set(self.nodes) - set(durations) or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in durations.values()):
            return {'available': False, 'reason': 'Complete nonnegative measured durations required'}
        costs, paths = {}, {}
        for key in self.order:
            parent = max(sorted(self.parents[key]), key=lambda x: costs[x], default=None)
            costs[key] = durations[key] + (costs[parent] if parent else 0)
            paths[key] = (paths[parent] if parent else []) + [key]
        last = max(self.order, key=lambda x: costs[x])
        return {'available': True, 'nodes': paths[last], 'seconds': costs[last],
                'interpretation': 'dependency lower bound; serial coordinator wall time may be longer'}

    def verify_sources(self, root):
        return {key: {'implementation': implementation(root, node['implementation']),
                      'evaluations': [implementation(root, e['implementation']) for e in node['evaluation_requirements']]}
                for key, node in self.nodes.items()}

    def capture(self, root):
        document = deepcopy(self.document)
        for node in document['nodes']:
            for ref in [node['implementation'], *[e['implementation'] for e in node['evaluation_requirements']]]:
                ref['sha256'] = implementation(root, {k: v for k, v in ref.items() if k != 'sha256'})['sha256']
            node['version'] = node['implementation']['sha256']
        document['version'] = digest(document['nodes'])
        return Graph(document)

    def compare(self, candidate):
        before, after = self.nodes, candidate.nodes
        left = {canonical(e) for e in self.edges}
        right = {canonical(e) for e in candidate.edges}
        caps = lambda nodes: {c for node in nodes.values() for c in node['capabilities']}
        return {'added_nodes': sorted(after.keys() - before.keys()), 'removed_nodes': sorted(before.keys() - after.keys()),
                'changed_nodes': sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
                'added_edges': [json.loads(x) for x in sorted(right - left)],
                'removed_edges': [json.loads(x) for x in sorted(left - right)],
                'lost_capabilities': sorted(caps(before) - caps(after))}
