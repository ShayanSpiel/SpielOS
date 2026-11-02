"""Source and installed-package entry point: python -B -m company.graph."""
import argparse
import json
from pathlib import Path
import sys

from .model import Graph, implementation
from .runtime import GraphRunner
from .experiments import Experiments
from ..home import CompanyHome, write_json
from ..runtime.boundary import require_runtime_destination


def read(path):
    return json.loads(Path(path).read_text())


def selected_runtime(home):
    if home is None:
        return None
    from ..security import CompanyAuthority
    from ..workflows.runs import WorkflowRuntime
    import os
    company = CompanyHome(home)
    if not company.lean or not (company.root / '.spielos/state/workflows.sqlite').is_file():
        raise ValueError('Select an existing initialized company; this command never installs one')
    authority = CompanyAuthority(company.root)
    token = os.environ.get('SPIELOS_PRINCIPAL_TOKEN')
    principal = authority.authenticate(token) if token else authority.local_owner()
    return WorkflowRuntime(company.root / '.spielos/state/workflows.sqlite', home=company.root, principal=principal)


def explorer(graph, *, output, source_root, trace=None, candidate=None, experiment=None, tests=None):
    """Produce a portable viewer from exactly the supplied graph and evidence files."""
    path = Path(output).expanduser().resolve()
    require_runtime_destination(path)
    sources = {}
    for key, node in graph.nodes.items():
        sources[key] = []
        for ref in [node['implementation'], *[e['implementation'] for e in node['evaluation_requirements']]]:
            try:
                measured = implementation(source_root, ref)
                source = Path(source_root) / measured['path']
                text = source.read_text()[:100000] if source.suffix in {'.py', '.md', '.toml', '.json', '.html', '.ts'} else '(binary or unsupported source preview)'
                sources[key].append({'reference': ref, 'measured': measured, 'text': text})
            except (ValueError, OSError, SyntaxError) as exc:
                sources[key].append({'reference': ref, 'error': str(exc)})
    if trace and trace.get('graph_digest') != graph.digest:
        raise ValueError('Execution trace belongs to a different graph version')
    payload = {'graph': graph.document, 'digest': graph.digest, 'order': graph.order,
               'findings': graph.findings(), 'trace': trace, 'candidate': candidate.document if candidate else None,
               'comparison': graph.compare(candidate) if candidate else None, 'experiment': experiment, 'sources': sources, 'tests': tests}
    encoded = json.dumps(payload, allow_nan=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    template = Path(__file__).with_name('explorer.html').read_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.replace('/*SPIELOS_GRAPH_DATA*/null', encoded))
    return {'explorer': str(path), 'graph_digest': graph.digest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', default=str(Path(__file__).resolve().parents[2]))
    sub = parser.add_subparsers(dest='command', required=True)
    default_graph = str(Path(__file__).with_name('architecture.json'))
    for command in ('validate', 'capture', 'impact', 'compare', 'run', 'explore', 'experiment-prepare'):
        item = sub.add_parser(command)
        item.add_argument('--graph', default=default_graph)
        if command in {'capture', 'explore'}:
            item.add_argument('--output', required=True)
        if command == 'validate':
            item.add_argument('--verify-sources', action='store_true')
        if command == 'impact':
            item.add_argument('nodes', nargs='+')
        if command == 'compare':
            item.add_argument('--candidate', required=True)
        if command == 'run':
            item.add_argument('--inputs', required=True)
            item.add_argument('--request-key', required=True)
        if command == 'experiment-prepare':
            item.add_argument('--benchmarks', required=True)
            item.add_argument('--modification', required=True)
            item.add_argument('--request-key', required=True)
        if command == 'explore':
            item.add_argument('--trace')
            item.add_argument('--candidate')
            item.add_argument('--experiment')
            item.add_argument('--tests', help='Actual unittest evidence JSON: tests array with id/status')
        if command in {'run', 'experiment-prepare'}:
            item.add_argument('--store', required=True)
            item.add_argument('--home')
    for command in ('resume', 'retry', 'show', 'experiment-run'):
        item = sub.add_parser(command)
        item.add_argument('identity')
        item.add_argument('--store', required=True)
        item.add_argument('--home')
        if command == 'retry':
            item.add_argument('--node', required=True)
    args = parser.parse_args(argv)
    try:
        command = args.command
        graph = Graph.load(args.graph) if hasattr(args, 'graph') else None
        if command == 'validate':
            result = {'valid': True, 'digest': graph.digest, 'order': graph.order, 'findings': graph.findings()}
            if args.verify_sources:
                result['sources'] = graph.verify_sources(args.source_root)
        elif command == 'capture':
            require_runtime_destination(args.output)
            captured = graph.capture(args.source_root)
            write_json(args.output, captured.document)
            result = {'snapshot': str(Path(args.output).resolve()), 'digest': captured.digest}
        elif command == 'impact':
            result = graph.impact(args.nodes)
        elif command == 'compare':
            result = graph.compare(Graph.load(args.candidate))
        elif command == 'explore':
            result = explorer(graph, output=args.output, source_root=args.source_root,
                              trace=read(args.trace) if args.trace else None,
                              candidate=Graph.load(args.candidate) if args.candidate else None,
                              experiment=read(args.experiment) if args.experiment else None,
                              tests=read(args.tests) if args.tests else None)
        else:
            runtime = selected_runtime(args.home)
            if command.startswith('experiment-'):
                experiments = Experiments(args.store, source_root=args.source_root, runtime=runtime)
                result = ({'experiment': experiments.prepare(graph, args.benchmarks, read(args.modification), request_key=args.request_key)}
                          if command == 'experiment-prepare' else experiments.run(args.identity))
            else:
                runner = GraphRunner(args.store, source_root=args.source_root, runtime=runtime)
                if command == 'run':
                    result = runner.run(graph, read(args.inputs), request_key=args.request_key)
                elif command == 'retry':
                    result = runner.retry(args.identity, args.node)
                else:
                    result = getattr(runner, command)(args.identity)
        print(json.dumps(result, indent=2, allow_nan=False))
        if command in {'run', 'resume', 'retry'} and result['status'] != 'completed':
            return 2
        if command == 'experiment-run' and result['decision'] != 'eligible_for_independent_review':
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError, SyntaxError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
