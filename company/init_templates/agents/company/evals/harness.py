"""Subject-independent suites, actual executions, ratings and bounded comparisons."""
from __future__ import annotations
import json

SCHEMA = '''
CREATE TABLE IF NOT EXISTS evaluation_suites (
 digest TEXT PRIMARY KEY, suite_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evaluation_experiments (
 id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, suite_digest TEXT NOT NULL,
 name TEXT NOT NULL, task_revision TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evaluation_items (
 experiment_id TEXT NOT NULL, case_id TEXT NOT NULL, session_id TEXT NOT NULL,
 event_id TEXT NOT NULL, report_json TEXT NOT NULL, PRIMARY KEY(experiment_id,case_id));
CREATE TABLE IF NOT EXISTS evaluation_confirmations (
 experiment_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, reference TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS evaluation_suite_no_update BEFORE UPDATE ON evaluation_suites
 BEGIN SELECT RAISE(ABORT,'evaluation suites are immutable'); END;
CREATE TRIGGER IF NOT EXISTS evaluation_suite_no_delete BEFORE DELETE ON evaluation_suites
 BEGIN SELECT RAISE(ABORT,'evaluation suites are preserved'); END;
CREATE TRIGGER IF NOT EXISTS evaluation_experiment_no_update BEFORE UPDATE ON evaluation_experiments
 BEGIN SELECT RAISE(ABORT,'experiment hypotheses and task revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS evaluation_item_no_update BEFORE UPDATE ON evaluation_items
 BEGIN SELECT RAISE(ABORT,'experiment observations are immutable'); END;
'''


class EvaluationHarness:
    def __init__(self, runtime):
        self.runtime = runtime
        if not runtime.readonly:
            with runtime.connect() as connection:
                connection.executescript(SCHEMA)

    def register(self, suite):
        from copy import deepcopy
        from pathlib import Path
        import hashlib
        from .standard import validate_suite
        from . import contracts,standard
        from ..workflows.runs import canonical, digest, stamp
        self.runtime._actor('build')
        suite=deepcopy(suite)
        if self.runtime.authority:
            for criterion in suite.get('evaluation',{}).get('criteria',[]):
                if criterion.get('evaluator')!='model':continue
                judge=criterion.get('judge',{})
                with self.runtime.connect() as connection:
                    record=connection.execute('SELECT record_json FROM workflow_judge_calibrations WHERE id=?',(judge.get('calibration_id'),)).fetchone()
                if not record:raise ValueError('A suite model judge needs independently authenticated calibration')
                calibration=json.loads(record[0])
                if any(judge.get(key)!=calibration['judge'][key] for key in ('model','prompt_digest','version')):
                    raise ValueError('Suite judge differs from its actual calibration')
                judge['calibration']=calibration['ratings'];judge['maximum_disagreement']=calibration['policy']['maximum_disagreement']
        validate_suite(suite)
        suite['evaluation']['implementation_digest']=hashlib.sha256(Path(contracts.__file__).read_bytes()).hexdigest()
        suite['evaluation']['standard_implementation_digest']=hashlib.sha256(Path(standard.__file__).read_bytes()).hexdigest()
        identity = digest(suite)
        with self.runtime.connect() as connection:
            connection.execute('INSERT OR IGNORE INTO evaluation_suites VALUES(?,?,?)', (identity, canonical(suite), stamp()))
        from ..observability.sessions import Sessions
        sessions=Sessions(self.runtime)
        session=sessions.start(host='manual',host_session='suite:'+identity,role='builder',coverage={
            'source':'evaluation suite registration','execution':'specification only; no task or model was executed'})
        sessions.record(session['id'],kind='decision',request_key='suite-definition',payload={
            'suite_definition':identity,'suite':suite,'state':'Registered specification; actual executions and independent ratings are required'})
        return identity

    def suite(self, identity):
        self.runtime._actor('read')
        with self.runtime.connect() as connection:
            row = connection.execute('SELECT suite_json FROM evaluation_suites WHERE digest=?', (identity,)).fetchone()
        if not row:
            raise KeyError('Unknown evaluation suite')
        return json.loads(row[0])

    def experiment(self, suite_digest, *, task, name, request_key, timeout_seconds=30):
        """Actually execute a trusted importable task. No recorded fixture is an agent run."""
        from ..workflows.runs import LocalAdapter, canonical, digest, stamp
        from ..observability.sessions import Sessions
        actor = self.runtime._actor('build')
        suite = self.suite(suite_digest)
        if not name or not request_key or not 1 <= timeout_seconds <= 300 or len(suite['evaluation']['cases']) > 200:
            raise ValueError('Experiment needs a name, stable request and bounded execution budget')
        adapter = LocalAdapter(task)
        identity = digest({'database': str(self.runtime.path.resolve()), 'request': request_key})[:32]
        with self.runtime.connect() as connection:
            existing = connection.execute('SELECT * FROM evaluation_experiments WHERE request_key=?', (request_key,)).fetchone()
            if existing and (existing['suite_digest'] != suite_digest or existing['task_revision'] != adapter.revision or existing['name'] != name):
                raise ValueError('Experiment identity was reused with another suite, task or hypothesis')
            connection.execute('INSERT OR IGNORE INTO evaluation_experiments VALUES(?,?,?,?,?,?,?)', (identity, request_key, suite_digest, name, adapter.revision, actor, stamp()))
        sessions = Sessions(self.runtime)
        for case in suite['evaluation']['cases']:
            with self.runtime.connect() as connection:
                if connection.execute('SELECT event_id FROM evaluation_items WHERE experiment_id=? AND case_id=?', (identity, case['id'])).fetchone():
                    continue
            session = sessions.start(host='python', host_session=identity+':'+case['id'], role='builder', coverage={
                'source': 'actual bounded Python task invocation', 'task_revision': adapter.revision,
                'subject': suite['evaluation']['subject'], 'model_quality': 'not established by deterministic software tests'})
            # The committed invocation event prevents an uncertain experiment from
            # silently rerunning the task after a process crash.
            invocation_key = 'invocation'
            if any(e['request_key'] == invocation_key for e in sessions.show(session['id'])['events']):
                continue
            sessions.record(session['id'], kind='decision', request_key=invocation_key, payload={
                'input': case['input'], 'task_revision': adapter.revision, 'case': case['id'], 'state': 'dispatch committed'})
            result = adapter.start(request_id=identity+':'+case['id'], manifest={'execution': {'timeout_seconds': timeout_seconds}}, inputs=case['input'])
            if result.get('status') != 'completed':
                sessions.record(session['id'], kind='tool', request_key='execution-error', payload={'status': result.get('status'), 'error': result.get('error'), 'source': 'task adapter'})
                continue
            self._evaluate(suite_digest, case, session['id'], result['output'], identity, adapter.revision)
        return self.show(identity)

    def _evaluate(self, suite_digest, case, session_id, output, experiment_id=None, task_revision=None, *, verdicts=None, producer=None):
        from ..observability.sessions import Sessions
        from ..workflows.runs import canonical
        suite = self.suite(suite_digest)
        actor = self.runtime._actor('evaluate')
        report = self.runtime.evaluate(suite, output, inputs=case['input'], case_id=case['id'], verdicts=verdicts, evaluator=actor, producer=producer)
        payload = {'input': case['input'], 'output': output, 'expected_output': case['reference'],
                   'intent': case['intent'], 'suite_digest': suite_digest, 'report': report,
                   'task_revision': task_revision, 'source': 'actual execution output',
                   **({'experiment_ref': {'id': experiment_id, 'suite_digest': suite_digest, 'case_id': case['id']}} if experiment_id else {})}
        event = Sessions(self.runtime).record(session_id, kind='evaluation', request_key='evaluation:'+case['id'], payload=payload)
        if experiment_id:
            with self.runtime.connect() as connection:
                connection.execute('INSERT OR IGNORE INTO evaluation_items VALUES(?,?,?,?,?)', (experiment_id, case['id'], session_id, event['id'], canonical(report)))
        return event

    def evaluate_event(self, suite_digest, *, case_id, session_id, event_id, verdicts=None):
        """Score an actual captured host output; preserve producer attribution."""
        from ..observability.sessions import Sessions
        session = Sessions(self.runtime).show(session_id)
        event = next((e for e in session['events'] if e['id'] == event_id), None)
        if not event or 'output' not in event['record']['payload']:
            raise ValueError('Evaluation needs an existing event containing actual output')
        suite = self.suite(suite_digest)
        case = next((c for c in suite['evaluation']['cases'] if c['id'] == case_id), None)
        if not case or event['record']['payload'].get('input') != case['input']:
            raise ValueError('Captured input must match the case actually being evaluated')
        return self._evaluate(suite_digest, case, session_id, event['record']['payload']['output'],
                              verdicts=verdicts, producer=event['actor'])

    def show(self, experiment_id):
        from .standard import matched
        self.runtime._actor('read')
        with self.runtime.connect() as connection:
            row = connection.execute('SELECT * FROM evaluation_experiments WHERE id=?', (experiment_id,)).fetchone()
            items = [dict(x) for x in connection.execute('SELECT * FROM evaluation_items WHERE experiment_id=? ORDER BY case_id', (experiment_id,))]
            exports = [dict(x) for x in connection.execute('SELECT x.status,x.remote_reference FROM activity_exports x JOIN evaluation_items i ON i.event_id=x.id WHERE i.experiment_id=?', (experiment_id,))]
            confirmation=connection.execute('SELECT * FROM evaluation_confirmations WHERE experiment_id=?',(experiment_id,)).fetchone()
        if not row:
            raise KeyError('Unknown evaluation experiment')
        suite = self.suite(row['suite_digest'])
        cases = {c['id']: c for c in suite['evaluation']['cases']}
        for item in items:
            item['report'] = json.loads(item.pop('report_json'))
            item['matched'] = matched(cases[item['case_id']], item['report'])
        complete = len(items) == len(cases)
        local_pass = complete and all(x['matched'] for x in items)
        observable = bool(confirmation) and bool(exports) and len(exports) == len(cases) and all(e['status'] == 'verified' for e in exports)
        return {**dict(row), 'items': items, 'coverage_complete': complete, 'local_pass': local_pass,
                'observable': observable, 'state': 'verified_pass' if local_pass and observable else 'awaiting_telemetry' if local_pass else 'failed' if complete else 'awaiting_evidence',
                'model_behavior_qualified': False, 'production_release_created': False}

    def verify(self, client, experiment_id):
        """Read back the remote experiment and exact item roots, not only its spans."""
        from urllib.parse import urlencode
        from ..observability.experiments import definitions,hashed
        from ..observability.langfuse import identities,ExportError
        experiment=self.show(experiment_id)
        if not experiment['coverage_complete']:return False
        with self.runtime.connect() as connection:
            events=[(row['case_id'],json.loads(row['payload_json']),row['status']) for row in connection.execute('SELECT i.case_id,x.payload_json,x.status FROM evaluation_items i JOIN activity_exports x ON x.id=i.event_id WHERE i.experiment_id=?',(experiment_id,))]
        if any(status!='verified' for _,_,status in events):return False
        suite=self.suite(experiment['suite_digest'])
        resources=definitions(self.runtime,suite,experiment['suite_digest'])
        dataset_name=resources[0][1]['name']
        from ..observability.experiments import lookup
        dataset=lookup(client,'dataset',resources[0][1])
        if not dataset:return False
        response=client.request('GET','/api/public/experiments?'+urlencode({'fromStartTime':experiment['created_at'],'id':experiment_id,'fields':'core','limit':10}))
        remote=next((row for row in response.get('data',[]) if row['id']==experiment_id),None)
        if not remote:return False
        if remote.get('datasetId')!=dataset['id']:raise ExportError('Evaluation experiment dataset differs from the pinned suite')
        expected=set()
        for case_id,event,_ in events:
            trace,span=identities(event)
            item=next(expected['id'] for kind,expected in resources if kind=='item' and expected['metadata']['case_digest']==hashed(case_id))
            expected.add((span,trace,item))
        actual=set();cursor=None
        for _ in range(10):
            params={'fromStartTime':experiment['created_at'],'experimentId':experiment_id,'fields':'core,dataset','limit':100}
            if cursor:params['cursor']=cursor
            result=client.request('GET','/api/public/experiment-items?'+urlencode(params))
            for row in result.get('data',[]):
                if row.get('experimentId')==experiment_id:actual.add((row['id'],row['traceId'],row['experimentItemId']))
            cursor=(result.get('meta') or {}).get('cursor')
            if not cursor:break
        else:raise ExportError('Evaluation experiment verification exceeded its pagination budget')
        if actual!=expected or remote.get('itemCount')!=len(expected):return False
        with self.runtime.connect() as connection:
            connection.execute('INSERT OR IGNORE INTO evaluation_confirmations VALUES(?,?,?)',(experiment_id,client.project_id,client.base_url+'/project/'+client.project_id+'/datasets/'+dataset['id']))
        return True

    def compare(self, baseline, candidate):
        """Paired cases, fixed judge and actual observations; never automatic promotion."""
        left, right = self.show(baseline), self.show(candidate)
        if left['suite_digest'] != right['suite_digest']:
            raise ValueError('Comparison requires the same immutable dataset and evaluator contract')
        if not left['coverage_complete'] or not right['coverage_complete']:
            raise ValueError('Comparison requires complete actual executions of both variants')
        before = {x['case_id']: x for x in left['items']}
        regressions = [x['case_id'] for x in right['items'] if before[x['case_id']]['matched'] and not x['matched']]
        improvements = [x['case_id'] for x in right['items'] if not before[x['case_id']]['matched'] and x['matched']]
        return {'baseline': baseline, 'candidate': candidate, 'regressions': regressions, 'improvements': improvements,
                'observable': left['observable'] and right['observable'],
                'eligible_for_review': right['local_pass'] and left['observable'] and right['observable'] and not regressions,
                'promotion': 'requires independent review', 'causal_business_impact': 'unmeasured'}


def enrich_suite_event(runtime, client, event):
    from ..observability.experiments import definitions, ensure_resources, hashed
    ref = event.get('suite_experiment')
    definition=event.get('suite_definition')
    if not ref and not definition:
        return event
    suite_digest=ref['suite_digest'] if ref else definition
    suite = EvaluationHarness(runtime).suite(suite_digest)
    resources = definitions(runtime, suite, suite_digest)
    found = ensure_resources(runtime, client, resources)
    if not found:
        return None
    if not ref:return event
    case = next(c for c in suite['evaluation']['cases'] if c['id'] == ref['case_id'])
    item = next(expected['id'] for kind, expected in resources if kind == 'item' and expected['metadata']['case_digest'] == hashed(case['id']))
    configs = {criterion['id']: response for criterion, response in zip(suite['evaluation']['criteria'], [response for (kind, _), response in zip(resources, found) if kind == 'score_config'])}
    with runtime.connect() as c:name=c.execute('SELECT name FROM evaluation_experiments WHERE id=?',(ref['id'],)).fetchone()[0]
    return {**event, 'root_event_id': event['id'], 'experiment': {'id': ref['id'], 'name': name,
            'dataset_id': found[0]['id'], 'item_id': item, 'expected_output': case['reference']}, 'score_configs': configs}


def dispatch_evaluation(runtime, action, payload, *, subject=None):
    if action=='pending':
        from ..observability.automatic import pending
        return {'requests':pending(runtime,**payload)}
    if action=='judge':
        from ..observability.automatic import submit
        return submit(runtime,**payload)
    if action=='template':
        from .standard import starter_suite
        return starter_suite(subject or payload['subject'])
    harness=EvaluationHarness(runtime)
    if action=='register':return {'suite_digest':harness.register(payload['suite'])}
    if action=='show':return harness.show(payload['experiment_id'])
    if action=='compare':return harness.compare(payload['baseline'],payload['candidate'])
    if action=='evaluate-event':return harness.evaluate_event(**payload)
    raise ValueError('Unknown evaluation operation')
