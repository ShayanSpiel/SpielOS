"""Append-only, inspectable activity for host sessions and SpielOS roles.

The host owns the model conversation. We record exposed events and supplied
context, never claim visibility into hidden reasoning or unexposed token usage.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import uuid
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS activity_sessions (
 id TEXT PRIMARY KEY, host TEXT NOT NULL, host_session TEXT NOT NULL,
 role TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(host,host_session,role));
CREATE TABLE IF NOT EXISTS activity_events (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES activity_sessions(id),
 request_key TEXT NOT NULL, kind TEXT NOT NULL, record_json TEXT NOT NULL,
 actor TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(session_id,request_key));
CREATE TABLE IF NOT EXISTS activity_exports (
 id TEXT PRIMARY KEY REFERENCES activity_events(id), payload_json TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, remote_reference TEXT);
CREATE TRIGGER IF NOT EXISTS activity_session_no_update BEFORE UPDATE ON activity_sessions
 BEGIN SELECT RAISE(ABORT,'session identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS activity_session_no_delete BEFORE DELETE ON activity_sessions
 BEGIN SELECT RAISE(ABORT,'session history is preserved'); END;
CREATE TRIGGER IF NOT EXISTS activity_event_no_update BEFORE UPDATE ON activity_events
 BEGIN SELECT RAISE(ABORT,'activity evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS activity_event_no_delete BEFORE DELETE ON activity_events
 BEGIN SELECT RAISE(ABORT,'activity history is preserved'); END;
CREATE TRIGGER IF NOT EXISTS activity_export_no_rewrite BEFORE UPDATE OF id,payload_json ON activity_exports
 BEGIN SELECT RAISE(ABORT,'export evidence is immutable'); END;
'''

KINDS = {'start', 'context', 'feedback', 'decision', 'tool', 'artifact', 'generation',
         'evaluation', 'boundary', 'message', 'end', 'link', 'rating'}
SECRET_KEY = re.compile(r'(?i)(password|secret|authorization|credential|api[_-]?key|access[_-]?token|private[_-]?key)')
SECRET_TEXT = re.compile(r'(?i)(bearer\s+\S+|(?:sk|pk)-lf-[\w-]+|sk-[\w-]{16,}|-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----|[\w-]*(?:password|secret|authorization|api[_-]?key|[_-]token)\s*[\"\x27]?\s*[:=]\s*[\"\x27]?[^\s,;]+)', re.S)


def sanitize(value):
    """Best-effort defense in depth; exports still use explicit payload selection."""
    if isinstance(value, dict):
        return {str(k): '[redacted]' if SECRET_KEY.search(str(k)) else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(x) for x in value]
    if isinstance(value, str):
        try:
            parsed=json.loads(value)
            if isinstance(parsed,(dict,list)):return json.dumps(sanitize(parsed),ensure_ascii=False)
        except (ValueError,TypeError):pass
        return re.sub(r'([?&]token=)[^&\s)]+',r'\1[redacted]',SECRET_TEXT.sub('[redacted]',value))
    return value


def policy(runtime):
    path = runtime.home/'.spielos/telemetry.json' if runtime.home else None
    if path and path.is_symlink():
        raise PermissionError('Telemetry configuration cannot be a symbolic link')
    return json.loads(path.read_text()) if path and path.is_file() else {}


def reviewed(runtime):
    return policy(runtime).get('payload_policy') == 'reviewed_evidence'


def session_label(runtime,session):
    company=runtime.home.name if runtime.home else 'Synthetic company'
    return session['host'].title()+' · '+company+' · '+session['created_at'][:10]+' · '+session['host_session']


class Sessions:
    def __init__(self, runtime):
        self.runtime = runtime
        if not runtime.readonly:
            with runtime.connect() as connection:
                connection.executescript(SCHEMA)

    def start(self, *, host, host_session, role='director', request_key='start', coverage=None, brief=False):
        from ..workflows.runs import digest, stamp
        actor = self.runtime._actor('build' if role in {'builder', 'system_improvement'} else 'evaluate' if role == 'evaluator' else 'run')
        if host not in {'codex', 'claude', 'opencode', 'python', 'manual'} or not host_session:
            raise ValueError('Session needs an explicit host and host-session identity')
        if role not in {'director', 'builder', 'system_improvement', 'workflow', 'agent', 'evaluator'}:
            raise ValueError('Choose an explicit SpielOS role; the host is a separate identity')
        identity = digest({'company': str(self.runtime.path.resolve()), 'host': host, 'session': host_session, 'role': role})[:32]
        with self.runtime.connect() as connection:
            connection.execute('INSERT OR IGNORE INTO activity_sessions VALUES(?,?,?,?,?,?)',
                               (identity, host, host_session, role, actor, stamp()))
            original=connection.execute('SELECT actor FROM activity_sessions WHERE id=?',(identity,)).fetchone()
            if original['actor']!=actor:raise PermissionError('The host session belongs to another authenticated executor')
            resumed=coverage is None and connection.execute('SELECT id FROM activity_events WHERE session_id=? AND request_key=?',(identity,request_key)).fetchone() is not None
        if resumed:return {'id':identity,'host':host,'role':role} if brief else self.show(identity)
        self.record(identity, kind='start', request_key=request_key, payload={
            'host': host, 'role': role, 'coverage': coverage or {
                'source': 'explicit instrumentation', 'model_context': 'only supplied snapshots',
                'tools': 'only reported events', 'tokens': 'unknown unless reported by provider',
                'reasoning': 'not collected'}})
        return {'id':identity,'host':host,'role':role} if brief else self.show(identity)

    def record(self, session_id, *, kind, request_key, payload, target=None, caused_by=None):
        from ..workflows.runs import canonical, digest, stamp
        # Builders and evaluators have different roles from production executors.
        with self.runtime.connect() as connection:
            identity_row = connection.execute('SELECT role FROM activity_sessions WHERE id=?', (session_id,)).fetchone()
        action = 'evaluate' if kind in {'evaluation', 'rating'} else 'build' if identity_row and identity_row[0] in {'builder', 'system_improvement'} else 'evaluate' if identity_row and identity_row[0] == 'evaluator' else 'run'
        actor = self.runtime._actor(action)
        if kind not in KINDS or not isinstance(request_key, str) or not request_key or not isinstance(payload, dict):
            raise ValueError('Activity needs a supported kind, stable request key and structured evidence')
        if kind == 'feedback':
            if payload.get('scope') not in {'run', 'project', 'owner', 'workflow', 'evaluation', 'build'} or not all(payload.get(k) for k in ('message', 'interpretation', 'effect')) or not target:
                raise ValueError('Feedback needs its message, interpretation, scope, effect and exact target')
            if payload['scope']=='run' and target.get('kind')!='run':
                raise ValueError('Order feedback must target an actual run')
            if payload['scope'] in {'build','workflow'} and target.get('kind')!='improvement':
                raise ValueError('Reusable changes must target a bounded Improvement')
        if kind == 'boundary' and not all(payload.get(k) for k in ('reason', 'before', 'after')):
            raise ValueError('Boundary changes need before/after state and a reason')
        if kind == 'generation':
            from ..workflows.runs import WorkflowRuntime
            WorkflowRuntime._usage(payload.get('usage', {'status': 'unknown'}))
            if not payload.get('source'):
                raise ValueError('Generation evidence must identify its source')
        if kind == 'rating':
            value=payload.get('value')
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not 0<=value<=1 or not all(payload.get(k) for k in ('criterion','reason')) or not target or target.get('kind')!='event':
                raise ValueError('Ratings require a criterion, finite 0–1 value, reason and exact target')
        with self.runtime.connect() as connection:
            session = connection.execute('SELECT * FROM activity_sessions WHERE id=?', (session_id,)).fetchone()
            if session is None:
                raise KeyError('Unknown session')
            if self.runtime.authority and actor != session['actor'] and kind not in {'evaluation', 'rating'}:
                raise PermissionError('Only the session executor can append its activity')
            if caused_by and not connection.execute('SELECT id FROM activity_events WHERE id=?', (caused_by,)).fetchone():
                raise ValueError('Causal activity reference does not exist')
            if target:
                table = {'run': 'workflow_invocations', 'improvement': 'workflow_improvements', 'session': 'activity_sessions', 'event': 'activity_events'}.get(target.get('kind'))
                if not table or not connection.execute('SELECT id FROM '+table+' WHERE id=?', (target.get('id'),)).fetchone():
                    raise ValueError('Activity target must name an existing record')
            clean = sanitize(payload)
            if len(canonical(clean).encode()) > 500_000:
                raise ValueError('Activity exceeds the evidence envelope; split into attributable artifacts')
            record = {'kind': kind, 'payload': clean, 'target': target, 'caused_by': caused_by}
            turn_key=getattr(self,'turn_key',None)
            if turn_key:record['turn_key']=turn_key
            existing = connection.execute('SELECT * FROM activity_events WHERE session_id=? AND request_key=?', (session_id, request_key)).fetchone()
            if existing:
                if existing['record_json'] != canonical(record) or existing['actor'] != actor:
                    raise ValueError('Activity request identity was reused for different evidence')
                return dict(existing)
            identity = digest({'session': session_id, 'request': request_key, 'record': record})
            now = stamp()
            first = connection.execute("SELECT id FROM activity_events WHERE session_id=? AND COALESCE(json_extract(record_json,'$.turn_key'),'')=? ORDER BY rowid LIMIT 1", (session_id,turn_key or '')).fetchone()
            root = first[0] if first else identity
            title=None
            if turn_key:
                title_row=connection.execute('SELECT title FROM activity_turns WHERE session_id=? AND turn_key=?',(session_id,turn_key)).fetchone()
                title=title_row[0] if title_row else None
            labels={'start':'Session opened','context':'Supplied context','feedback':'Owner feedback','decision':'Director decision','tool':clean.get('tool_name','Tool call'),
                    'artifact':'Artifact · '+str(clean.get('purpose','Produced file'))[:90],'generation':'Model generation','evaluation':'Codex quality review' if clean.get('category')=='host_judgment' else 'Turn evidence evaluation',
                    'boundary':'Scope or lifecycle boundary','message':'Owner request' if clean.get('speaker')=='owner' else 'Director answer','end':'Turn ended','link':'Related work','rating':'Human rating'}
            event = {'id': identity, 'run_id': session_id, 'session_id': session_id, 'root_event_id': root,
                     'host_session_id': session_label(self.runtime,session),
                     'trace_run_id': session_id+':turn:'+turn_key if turn_key else session_id, 'release_digest': 'activity-v2', 'status': kind,
                     'trace_name':session['role'].replace('_',' ').title()+' · '+(title or 'Session activity'),
                     'name': labels[kind], 'category':clean.get('category','activity'),
                     'company_id':self.runtime.authority.company_id if self.runtime.authority else 'synthetic',
                     'runtime_model':clean.get('model'),
                     'observation_type': 'generation' if kind == 'generation' else 'tool' if kind == 'tool' else 'evaluator' if kind == 'evaluation' else 'span',
                     'at': now, 'started_at': now, 'workflow_version': '2', 'input_digest': digest(clean),
                     'output_digest': None, 'usage': clean.get('usage', {'status': 'unknown'}),
                     'context_export': 'reviewed_evidence' if reviewed(self.runtime) else 'digests_only'}
            if reviewed(self.runtime):
                event['evidence'] = {'input': {'host': session['host'], 'role': session['role'], 'kind': kind, 'target': target, 'caused_by': caused_by}, 'output': clean}
                if clean.get('suite_definition'):event['suite_definition']=clean['suite_definition']
                if kind == 'evaluation':
                    event['evaluation'] = clean.get('report')
                    if clean.get('experiment_ref'):
                        event['suite_experiment'] = clean['experiment_ref']
                    event['evidence'] = {'input': clean.get('input'), 'output': clean.get('output'), 'evaluation_contract': clean.get('report')}
                if kind == 'rating':
                    event['rating'] = {**clean,'target':target}
                    rated=connection.execute('SELECT payload_json FROM activity_exports WHERE id=?',(target['id'],)).fetchone()
                    if not rated:raise ValueError('Rating target has no observable activity')
                    event['rating_subject']=json.loads(rated[0])
                if kind == 'generation':
                    event['model'] = clean.get('model')
            connection.execute('INSERT INTO activity_events VALUES(?,?,?,?,?,?,?)', (identity, session_id, request_key, kind, canonical(record), actor, now))
            connection.execute("INSERT INTO activity_exports(id,payload_json,status) VALUES(?,?,'pending')", (identity, canonical(event)))
        return {'id': identity, 'session_id': session_id, **record}

    def context(self, session_id, *, documents, request_key, reason, target=None):
        from ..workflows.runs import digest
        if not isinstance(documents, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in documents.items()) or not reason:
            raise ValueError('Context requires named actual text and a change reason')
        with self.runtime.connect() as c:
            row=c.execute("SELECT record_json FROM activity_events WHERE session_id=? AND kind='context' ORDER BY rowid DESC LIMIT 1",(session_id,)).fetchone()
        previous=json.loads(row[0])['payload']['documents'] if row else {}
        snapshot = {name: {'text': sanitize(text), 'sha256': hashlib.sha256(text.encode()).hexdigest()} for name, text in sorted(documents.items())}
        changed = [name for name, value in snapshot.items() if previous.get(name, {}).get('sha256') != value['sha256']]
        return self.record(session_id, kind='context', request_key=request_key, target=target, payload={
            'reason': reason, 'documents': snapshot, 'added_or_changed': changed, 'removed': sorted(set(previous)-set(snapshot)),
            'snapshot_digest': digest(snapshot), 'coverage': 'SpielOS-supplied context; host system and hidden context are not inferred'})

    def artifact(self, session_id, *, path, purpose, request_key, target=None, caused_by=None):
        if not self.runtime.home or not purpose:
            raise ValueError('Artifact registration needs the selected home and its purpose')
        home = self.runtime.home.resolve()
        source = Path(path)
        source = source if source.is_absolute() else home/source
        if source.is_symlink() or not source.resolve().is_relative_to(home) or set(source.resolve().relative_to(home).parts) & {'credentials', 'security', '.env'} or source.name.startswith('.env'):
            raise ValueError('Register a non-secret artifact inside the selected home')
        source=source.resolve()
        raw = source.read_bytes()
        return self.record(session_id, kind='artifact', request_key=request_key, target=target, caused_by=caused_by, payload={
            'path': source.relative_to(home).as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'media_type': mimetypes.guess_type(source.name)[0] or 'application/octet-stream',
            'purpose': purpose, 'availability': 'local company artifact; path is provenance, not a quality judgment'})

    def show(self, session_id):
        self.runtime._actor('read')
        with self.runtime.connect() as connection:
            row = connection.execute('SELECT * FROM activity_sessions WHERE id=?', (session_id,)).fetchone()
            if row is None:
                raise KeyError('Unknown session')
            events = [{**dict(e), 'record': json.loads(e['record_json'])} for e in connection.execute('SELECT * FROM activity_events WHERE session_id=? ORDER BY rowid', (session_id,))]
            exports = [dict(e) for e in connection.execute('SELECT x.id,x.status,x.last_error,x.remote_reference FROM activity_exports x JOIN activity_events e ON e.id=x.id WHERE e.session_id=?', (session_id,))]
        return {**dict(row), 'events': events, 'telemetry': exports,
                'observable': bool(exports) and all(e['status'] == 'verified' for e in exports)}

    def import_ratings(self,client,session_id,*,event_id):
        """Preserve native human annotations as evidence, never as action approval."""
        from urllib.parse import urlencode
        from .langfuse import identities
        from ..workflows.runs import digest
        self.runtime._actor('evaluate')
        config=policy(self.runtime)
        if client.project_id!=config.get('project_id') or client.base_url!=config.get('base_url'):
            raise PermissionError('Rating source differs from the approved Langfuse project')
        if not client._project_verified:client.verify_project()
        with self.runtime.connect() as connection:
            row=connection.execute('SELECT x.payload_json FROM activity_exports x JOIN activity_events e ON e.id=x.id WHERE x.id=? AND e.session_id=?',(event_id,session_id)).fetchone()
        if not row:raise ValueError('Choose an actual observation from this session')
        trace,span=identities(json.loads(row[0]));cursor=None;imported=[]
        for _ in range(10):
            query={'traceId':trace,'fields':'subject,details','limit':100}
            if cursor:query['cursor']=cursor
            response=client.request('GET','/api/public/v3/scores?'+urlencode(query))
            for score in response.get('data',[]):
                subject=score.get('subject',{})
                if score.get('source')!='ANNOTATION' or subject.get('kind')!='observation' or subject.get('id')!=span:continue
                imported.append(self.record(session_id,kind='evaluation',request_key='langfuse-rating:'+digest(score),target={'kind':'event','id':event_id},payload={
                    'source':'Langfuse human annotation','score_id':score['id'],'criterion':score['name'],'value':score['value'],
                    'reason':score.get('comment'),'author_digest':digest(str(score.get('authorUserId'))),'authority':'review evidence only; no release or external-action approval'}))
            cursor=(response.get('meta') or {}).get('cursor')
            if not cursor:break
        else:raise ValueError('Rating import exceeded its bounded pagination budget')
        return {'imported':len(imported),'events':imported}

    def export(self, client, *, limit=50, max_attempts=20):
        from .langfuse import ExportError
        self.runtime._actor('read')
        config = policy(self.runtime)
        if config and (not config.get('enabled') or client.project_id != config.get('project_id') or client.base_url != config.get('base_url')):
            raise PermissionError('Activity export destination differs from the approved company project')
        if not 1 <= limit <= 100 or not 1 <= max_attempts <= 100:
            raise ValueError('Export budgets must be between 1 and 100')
        client.begin_batch()
        with self.runtime.connect() as connection:
            rows = connection.execute("SELECT id FROM activity_exports WHERE status!='verified' AND attempts<? ORDER BY rowid LIMIT ?", (max_attempts, limit)).fetchall()
        result = []
        for selected in rows:
            with self.runtime.connect() as connection:
                payload = json.loads(connection.execute('SELECT payload_json FROM activity_exports WHERE id=?', (selected[0],)).fetchone()[0])
            from ..evals.harness import enrich_suite_event
            payload = enrich_suite_event(self.runtime, client, payload)
            if payload is None:
                result.append({'id': selected[0], 'status': 'awaiting_experiment_setup'})
                continue
            with self.runtime.connect() as connection:
                connection.execute('BEGIN IMMEDIATE')
                row = connection.execute('SELECT * FROM activity_exports WHERE id=?', (selected[0],)).fetchone()
                if row['status'] == 'verified' or row['attempts'] >= max_attempts:
                    continue
                allow = row['status'] == 'pending'
                connection.execute("UPDATE activity_exports SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            reference, error = None, None
            try:
                reference = client.export(payload, allow_ingest=allow)
                status = 'verified' if reference else 'awaiting_readback'
            except ExportError as exc:
                status, error = ('awaiting_readback' if exc.ambiguous or not allow else 'pending'), str(exc)
            except Exception:
                status, error = 'awaiting_readback', 'Activity export failed; inspect the scoped connection'
            if status != 'verified' and row['attempts']+1 >= max_attempts:
                status = 'exhausted'
            with self.runtime.connect() as connection:
                connection.execute("UPDATE activity_exports SET status=?,last_error=?,remote_reference=? WHERE id=? AND status!='verified'", (status, error, reference, row['id']))
            result.append({'id': row['id'], 'status': status, 'reference': reference, 'error': error})
        with self.runtime.connect() as connection:
            tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            experiments=[r[0] for r in connection.execute('SELECT id FROM evaluation_experiments WHERE id NOT IN (SELECT experiment_id FROM evaluation_confirmations) LIMIT 20')] if 'evaluation_confirmations' in tables else []
        from ..evals.harness import EvaluationHarness
        for identity in experiments:
            EvaluationHarness(self.runtime).verify(client,identity)
        return result



def completion_end(connection,session_id,turn_key):
    """First Stop is the completion boundary; a later close is fallback evidence only."""
    row=connection.execute("SELECT record_json FROM activity_events WHERE session_id=? AND kind='end' AND json_extract(record_json,'$.turn_key')=? ORDER BY CASE WHEN json_extract(record_json,'$.payload.event')='Stop' THEN 0 ELSE 1 END,rowid ASC LIMIT 1",(session_id,turn_key)).fetchone()
    return json.loads(row[0])['payload'] if row else None


def capture_hook(home, request, *, host, context=None, documents=None):
    """Explicit installed hook. No transcript discovery or host trust bypass."""
    from ..mcp import CompanySession
    from ..workflows.runs import digest
    config_path = Path(home)/'.spielos/telemetry.json'
    if not config_path.is_file() or json.loads(config_path.read_text()).get('payload_policy') != 'reviewed_evidence':
        return None
    host_id = request.get('session_id') or request.get('sessionId')
    if not host_id:
        raise ValueError('Host did not expose a session identity; activity coverage is incomplete')
    selection = CompanySession()
    selected = selection.select(str(home))
    runtime = selection.runtime(selected['company_id'])
    sessions = Sessions(runtime)
    session = sessions.start(host=host, host_session=host_id,brief=True)
    event = request.get('hook_event_name') or request.get('hookEventName') or 'unknown'
    from .automatic import enabled,turn,evaluate_turn
    automatic=enabled(runtime)
    if automatic:turn(sessions,session['id'],request)
    key = digest({'event': event, 'turn': request.get('turn_id'), 'tool': request.get('tool_use_id'), 'request': sanitize(request), 'context': context})
    if host=='codex' and event in {'UserPromptSubmit','PostToolUse','Stop','SessionEnd'}:
        try:
            from .usage import ingest
            ingest(runtime,session['id'],path=request.get('transcript_path'),publish=True)
        except (ValueError,PermissionError,OSError):
            pass # Unsupported/mismatched logs remain unmeasured; never substitute another chat.
    if context is not None:
        sessions.context(session['id'], documents=documents or {'injected-company-context': context}, reason=event, request_key=key+':context')
    prompt = request.get('prompt') or request.get('user_prompt')
    if prompt:
        sessions.record(session['id'], kind='message', request_key=key+':message', payload={'speaker': 'owner', 'text': prompt, 'interpretation': 'Awaiting Director classification; a prompt does not silently amend a run'})
    if event in {'PostToolUse', 'PostToolUseFailure', 'PreToolUse'}:
        tool_input=json.dumps(request.get('tool_input',{}),ensure_ascii=False)
        private=any(part in tool_input for part in ('.env','/credentials/','/security/','authority.key','principals.json'))
        payload={k:request[k] for k in ('tool_name','tool_input','tool_response','error','tool_use_id') if k in request}
        if private:
            payload={k:request[k] for k in ('tool_name','tool_use_id') if k in request}
            payload.update({'input_digest':digest(tool_input),'payload':'Private credential/authority operation; arguments and result excluded'})
        sessions.record(session['id'], kind='tool', request_key=key, payload=payload)
    if event in {'Stop', 'SessionEnd'} and not request.get('stop_hook_active'):
        if request.get('last_assistant_message'):
            sessions.record(session['id'],kind='message',request_key=key+':answer',payload={
                'speaker':'assistant','output':request['last_assistant_message'],'source':'host-exposed final message','model':request.get('model')})
        usage=request.get('usage') or request.get('token_usage') or {'status':'unknown'}
        if not isinstance(usage,dict):usage={'status':'unknown'}
        if usage.get('status') in {'actual','estimated'}:
            from ..workflows.runs import WorkflowRuntime
            WorkflowRuntime._usage(usage)
        else:usage={'status':'unknown'}
        usage={**usage,'scope':'turn_total'}
        elapsed=None
        from datetime import datetime,timezone
        if automatic:
            with runtime.connect() as c:
                first=c.execute('SELECT created_at FROM activity_turns WHERE session_id=? AND turn_key=?',(session['id'],sessions.turn_key)).fetchone()
                completed=completion_end(c,session['id'],sessions.turn_key)
            if completed and completed.get('event')=='Stop':elapsed=completed.get('elapsed_seconds')
            elif first:elapsed=max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(first[0])).total_seconds())
        end_payload={'source':'host hook','event':event,'usage':usage,'elapsed_seconds':elapsed,'time_basis':'Observed host turn wall time including tool and waiting; not active compute','completion':'Host turn ended; quality and observability require separate evidence'}
        with runtime.connect() as c:existing_end=c.execute('SELECT record_json FROM activity_events WHERE session_id=? AND request_key=?',(session['id'],key)).fetchone()
        if existing_end:end_payload=json.loads(existing_end[0])['payload']
        sessions.record(session['id'],kind='end',request_key=key,payload=end_payload)
        if automatic:evaluate_turn(sessions,session['id'],sessions.turn_key,model=request.get('model'))
    if event=='Interrupt':
        sessions.record(session['id'],kind='boundary',request_key=key,payload={
            'reason':'Owner interrupted the host turn','before':'Host turn active','after':'Host turn interrupted; workflow cancellation or revision must be recorded separately'})
    return {'session_id': session['id'], 'host': host, 'role': 'director'}


def dispatch_activity(runtime, action, payload, *, session_id=None):
    sessions=Sessions(runtime)
    values=dict(payload)
    identity=values.pop('session_id',None) or session_id
    if action=='start':return sessions.start(**values)
    if action=='show':return sessions.show(identity)
    if action=='import-usage':
        from .usage import ingest
        return ingest(runtime,identity,path=values.get('path'),publish=True)
    if action in {'export','import-ratings'}:
        from .langfuse import LangfuseClient
        config=policy(runtime)
        if not config.get('enabled'):raise ValueError('Configure the exact Langfuse project first')
        client=LangfuseClient.from_configuration(runtime.home,config)
        return {'events':sessions.export(client,**values)} if action=='export' else sessions.import_ratings(client,identity,**values)
    if action not in {'record','context','artifact'}:raise ValueError('Unknown activity operation')
    return getattr(sessions,action)(identity,**values)
