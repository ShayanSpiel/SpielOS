"""Local experiment evidence with a durable, privacy-scoped Langfuse projection.

Datasets contain case digests, not unrestricted company inputs. Remote writes
are journaled before transport; an unknown creation is read back, never repeated
blindly. Langfuse v4 experiment attributes link the actual invocation spans.
"""
from __future__ import annotations
import hashlib,json
from urllib.parse import quote,urlencode

SCHEMA='''
CREATE TABLE IF NOT EXISTS workflow_experiments (
 id TEXT PRIMARY KEY,request_key TEXT NOT NULL UNIQUE,release_digest TEXT NOT NULL REFERENCES workflow_releases(digest),
 name TEXT NOT NULL,created_at TEXT NOT NULL,remote_dataset_id TEXT,remote_verified INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS workflow_remote_resources (
 key TEXT PRIMARY KEY,project_id TEXT NOT NULL,kind TEXT NOT NULL,expected_json TEXT NOT NULL,
 status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,reference_json TEXT,last_error TEXT);
CREATE TRIGGER IF NOT EXISTS workflow_resource_identity_immutable BEFORE UPDATE OF key,project_id,kind,expected_json ON workflow_remote_resources
 BEGIN SELECT RAISE(ABORT,'remote resource definitions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_experiment_identity_immutable
 BEFORE UPDATE OF id,request_key,release_digest,name,created_at ON workflow_experiments
 BEGIN SELECT RAISE(ABORT,'experiment identities are immutable'); END;
'''


def hashed(value):return hashlib.sha256(value.encode()).hexdigest()
def dataset_name(release):return 'spielos-release-'+release[:24]
def item_id(release,case):return hashed('spielos-case:'+release+':'+case)


def run_experiment(runtime,release,*,name,request_key):
    from ..workflows.runs import stamp
    actor=runtime._actor('build');manifest=runtime.manifest(release)
    if not isinstance(name,str) or not name.strip() or not isinstance(request_key,str) or not request_key.strip():
        raise ValueError('Experiment needs a name and stable request identity')
    if len(manifest['evaluation']['cases'])>200:raise ValueError('Use a bounded experiment of at most 200 cases')
    identity=hashed('spielos-experiment:'+str(runtime.path.resolve())+':'+request_key)[:32]
    with runtime.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing=connection.execute('SELECT * FROM workflow_experiments WHERE request_key=?',(request_key,)).fetchone()
        if existing:
            if existing['release_digest']!=release or existing['name']!=name:raise ValueError('Experiment request was used for different content')
            identity=existing['id']
        else:
            connection.execute('INSERT INTO workflow_experiments VALUES(?,?,?,?,?,NULL,0)',(identity,request_key,release,name,stamp()))
            runtime._audit(connection,'experiment',identity,{'release_digest':release},actor=actor)
    for case in manifest['evaluation']['cases']:
        run=runtime.run(release,case['input'],request_key=identity+':'+case['id'],candidate_case=case['id'],experiment_id=identity)
        if run['status']=='awaiting_evaluation':runtime.evaluate_run(run['id'])
    return get_experiment(runtime,identity)


def get_experiment(runtime,identity):
    runtime._actor('read')
    with runtime.connect() as connection:
        row=connection.execute('SELECT * FROM workflow_experiments WHERE id=?',(identity,)).fetchone()
        runs=connection.execute("SELECT id,case_id,status,evaluation_json FROM workflow_invocations WHERE experiment_id=? AND kind='candidate' ORDER BY created_at",(identity,)).fetchall()
    if row is None:raise KeyError('Unknown experiment')
    manifest=runtime.manifest(row['release_digest']);expected={case['id']:case['expected'] for case in manifest['evaluation']['cases']}
    reports=[{'run_id':run['id'],'case_id':run['case_id'],'status':run['status'],'evaluation':json.loads(run['evaluation_json'] or 'null')} for run in runs]
    complete=len(reports)==len(expected) and all(run['evaluation'] and run['evaluation']['coverage_complete'] for run in reports)
    from ..evals.standard import matched as case_matched
    cases={case['id']:case for case in manifest['evaluation']['cases']}
    matched=complete and all(case_matched(cases[run['case_id']],run['evaluation']) for run in reports)
    return {**dict(row),'state':'pass' if matched else 'fail' if complete else 'awaiting_evidence','runs':reports,
            'candidate_runs':{run['case_id']:run['run_id'] for run in reports},'production_release_created':False}


def expected_resources(manifest,release,*,payload_policy='digests_only'):
    from ..workflows.runs import digest
    inspectable=payload_policy=='reviewed_evidence'
    basis=digest({'input_schema':manifest['input_schema'],'output_schema':manifest['output_schema'],'evaluation':manifest['evaluation']}) if inspectable else release
    name=(manifest['evaluation'].get('subject','workflow').replace('_',' ').title()+' · '+manifest.get('purpose',manifest['id'])[:100]+' · Evaluation '+str(manifest['evaluation']['version'])+' · '+basis[:8]) if inspectable else dataset_name(release)
    resources=[('dataset',{'name':name,'description':manifest['evaluation'].get('objective','SpielOS immutable case references; canonical inputs and rubrics remain local.'),
        'metadata':{'evaluation_digest':basis,'payload_policy':payload_policy,
                    **({'standard':manifest['evaluation']['standard'],'criteria':manifest['evaluation']['criteria']} if inspectable else {'release_digest':release})},
        **({'inputSchema':manifest['input_schema'],'expectedOutputSchema':manifest['output_schema']} if inspectable else {})})]
    for case in manifest['evaluation']['cases']:
        resources.append(('item',{'id':item_id(basis,case['id']),'datasetName':name,
            'input':case['input'] if inspectable else {'digest':digest(case['input'])},
            'expectedOutput':case['reference'] if inspectable else {'digest':digest(case['reference'])},
            'metadata':{'evaluation_digest':basis,'case_digest':hashed(case['id']),'split':case['split'],
                        'expected_quality':case['expected'],'rubric_version':manifest['evaluation']['version'],'payload_policy':payload_policy,
                        **({'intent':case['intent'],'failure_criteria':case.get('failure_criteria',[])} if inspectable else {'release_digest':release})}}))
    for criterion in manifest['evaluation']['criteria']:
        definition=digest({'release':release,'criterion':criterion})
        resources.append(('score_config',{'name':(criterion.get('question') or criterion['id'])[:120]+' · '+str(manifest['evaluation']['version'])+' · '+definition[:6],'dataType':'CATEGORICAL',
            'categories':[{'label':state,'value':value} for state,value in [('pass',1),('fail',0),('missing',-1),('error',-2),('not_applicable',-3)]],
            'description':criterion.get('question',criterion['id'])+' Rating anchors: '+json.dumps(criterion['anchors'],ensure_ascii=False)+'; evaluator definition '+definition}))
    return resources


def ensure_resources(runtime,client,resources,*,max_attempts=20):
    """Shared durable resource journal for workflow and Director/agent suites."""
    from ..workflows.runs import canonical,digest
    from .langfuse import ExportError
    if not client._project_verified:client.verify_project()
    found=[]
    for kind,expected in resources:
        if kind=='item' and (not found or found[0] is None):
            found.append(None);continue
        key=digest({'project':client.project_id,'kind':kind,'expected':expected})
        with runtime.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT OR IGNORE INTO workflow_remote_resources VALUES(?,?,?,?,'pending',0,NULL,NULL)",(key,client.project_id,kind,canonical(expected)))
            row=connection.execute('SELECT * FROM workflow_remote_resources WHERE key=?',(key,)).fetchone()
            if row['status']=='verified':
                found.append(json.loads(row['reference_json']));continue
            if row['attempts']>=max_attempts:return None
            connection.execute("UPDATE workflow_remote_resources SET status='sending',attempts=attempts+1 WHERE key=?",(key,))
        reference=None;error=None;allow=row['status']=='pending'
        try:
            actual=lookup(client,kind,expected)
            if actual:
                if not matches(kind,expected,actual):raise ExportError('Immutable evaluation resource differs in Langfuse')
                reference={'id':actual['id'],'name':actual.get('name')};status='verified'
            elif allow:
                route={'dataset':'/api/public/v2/datasets','item':'/api/public/dataset-items','score_config':'/api/public/score-configs'}[kind]
                client.request('POST',route,expected);status='awaiting_readback'
            else:status='awaiting_readback'
        except ExportError as exc:
            status='awaiting_readback' if exc.ambiguous or not allow else 'pending';error=str(exc)
        except Exception:
            status='awaiting_readback';error='Evaluation resource transport failed; inspect the scoped connection'
        if status!='verified' and row['attempts']+1>=max_attempts:status='exhausted'
        with runtime.connect() as connection:
            connection.execute('UPDATE workflow_remote_resources SET status=?,reference_json=?,last_error=? WHERE key=?',(status,canonical(reference) if reference else None,error,key))
        found.append(reference)
    return found if all(found) else None


def lookup(client,kind,expected):
    from .langfuse import ExportError
    try:
        if kind=='dataset':return client.request('GET','/api/public/v2/datasets/'+quote(expected['name'],safe=''))
        if kind=='item':return client.request('GET','/api/public/dataset-items/'+quote(expected['id'],safe=''))
        for page in range(1,21):
            result=client.request('GET','/api/public/score-configs?'+urlencode({'page':page,'limit':100}))
            matched=[row for row in result.get('data',[]) if row.get('name')==expected['name']]
            if len(matched)>1:raise ExportError('Score definition identity is ambiguous')
            if matched:return matched[0]
            if page>=result.get('meta',{}).get('totalPages',1):return None
        raise ExportError('Score definition pagination exceeded its bounded budget')
    except ExportError as error:
        if error.status==404:return None
        raise


def matches(kind,expected,actual):
    if not actual or not actual.get('id'):return False
    if kind=='dataset':return actual.get('name')==expected['name'] and all((actual.get('metadata') or {}).get(key)==value for key,value in expected['metadata'].items())
    if kind=='item':return actual.get('id')==expected['id'] and actual.get('input')==expected['input'] and actual.get('expectedOutput')==expected['expectedOutput'] and all((actual.get('metadata') or {}).get(key)==value for key,value in expected['metadata'].items())
    return (actual.get('name')==expected['name'] and actual.get('dataType')==expected['dataType'] and
            actual.get('description')==expected['description'] and
            {(row['label'],float(row['value'])) for row in actual.get('categories',[])}=={(row['label'],float(row['value'])) for row in expected['categories']})


def definitions(runtime,manifest,release):
    from .sessions import reviewed,sanitize
    mode='reviewed_evidence' if reviewed(runtime) else 'digests_only'
    return sanitize(expected_resources(manifest,release,payload_policy=mode))


def sync_resources(runtime,client,*,max_attempts=20):
    with runtime.connect() as connection:
        experiments=connection.execute('SELECT * FROM workflow_experiments ORDER BY created_at LIMIT 50').fetchall()
    for experiment in experiments:
        manifest=runtime.manifest(experiment['release_digest'])
        found=ensure_resources(runtime,client,definitions(runtime,manifest,experiment['release_digest']),max_attempts=max_attempts)
        if found:
            with runtime.connect() as connection:
                connection.execute('UPDATE workflow_experiments SET remote_dataset_id=? WHERE id=?',(found[0]['id'],experiment['id']))


def resource_projection(runtime,project_id,manifest,release):
    from ..workflows.runs import digest
    found=[]
    with runtime.connect() as connection:
        for kind,expected in definitions(runtime,manifest,release):
            key=digest({'project':project_id,'kind':kind,'expected':expected})
            row=connection.execute('SELECT status,reference_json FROM workflow_remote_resources WHERE key=?',(key,)).fetchone()
            if not row or row['status']!='verified':return None
            found.append((kind,expected,json.loads(row['reference_json'])))
    configs={criterion['id']:reference for criterion,(_,_,reference) in zip(manifest['evaluation']['criteria'],[row for row in found if row[0]=='score_config'])}
    return {'dataset_id':found[0][2]['id'],'score_configs':configs}


def enrich_event(runtime,client,event):
    identity=event.get('experiment_id')
    if not identity:return event
    with runtime.connect() as connection:experiment=connection.execute('SELECT * FROM workflow_experiments WHERE id=?',(identity,)).fetchone()
    if not experiment:raise ValueError('Experiment event lost its local authority')
    manifest=runtime.manifest(experiment['release_digest'])
    resources=resource_projection(runtime,client.project_id,manifest,experiment['release_digest'])
    if not resources:return None
    case=next(row for row in manifest['evaluation']['cases'] if row['id']==event['experiment_case'])
    return {**event,'experiment':{'id':identity,'name':experiment['name'],
        'dataset_id':resources['dataset_id'],'item_id':next(expected['id'] for kind,expected in definitions(runtime,manifest,experiment['release_digest']) if kind=='item' and expected['metadata']['case_digest']==hashed(case['id'])),
        'expected_output':case['reference'] if event.get('context_export')=='reviewed_evidence' else {'digest':hashed(json.dumps(case['reference'],sort_keys=True,separators=(',',':'),allow_nan=False))}},
        'score_configs':resources['score_configs']}


def confirm_experiments(runtime,client):
    """Confirm the v4 experiment and every item root, not just HTTP acceptance."""
    from .langfuse import identities,ExportError
    with runtime.connect() as connection:experiments=connection.execute('SELECT * FROM workflow_experiments WHERE remote_dataset_id IS NOT NULL AND remote_verified=0 ORDER BY created_at LIMIT 50').fetchall()
    for experiment in experiments:
        manifest=runtime.manifest(experiment['release_digest'])
        with runtime.connect() as connection:
            pending=connection.execute("SELECT COUNT(*) FROM workflow_export_outbox e JOIN workflow_invocations i ON i.id=e.run_id WHERE i.experiment_id=? AND e.status!='verified'",(experiment['id'],)).fetchone()[0]
            roots=connection.execute("SELECT i.case_id,e.payload_json FROM workflow_invocations i JOIN workflow_export_outbox e ON e.rowid=(SELECT MIN(x.rowid) FROM workflow_export_outbox x WHERE x.run_id=i.id) WHERE i.experiment_id=? AND i.kind='candidate'",(experiment['id'],)).fetchall()
        if pending or not roots:continue
        query={'fields':'core','fromStartTime':experiment['created_at'],'id':experiment['id'],'limit':100}
        response=client.request('GET','/api/public/experiments?'+urlencode(query))
        matches_=[row for row in response.get('data',[]) if row.get('id')==experiment['id']]
        if not matches_:continue
        remote=matches_[0]
        if remote.get('datasetId')!=experiment['remote_dataset_id'] or remote.get('name')!=experiment['name']:
            raise ExportError('Remote experiment identity differs from the local experiment')
        expected=set()
        for root in roots:
            event=json.loads(root['payload_json']);trace,span=identities(event)
            expected.add((span,trace,next(expected['id'] for kind,expected in definitions(runtime,manifest,experiment['release_digest']) if kind=='item' and expected['metadata']['case_digest']==hashed(root['case_id']))))
        actual=set();cursor=None
        for _ in range(10):
            params={'fields':'core,dataset','fromStartTime':experiment['created_at'],'experimentId':experiment['id'],'limit':100}
            if cursor:params['cursor']=cursor
            response=client.request('GET','/api/public/experiment-items?'+urlencode(params))
            for row in response.get('data',[]):
                if row.get('experimentId')==experiment['id']:
                    if row.get('experimentDatasetId')!=experiment['remote_dataset_id']:raise ExportError('Experiment item dataset differs from the pinned reference')
                    actual.add((row['id'],row['traceId'],row['experimentItemId']))
            cursor=(response.get('meta') or {}).get('cursor')
            if not cursor:break
        else:raise ExportError('Experiment item pagination exceeded its bounded budget')
        if actual==expected and remote.get('itemCount')==len(expected):
            with runtime.connect() as connection:connection.execute('UPDATE workflow_experiments SET remote_verified=1 WHERE id=?',(experiment['id'],))
