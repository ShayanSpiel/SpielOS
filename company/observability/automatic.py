"""Bounded lifecycle evaluation using the selected host, never a pursuit loop."""
from __future__ import annotations
import json
import time
import uuid
import os

SCHEMA = '''
CREATE TABLE IF NOT EXISTS activity_turn_heads(session_id TEXT PRIMARY KEY,turn_key TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activity_turns(session_id TEXT NOT NULL,turn_key TEXT NOT NULL,title TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(session_id,turn_key));
CREATE TABLE IF NOT EXISTS host_evaluation_requests(
 id TEXT PRIMARY KEY,session_id TEXT NOT NULL,turn_key TEXT NOT NULL,subject TEXT NOT NULL,
 request_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL, UNIQUE(session_id,turn_key,subject));
CREATE TABLE IF NOT EXISTS host_evaluation_verdicts(id TEXT PRIMARY KEY,request_id TEXT NOT NULL,verdict_json TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS host_verdict_immutable BEFORE UPDATE ON host_evaluation_verdicts BEGIN SELECT RAISE(ABORT,'host verdicts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS host_verdict_preserved BEFORE DELETE ON host_evaluation_verdicts BEGIN SELECT RAISE(ABORT,'host verdict history is preserved'); END;
'''

RUBRIC = [
    {'id':'Request fulfilled','question':'Does the answer deliver the owner’s requested result and respect the stated scope?',
     'pass':'The requested result is delivered, or a precise evidenced blocker is reported; scope is respected.',
     'fail':'The answer substitutes planning for authorized work, misses a requested result, or silently broadens scope.'},
    {'id':'Evidence and honest status','question':'Are completion and quality claims supported by actual tool results or inspected artifacts?',
     'pass':'Claims cite observable results and distinguish completed, pending, unknown and unverified work.',
     'fail':'A claim contradicts tool evidence, treats file presence as quality, or invents verification, usage or impact.'},
    {'id':'Feedback and boundaries','question':'Does feedback affect the correct order, workflow, build or evaluation without silently changing reusable policy?',
     'pass':'Applicable feedback is interpreted and its effect is recorded against the correct target; approvals stay separate.',
     'fail':'Feedback is ignored, applied globally without authority, or treated as publishing permission.'},
    {'id':'Clear owner communication','question':'Can the owner understand what happened, what changed, and what remains unresolved?',
     'pass':'The answer uses readable names, concrete outcomes and reasons; machine identifiers are supporting references.',
     'fail':'The answer is dominated by identifiers or vague success claims, or hides a material limitation.'},
    {'id':'Registered workflow boundaries','question':'When work uses or changes a workflow, is there an actual registered Run or bounded Improvement rather than an unsupported completion claim?',
     'pass':'Workflow work cites the actual version/run and change scope; free-chat drafts are identified accurately. A greeting or ordinary question does not create work.',
     'fail':'The answer claims a workflow/agent run or improvement completed from direct tool activity without the corresponding registered evidence.'},
    {'id':'Mandatory evaluator definitions','question':'For any workflow or agent built or changed, are its evaluation rubric, model/runtime binding and native Langfuse definition actually established?',
     'pass':'Actual definition/evaluation evidence is present, or missing qualification is explicitly reported as pending; no pass is inferred from creating files.',
     'fail':'The answer declares a new workflow or agent ready without the paired evaluation definition and attributable evidence.'},
]


def enabled(runtime):
    from .sessions import policy
    return policy(runtime).get('automatic',{}).get('enabled') is True


def prepare(runtime):
    if runtime.readonly:return
    with runtime.connect() as c:c.executescript(SCHEMA)


def turn(sessions,session_id,request):
    from ..workflows.runs import stamp
    runtime=sessions.runtime;prepare(runtime)
    event=request.get('hook_event_name') or request.get('hookEventName')
    with runtime.connect() as c:
        current=c.execute('SELECT turn_key FROM activity_turn_heads WHERE session_id=?',(session_id,)).fetchone()
        key=request.get('turn_id') or (current[0] if current and event!='UserPromptSubmit' else 'local-'+uuid.uuid4().hex)
        if current and current[0].startswith('local-') and event not in {'UserPromptSubmit','SessionStart'}:key=current[0]
        title=' '.join(str(request.get('prompt') or request.get('user_prompt') or '').split())[:100]
        c.execute('INSERT OR IGNORE INTO activity_turns VALUES(?,?,?,?)',(session_id,key,title or 'Director work',stamp()))
        c.execute('INSERT INTO activity_turn_heads VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET turn_key=excluded.turn_key',(session_id,key))
    sessions.turn_key=key
    return key


def request_judgment(runtime,session_id,turn_key,*,subject,inputs,output,rubric,model=None,target=None):
    from ..workflows.runs import canonical,digest,stamp
    from .sessions import sanitize
    prepare(runtime)
    frozen=sanitize({'subject':subject,'input':inputs,'output':output,'rubric':rubric,'model':model,
                     'runtime':'selected host model','target':target,'artifact_digest':digest(output),
                     'instructions':'Judge this frozen result using the current host model. Do not repair or replace it. Return an evidence-based verdict for every criterion. This diagnostic review does not grant independent acceptance.'})
    identity=digest({'session':session_id,'turn':turn_key,'subject':subject})
    with runtime.connect() as c:
        c.execute("INSERT OR IGNORE INTO host_evaluation_requests VALUES(?,?,?,?,?,'pending',?)",(identity,session_id,turn_key,subject,canonical(frozen),stamp()))
    return identity


def evaluate_turn(sessions,session_id,turn_key,*,model=None):
    from ..workflows.runs import digest
    runtime=sessions.runtime;prepare(runtime)
    with runtime.connect() as c:
        rows=c.execute("SELECT id,record_json FROM activity_events WHERE session_id=? AND json_extract(record_json,'$.turn_key')=? ORDER BY rowid LIMIT 501",(session_id,turn_key)).fetchall()
    with runtime.connect() as c:
        prior=c.execute("SELECT id FROM host_evaluation_requests WHERE session_id=? AND turn_key=? AND subject='Director turn'",(session_id,turn_key)).fetchone()
    if prior:return prior[0]
    records=[json.loads(r['record_json']) for r in rows]
    prompts=[r['payload'].get('text') for r in records if r['kind']=='message' and r['payload'].get('speaker')=='owner']
    answers=[r['payload'].get('output') for r in records if r['kind']=='message' and r['payload'].get('speaker')=='assistant']
    tools=[{'name':r['payload'].get('tool_name','Tool'),'error':r['payload'].get('error'),'response':str(r['payload'].get('tool_response',''))[:1500]} for r in records if r['kind']=='tool'][-100:]
    context=[r['payload'] for r in records if r['kind']=='context']
    inputs={'request':prompts[0] if prompts else None,'context_sources':[list(r.get('documents',{})) for r in context],
            'context':context[-1].get('documents',{}) if context else {},
            'tools':tools,'tool_evidence_window':'Last 100 captured calls; response excerpts are limited to 1500 characters. Full individual events remain in the activity journal.',
            'evidence_event_ids':[r['id'] for r in rows],'captured_events':len(rows),'coverage_complete':len(rows)<=500}
    output=answers[0] if answers else None
    rid=request_judgment(runtime,session_id,turn_key,subject='Director turn',inputs=inputs,output=output,rubric=RUBRIC,model=model)
    # These checks describe evidence coverage, not answer quality.
    checks={
        'Owner request captured':('pass' if prompts else 'missing','The owner request is available.' if prompts else 'No owner request was exposed for this turn.'),
        'Supplied context traceable':('pass' if context else 'missing','Supplied documents and changes are recorded.' if context else 'This turn has no captured context snapshot.'),
        'Final answer captured':('pass' if output else 'missing','The frozen host answer is available.' if output else 'The host did not expose a final answer.'),
        'Reported tool failures':('fail' if any(t['error'] for t in tools) else 'missing' if tools else 'not_applicable','Explicitly reported tool errors: '+str(sum(bool(t['error']) for t in tools))+'; unreported success is not assumed.'),
        'Capture coverage':('pass' if len(rows)<=500 else 'missing','Captured '+str(len(rows))+' events; the bounded inspection limit is 500.'),
        'Codex quality review':('missing','A frozen review request is assigned to the selected host model; no semantic pass is inferred from logging.'),
    }
    report={'state':'missing','case_id':None,'rubric_version':'Director continuous review v1','release_digest':'director-continuous-v1',
            'artifact_digest':digest(output),'coverage_complete':False,'quality_domain':'director_behavior','business_outcome':'unmeasured',
            'criteria':{name:{'state':state,'reason':reason,'score':None,'evaluator_version':'Lifecycle evidence checks v1','dimension':'operational'} for name,(state,reason) in checks.items()}}
    sessions.record(session_id,kind='evaluation',request_key='turn-evidence:'+turn_key,payload={
        'input':inputs,'output':{'answer':output,'governance':report['criteria'],'quality_review':'Pending host-model review','review_request':rid},
        'report':report,'category':'director_turn','evaluation_request':rid,'model':model})
    return rid


def pending(runtime,*,session_id=None,limit=3):
    runtime._actor('read');prepare(runtime)
    with runtime.connect() as c:
        rows=c.execute("SELECT * FROM host_evaluation_requests WHERE status='pending'"+(' AND session_id=?' if session_id else '')+' ORDER BY created_at LIMIT ?',((session_id,limit) if session_id else (limit,))).fetchall()
    return [{**dict(row),'request':json.loads(row['request_json'])} for row in rows]


def submit(runtime,request_id,*,verdicts,model,source='Selected host model runtime'):
    from ..workflows.runs import canonical,digest,stamp
    from .sessions import Sessions
    actor=runtime._actor('evaluate');prepare(runtime)
    with runtime.connect() as c:row=c.execute('SELECT * FROM host_evaluation_requests WHERE id=?',(request_id,)).fetchone()
    if not row:raise ValueError('Unknown frozen host evaluation request')
    req=json.loads(row['request_json']);criteria=req['rubric']
    if not model or not isinstance(verdicts,dict) or set(verdicts)!={c['id'] for c in criteria}:
        raise ValueError('The host model must identify itself and judge every pinned criterion')
    if req.get('model') and req['model']!=model:raise ValueError('Judge model differs from the model exposed by the host')
    for cid,v in verdicts.items():
        if v.get('state') not in {'pass','fail','missing'} or not v.get('reason') or not v.get('evidence'):
            raise ValueError('Each host verdict needs its actual state, reason and artifact-specific evidence')
        score=v.get('score')
        if score is not None and (not isinstance(score,(int,float)) or isinstance(score,bool) or not 0<=score<=1):raise ValueError('Ratings must be finite values from zero to one')
    record={'request_id':request_id,'verdicts':verdicts,'model':model,'source':source,'artifact_digest':req['artifact_digest'],'review_scope':'Same-host diagnostic; independent acceptance is separate'}
    identity=digest(record)
    with runtime.connect() as c:
        old=c.execute('SELECT id FROM host_evaluation_verdicts WHERE request_id=?',(request_id,)).fetchone()
        if old:
            if old[0]!=identity:raise ValueError('Frozen verdict already exists; use an explicit reviewed revision')
            return {'id':identity,'status':'recorded'}
        c.execute('INSERT INTO host_evaluation_verdicts VALUES(?,?,?,?,?)',(identity,request_id,canonical(record),actor,stamp()))
        c.execute("UPDATE host_evaluation_requests SET status='reviewed' WHERE id=?",(request_id,))
    report={'state':'fail' if any(v['state']=='fail' for v in verdicts.values()) else 'missing' if any(v['state']=='missing' for v in verdicts.values()) else 'pass',
            'case_id':None,'rubric_version':digest(criteria),'release_digest':'host-review-v1','artifact_digest':req['artifact_digest'],
            'coverage_complete':all(v['state'] in {'pass','fail'} for v in verdicts.values()),'self_judged':True,'quality_domain':'host_model_review',
            'criteria':{cid:{**v,'evaluator_version':model,'source':source,'dimension':'behavior'} for cid,v in verdicts.items()}}
    sessions=Sessions(runtime);sessions.turn_key=row['turn_key']
    event=sessions.record(row['session_id'],kind='evaluation',request_key='host-judgment:'+request_id,payload={
        'input':{'request':req['input'],'rubric':criteria},'output':{'evaluated_output':req['output'],'verdicts':verdicts,'model':model,'review_scope':record['review_scope']},
        'report':report,'category':'host_judgment','model':model})
    return {'id':identity,'status':'recorded','event_id':event['id'],'independent_acceptance':False}


def workflow_output(runtime,run_id):
    if not enabled(runtime):return runtime.get(run_id)
    run=runtime.get(run_id)
    if run['status']=='awaiting_evaluation' and not run.get('evaluation'):run=runtime.evaluate_run(run_id)
    manifest=runtime.manifest(run['release_digest'])
    if run['output'] is not None and run.get('session_id'):
        rubric=[{'id':c['id'],'question':c['question'],**c['anchors']} for c in manifest['evaluation']['criteria'] if c['evaluator'] in {'human','model'}]
        if rubric:request_judgment(runtime,run['session_id'],'workflow:'+run_id,subject='Workflow · '+manifest['purpose'],inputs=run['inputs'],output=run['output'],rubric=rubric,target={'kind':'run','id':run_id})
    return run


def drain(runtime,*,seconds=18,limit=80,reconcile_exhausted=False,client=None):
    """One bounded host wake, batching observation transport. No resident worker."""
    import fcntl
    from pathlib import Path
    from .sessions import policy
    from .langfuse import LangfuseClient,ExportError,observation
    from ..workflows.runs import canonical,stamp
    config=policy(runtime)
    if not config.get('enabled'):return {'state':'disabled'}
    if not 1<=seconds<=25 or not 1<=limit<=100:raise ValueError('Automatic delivery must have a bounded time and record budget')
    lock_path=runtime.path.parent/'activity-export.lock'
    fd=os.open(lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'state':'another wake is delivering; evidence remains journaled'}
        client=client or LangfuseClient.from_configuration(runtime.home,config)
        client.timeout=min(client.timeout,4);client.deadline=time.monotonic()+seconds;client.begin_batch()
        from .evaluators import prepare as prepare_native,sync as sync_native
        prepare_native(runtime)
        with runtime.connect() as c:native_pending=c.execute("SELECT 1 FROM native_evaluation_definitions WHERE status!='verified' LIMIT 1").fetchone()
        native_issue=None
        if native_pending and time.monotonic()<client.deadline-10:
            native_deadline=client.deadline;client.deadline=min(native_deadline,time.monotonic()+2)
            try:sync_native(runtime,client,limit=1,pending_only=True)
            except (ExportError,ValueError,RuntimeError) as exc:
                native_issue=('Native definition setup is rate limited' if getattr(exc,'status',None)==429 else 'Native definitions pending: '+str(exc))+'; activity delivery continues separately'
            finally:client.deadline=native_deadline
        selected=[]
        for table in ('activity_exports','workflow_export_outbox'):
            with runtime.connect() as c:
                if reconcile_exhausted:c.execute("UPDATE "+table+" SET status='awaiting_readback',last_error='Explicitly reopened for readback; no blind resend' WHERE status='exhausted'")
                recent=[r[0] for r in c.execute("SELECT id FROM "+table+" WHERE status IN ('pending','awaiting_readback','sending') ORDER BY rowid DESC LIMIT ?",(limit//4,))]
                oldest=[r[0] for r in c.execute("SELECT id FROM "+table+" WHERE status IN ('pending','awaiting_readback','sending') ORDER BY rowid LIMIT ?",(limit//2-len(recent),))]
            selected.extend((table,identity) for identity in dict.fromkeys(recent+oldest))
        ready=[];new=[];results=[]
        if not client._project_verified:client.verify_project()
        for table,identity in selected:
            if time.monotonic()>=client.deadline-seconds/2:break
            with runtime.connect() as c:row=dict(c.execute('SELECT * FROM '+table+' WHERE id=?',(identity,)).fetchone())
            row['table']=table
            event=json.loads(row['payload_json'])
            if event.get('suite_experiment') or event.get('suite_definition'):
                from ..evals.harness import enrich_suite_event
                event=enrich_suite_event(runtime,client,event)
                if event is None:continue
            if event.get('experiment_id'):
                from .experiments import sync_resources,enrich_event
                sync_resources(runtime,client)
                event=enrich_event(runtime,client,event)
                if event is None:continue
            if row['status']=='pending':new.append((row,event))
            else:ready.append((row,event))
        # Include a pending trace root with its recent children. Otherwise the
        # observations can exist remotely while their trace has no root yet.
        queued={row['id'] for row,_ in new}
        for child,event in list(new):
            root=event.get('root_event_id')
            if not root or root in queued or root==child['id']:continue
            with runtime.connect() as c:parent=c.execute('SELECT * FROM '+child['table']+' WHERE id=? AND status=?',(root,'pending')).fetchone()
            if parent:
                parent=dict(parent);parent['table']=child['table'];new.insert(0,(parent,json.loads(parent['payload_json'])));queued.add(root)
        # Commit every send intent before the single OTLP batch.
        if new and time.monotonic()<client.deadline-1:
            batches=[];size=0;selected=[]
            for row,event in new:
                wire=observation(event);length=len(canonical(wire).encode())
                if size+length>3_000_000:break
                batches.extend(wire['resourceSpans']);size+=length;selected.append((row,event))
            with runtime.connect() as c:
                for row,_ in selected:c.execute("UPDATE "+row['table']+" SET status='sending',attempts=attempts+1 WHERE id=? AND status='pending'",(row['id'],))
            status='awaiting_readback';error=None
            try:
                response=client.request('POST','/api/public/otel/v1/traces',{'resourceSpans':batches})
                if response.get('partialSuccess',{}).get('rejectedSpans','0') not in (0,'0'):raise ExportError('Langfuse partially rejected the observation batch',ambiguous=True)
            except ExportError as exc:status='awaiting_readback' if exc.ambiguous else 'pending';error=str(exc)
            with runtime.connect() as c:
                for row,_ in selected:c.execute('UPDATE '+row['table']+' SET status=?,last_error=? WHERE id=?',(status,error,row['id']))
            results.extend({'id':r['id'],'status':status} for r,_ in selected)
        for row,event in ready:
            if time.monotonic()>=client.deadline-1:break
            try:
                reference=client.export(event,allow_ingest=False)
                status='verified' if reference else 'awaiting_readback';error=None
            except ExportError as exc:reference=None;status='awaiting_readback';error=str(exc)
            with runtime.connect() as c:c.execute("UPDATE "+row['table']+" SET status=?,attempts=attempts+1,last_error=?,remote_reference=COALESCE(?,remote_reference) WHERE id=?",(status,error,reference,row['id']))
            results.append({'id':row['id'],'status':status})
        return {'state':'bounded wake completed','records':results,'native_definition_issue':native_issue}
    except Exception as exc:
        return {'state':'pending','issue':str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Telemetry delivery could not complete within this wake'}
    finally:
        with runtime.connect() as c:
            counts=dict(c.execute('SELECT status,COUNT(*) FROM activity_exports GROUP BY status'))
            workflow_counts=dict(c.execute('SELECT status,COUNT(*) FROM workflow_export_outbox GROUP BY status'))
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            native_count=c.execute("SELECT COUNT(*) FROM native_evaluation_definitions WHERE status!='verified'").fetchone()[0] if 'native_evaluation_definitions' in tables else 0
        if runtime.home:
            from ..home import write_json
            rate_file=runtime.home/'.spielos/telemetry-rate-limit.json'
            cooldown=json.loads(rate_file.read_text()) if rate_file.is_file() and not rate_file.is_symlink() else {}
            write_json(runtime.home/'.spielos/telemetry-health.json',{'at':stamp(),'activity':counts,'workflow_events':workflow_counts,'native_definitions_pending':native_count,'rate_limit':cooldown,
                'last_delivery_issue':locals().get('native_issue') or locals().get('error'),'synchronized':bool(counts or workflow_counts) and (set(counts)|set(workflow_counts))<={'verified'} and native_count==0})
        os.close(fd)
