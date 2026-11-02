#!/usr/bin/env python3
"""Verify an installed release from an isolated synthetic home, never source imports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(python, expected):
    python = os.path.abspath(os.path.expanduser(python))
    env = {k: v for k, v in os.environ.items() if k not in {
        'PYTHONPATH', 'SPIELOS_HOME', 'SPIELOS_TEMPLATE_DIR', 'SPIELOS_PRINCIPAL_TOKEN'}}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    with tempfile.TemporaryDirectory(prefix='spielos-wheel-smoke-') as directory:
        root = Path(directory).resolve()
        home = root / 'example-company'
        checks = []

        def cli(*args, fail=False):
            result = subprocess.run([python, '-I', '-B', '-m', 'company.cli', *map(str, args)],
                cwd=root, env=env, capture_output=True, text=True, timeout=60)
            if fail:
                assert result.returncode != 0, result.stdout
            elif result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            checks.append(' '.join(map(str, args)))
            return result.stdout

        assert cli('--version').strip() == 'spielos ' + expected
        cli('init', '--dir', home, '-y', '--json')
        assert (home / '.spielos/runtime/company/__main__.py').is_file()
        assert (home / '.agents/company').resolve() == home / '.spielos/runtime/company'
        for command in ('status', 'context', 'catalog', 'layout'):
            json.loads(cli(command, '--home', home, '--json'))
        json.loads(cli('profile', 'show', '--home', home, '--json'))
        json.loads(cli('memory', 'summary', '--home', home, '--json'))
        report = json.loads(cli('report', '--snapshot', '--home', home, '--json'))
        assert report['totals']['production_runs'] == 0
        assert report['totals']['workflows'] == 1
        candidate = json.loads(cli('workflow', 'candidate', '--home', home, '--manifest',
            home / 'company/workflows/sales-report/workflow.json', '--json'))
        experiment = json.loads(cli('workflow', 'experiment', '--home', home, '--release',
            candidate['release_digest'], '--name', 'Installed wheel qualification',
            '--request-key', 'wheel-smoke', '--json'))
        assert experiment['state'] == 'pass', experiment
        report = json.loads(cli('report', '--snapshot', '--home', home, '--json'))
        assert report['totals']['candidate_runs'] == 3
        assert report['totals']['production_runs'] == 0
        voice = home / 'company/brand/voice.md'
        voice.write_text('Synthetic owner voice survives an update.\n')
        cli('update', '--dir', home, '--keep-stale', '--json')
        assert voice.read_text() == 'Synthetic owner voice survives an update.\n'
        assert 'runner' not in cli('--help')
        assert not (home / '.spielos/state/company.sqlite').exists()
        print(json.dumps({'version': expected, 'checks': len(checks),
            'result': 'passed', 'scope': 'isolated installed-wheel local journey'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True)
    parser.add_argument('--expected', required=True)
    args = parser.parse_args()
    run(args.python, args.expected)
