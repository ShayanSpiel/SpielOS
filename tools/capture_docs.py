#!/usr/bin/env python3
"""Prepare a synthetic home and actual CLI/hook transcript for documentation capture.

Prints private local capture paths. Screenshot with a browser separately. Nothing
is installed in source, and no host model, external service or production data is used.
"""
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from company.runtime.bootstrap import scaffold
from company.mcp import CompanySession
from company.context.workflow import WorkflowMemory
from company.reporting import ensure_server


def prepare():
    root = Path(tempfile.mkdtemp(prefix='spielos-docs-'))
    home = root / 'example-company'
    scaffold(home, keep_stale=True)
    selected = CompanySession()
    choice = selected.select(str(home))
    runtime = selected.runtime(choice['company_id'])
    memory = WorkflowMemory(runtime)
    memory.add(scope='owner', claim='Never include customer identifiers in public examples.',
        source='Synthetic owner direction', topics=['privacy'], critical=True)
    memory.add(scope='strategy', claim='Make weekly sales reporting reproducible.',
        source='Synthetic owner direction', topics=['sales'])
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
    env.pop('SPIELOS_PRINCIPAL_TOKEN', None)
    transcript = []
    for args in (['--version'], ['status', '--home', str(home)], ['layout', '--home', str(home)]):
        result = subprocess.run([sys.executable, '-B', '-m', 'company', *args],
            env=env, cwd=root, capture_output=True, text=True, check=True)
        command = 'spielos ' + ' '.join(args).replace(str(home), '/path/to/example-company')
        transcript.append('$ ' + command + '\n' + result.stdout.replace(str(home), '/path/to/example-company').strip())
    hook = subprocess.run([sys.executable, '-B', str(home / '.codex/hooks/spielos-context.py')],
        input=json.dumps({'cwd': str(home), 'hook_event_name': 'UserPromptSubmit',
            'prompt': 'Prepare weekly sales totals'}), capture_output=True, text=True, check=True)
    context = json.loads(hook.stdout)['hookSpecificOutput']['additionalContext']
    assert 'Never include customer identifiers' in context and 'injection failed' not in context
    # Omit machine payloads and host instructions; display actual supplied context.
    context = context.split('Machine reference:')[0].strip()
    context = context[context.index('Relevant owner/workflow context'):]
    transcript.append('Actual Codex hook context excerpt (synthetic company)\n' + context)
    body = html.escape('\n\n'.join(transcript))
    page = root / 'commands.html'
    page.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>SpielOS commands and Codex context</title>
<style>body{margin:0;padding:40px;background:#0b0f1a;color:#e2e8f0;font:17px/1.7 system-ui}small{color:#94a3b8}pre{padding:25px;background:#111827;border:1px solid #334155;border-radius:10px;white-space:pre-wrap;font:15px/1.7 ui-monospace,monospace}</style>
<h1>Company state, back in context.</h1><small>Actual CLI output and Codex hook output · synthetic company · no model session or independent acceptance</small><pre>''' + body + '</pre></html>')
    server = ensure_server(home, port=0)
    metadata = {'home': str(home), 'transcript': str(page), **server}
    (root / 'capture.json').write_text(json.dumps(metadata))
    print(json.dumps(metadata))


if __name__ == '__main__':
    prepare()
