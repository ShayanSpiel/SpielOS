"""Read-only company reporting, explicit custom UI and an authenticated loopback server."""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os, secrets, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, unquote,quote
from .platform import protect_private,is_link

VERSION='spielos-report/1'

def _now():return datetime.now(timezone.utc).isoformat()
def _json(path,default=None):
    if not path.is_file() or path.is_symlink():return default
    try:return json.loads(path.read_text())
    except (ValueError,OSError):return default

def configuration(home):
    home=Path(home).resolve();data=_json(home/'.spielos/report.json',{})
    custom=data.get('ui_root')
    if custom:
        p=Path(custom)
        if p.is_absolute() or '..' in p.parts or p.parts[:2]!=('.spielos','artifacts'):
            raise ValueError('Custom report UI must be explicitly contained in company artifacts')
        if not (home/p/'index.html').is_file() or any(is_link(home/Path(*p.parts[:i])) for i in range(1,len(p.parts)+1)):
            raise ValueError('Custom report UI is missing or symbolic')
        custom=p.as_posix()
    return {'schema':1,'ui_root':custom,'custom_name':data.get('custom_name'),'port':data.get('port',8775)}

def permitted_file(home,path):
    """No state/credentials, traversal or symlink escapes, even within an allowed root."""
    home=Path(home).resolve();name=unquote(str(path)).replace('\\','/').lstrip('/');p=Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or any(':' in part for part in p.parts):raise PermissionError('File is outside the report scope')
    if any(x.startswith('.') and x!='.spielos' or x.lower() in {'credentials','security','connections','private-inputs','node_modules'} for x in p.parts):
        # Only the pinned icon font CSS is a useful exception, never a general dependency server.
        if not name.startswith('company/departments/videography/remotion/node_modules/boxicons/'):
            raise PermissionError('Private or executable dependency files are excluded')
    allowed=name=='company/profile.md' or name.startswith(('company/strategy/','company/brand/','company/workflows/','company/skills/','company/agents/installed/','.spielos/artifacts/','company/departments/'))
    if not allowed:raise PermissionError('File is outside the report scope')
    for i in range(1,len(p.parts)+1):
        if is_link(home/Path(*p.parts[:i])):raise PermissionError('Symbolic files are not served')
    f=home/p
    if not f.resolve().is_relative_to(home) or not f.is_file():raise FileNotFoundError('Report file not found')
    return f

def _document(home,path):
    from .observability.sessions import sanitize
    f=permitted_file(home,path);raw=f.read_bytes()
    if len(raw)>1024*1024:raise ValueError('Document preview exceeds one megabyte')
    return {'path':f.relative_to(home).as_posix(),'name':f.name,'sha256':hashlib.sha256(raw).hexdigest(),'modified_at':datetime.fromtimestamp(f.stat().st_mtime,timezone.utc).isoformat(),'text':sanitize(raw.decode('utf-8'))}

def usage_summary(records):
    """Only exposed amounts, never zero-fill unknown components or mix currencies."""
    result={'records':len(records),'actual':0,'estimated':0,'unknown':0,'input_tokens':None,'output_tokens':None,'costs':{},'complete':True}
    for row in records:
        u=row.get('usage',row);state=u.get('status','unknown');result[state if state in ('actual','estimated') else 'unknown']+=1
        if state!='actual':result['complete']=False
        if state=='unknown':continue
        for field in ('input_tokens','output_tokens'):
            value=u.get(field)
            if state=='actual' and isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0:result[field]=(result[field] or 0)+value
        if isinstance(u.get('cost'),(int,float)) and u.get('currency'):
            costs=result['costs'].setdefault(u['currency'],{'actual':None,'estimated':None});costs[state]=(costs[state] or 0)+u['cost']
    if not records:result['complete']=False
    result['meaning']='Reported subtotals only. Missing usage and unmeasured time are not zero.'
    return result

def snapshot(home):
    from .mcp import CompanySession
    from .observability.sessions import sanitize
    from .observability.langfuse import identities
    home=Path(home).resolve();selected=CompanySession();choice=selected.select(str(home))
    database=home/'.spielos/state/workflows.sqlite'
    runtime=selected.runtime(choice['company_id'],readonly=True) if database.is_file() else None
    result={'schema':VERSION,'generated_at':_now(),'company':{'name':home.name,'home':str(home)},'extension':configuration(home),'totals':{},'workflows':[],'runs':[],'improvements':[],'memory':{'records':[],'categories':{},'scopes':{}},'context':[],'activity':[],'evaluations':[],'telemetry':{},'usage':{},'documents':[],'limitations':['Host usage is available only when actually exposed.','A same-host diagnostic does not grant independent acceptance.','Historical file existence does not establish a workflow Run.']}
    definition_paths=sorted((home/'company/workflows').glob('*/workflow.json'))
    agents=[{'id':f.stem,'path':f.relative_to(home).as_posix()} for f in sorted((home/'company/agents/installed').glob('*.json')) if not f.is_symlink()]
    skills=[{'id':f.parent.name,'path':f.relative_to(home).as_posix()} for f in sorted((home/'company/skills').glob('*/SKILL.md')) if not f.is_symlink()]
    result['agents']=agents;result['skills']=skills
    for f in definition_paths:
        try:
            doc=_document(home,f.relative_to(home));m=json.loads(doc['text']);result['workflows'].append({'id':m['id'],'purpose':m.get('purpose'),'version':m.get('version'),'path':doc['path'],'readiness':'draft','runs':0,'evaluation':m.get('evaluation'),'memory_count':0})
        except (ValueError,KeyError,OSError,PermissionError):continue
    records=[];workflow_usage=[];host_usage=[];groups={};tables=set()
    if runtime is not None:
        with runtime.connect() as c:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'workflow_invocations' in tables:
                result['run_counts']={r[0]:r[1] for r in c.execute('SELECT kind,COUNT(*) FROM workflow_invocations GROUP BY kind')}
                for row in c.execute('SELECT i.id,i.kind,i.status,i.created_at,i.updated_at,i.release_digest,i.session_id,i.evaluation_json,i.memory_snapshot_json,r.workflow_id,r.version,r.manifest_json FROM workflow_invocations i JOIN workflow_releases r ON r.digest=i.release_digest ORDER BY i.created_at DESC LIMIT 300'):
                    a=dict(row);manifest=json.loads(a.pop('manifest_json'));a['agent_id']=manifest.get('resolved_agent',{}).get('id');a['pinned_context']=[{'name':n,'sha256':v.get('sha256'),'source':v.get('source')} for n,v in manifest.get('resolved_context',{}).items()];a['selected_memory']=json.loads(a.pop('memory_snapshot_json') or '[]');a['context_basis']='Pinned run context, not proof the host read it';a['evaluation']=json.loads(a.pop('evaluation_json') or 'null');a['elapsed_seconds']=max(0,(datetime.fromisoformat(a['updated_at'])-datetime.fromisoformat(a['created_at'])).total_seconds());a['time_basis']='Observed run elapsed interval; includes waiting, not active compute';result['runs'].append(a)
                for w in result['workflows']:
                    w['runs']=c.execute("SELECT COUNT(*) FROM workflow_invocations i JOIN workflow_releases r ON r.digest=i.release_digest WHERE r.workflow_id=? AND i.kind='production'",(w['id'],)).fetchone()[0]
                    w['candidate_runs']=c.execute("SELECT COUNT(*) FROM workflow_invocations i JOIN workflow_releases r ON r.digest=i.release_digest WHERE r.workflow_id=? AND i.kind='candidate'",(w['id'],)).fetchone()[0]
                    if c.execute('SELECT 1 FROM workflow_releases r JOIN workflow_release_acceptance a ON a.digest=r.digest WHERE r.workflow_id=?',(w['id'],)).fetchone():w['readiness']='accepted release available'
            if 'workflow_improvements' in tables:
                for row in c.execute('SELECT id,stage,brief_json,candidate_digest,created_at,updated_at FROM workflow_improvements ORDER BY created_at DESC LIMIT 500'):
                    a=dict(row);brief=json.loads(a.pop('brief_json'));a['name']=brief.get('name');a['need']=brief.get('business_need');result['improvements'].append(a)
            if 'workflow_usage_events' in tables:
                for row in c.execute('SELECT u.usage_json,r.workflow_id,u.run_id,u.stage,u.created_at FROM workflow_usage_events u JOIN workflow_invocations i ON i.id=u.run_id JOIN workflow_releases r ON r.digest=i.release_digest'):
                    value=json.loads(row[0]);workflow_usage.append(value);groups.setdefault(row[1],[]).append(value);result.setdefault('workflow_usage',[]).append({'run_id':row[2],'workflow_id':row[1],'stage':row[3],'created_at':row[4],'usage':value})
            if 'workflow_memories' in tables:
                meta={r[0]:json.loads(r[1]) for r in c.execute('SELECT memory_id,metadata_json FROM workflow_memory_classifications')} if 'workflow_memory_classifications' in tables else {}
                result['memory']['total']=c.execute('SELECT COUNT(*) FROM workflow_memories').fetchone()[0]
                for row in c.execute('SELECT id,scope,workflow_id,claim,evidence_json,source,created_at,status FROM workflow_memories ORDER BY created_at DESC LIMIT 2000'):
                    a=dict(row);a['evidence']=json.loads(a.pop('evidence_json'));a['classification']=meta.get(a['id'],{'category':a['scope'],'topics':[]});records.append(a)
                result['memory']['records']=records
                for a in records:
                    category=a['classification'].get('category',a['scope']);result['memory']['categories'][category]=result['memory']['categories'].get(category,0)+1;result['memory']['scopes'][a['scope']]=result['memory']['scopes'].get(a['scope'],0)+1
                for w in result['workflows']:w['memory_count']=sum(a['workflow_id']==w['id'] and a['status']=='active' for a in records)
                result['memory']['truncated']=result['memory']['total']>len(records)
            if 'activity_events' in tables:
                result['activity_counts']={r[0]:r[1] for r in c.execute('SELECT kind,COUNT(*) FROM activity_events GROUP BY kind')}
                result['unique_completions']=c.execute("SELECT COUNT(*) FROM (SELECT session_id,COALESCE(json_extract(record_json,'$.turn_key'),id) FROM activity_events WHERE kind='end' GROUP BY session_id,COALESCE(json_extract(record_json,'$.turn_key'),id))").fetchone()[0]
                for row in c.execute("SELECT id,session_id,record_json,created_at FROM activity_events WHERE kind IN ('end','generation') ORDER BY rowid DESC LIMIT 2000"):
                    a=dict(row);payload=json.loads(a.pop('record_json'));data=payload['payload'];turn=payload.get('turn_key');u=data.get('usage',{'status':'unknown'});a.update({'turn_key':turn,'usage':u,'elapsed_seconds':data.get('elapsed_seconds'),'time_basis':data.get('time_basis'),'target':payload.get('target')})
                    if payload.get('kind')=='end' and turn:
                        from .observability.sessions import completion_end
                        completed=completion_end(c,a['session_id'],turn) or data
                        a['elapsed_seconds']=completed.get('elapsed_seconds');a['usage']=completed.get('usage',u)
                    host_usage.append(a['usage']);a['event_kind']=payload.get('kind');result['activity'].append(a)
                # Aggregates use completion totals when present; a generation is not added again to its turn total.
                end_turns={a['session_id']+':'+str(a['turn_key']) for a in result['activity'] if a['usage'].get('scope')=='turn_total'}
                totals=[];seen_totals=set()
                for a in result['activity']:
                    turn_id=a['session_id']+':'+str(a['turn_key'] or a['id'])
                    if a['usage'].get('scope')=='turn_total':
                        if turn_id in seen_totals:continue
                        seen_totals.add(turn_id);totals.append(a['usage'])
                    elif turn_id not in end_turns:totals.append(a['usage'])
                result['usage']['chat']=usage_summary(totals)
                for row in c.execute("SELECT id,session_id,record_json,created_at FROM activity_events WHERE kind='context' ORDER BY rowid DESC LIMIT 12"):
                    a=dict(row);data=json.loads(a.pop('record_json'))['payload'];a['reason']=data.get('reason');a['documents']=[{'name':n,'sha256':v.get('sha256'),'preview':v.get('text','')[:1200]} for n,v in data.get('documents',{}).items()];a['changed']=data.get('added_or_changed',[]);result['context'].append(a)
            if 'host_evaluation_verdicts' in tables:
                for row in c.execute('SELECT request_id,verdict_json,created_at FROM host_evaluation_verdicts ORDER BY rowid DESC LIMIT 20'):
                    a=dict(row);a['verdict']=json.loads(a.pop('verdict_json'));a['independent_acceptance']=False;result['evaluations'].append(a)
            result['evaluation_requests']=[]
            if 'host_evaluation_requests' in tables:
                for row in c.execute('SELECT id,session_id,subject,status,request_json,created_at FROM host_evaluation_requests ORDER BY rowid DESC LIMIT 30'):
                    request=json.loads(row['request_json'])
                    result['evaluation_requests'].append({'id':row['id'],'session_id':row['session_id'],'target':request.get('target'),'subject':row['subject'],'status':row['status'],
                        'created_at':row['created_at'],'criteria':request.get('rubric',[]),
                        'artifact_digest':request.get('artifact_digest'),'independent_acceptance':False})
            cfg=_json(home/'.spielos/telemetry.json',{})
            project=cfg['base_url']+'/project/'+str(cfg['project_id']) if cfg.get('enabled') is True and cfg.get('base_url') and cfg.get('project_id') else None
            telemetry={'enabled':cfg.get('enabled',False),'project_url':project,'activity':{},'workflow':{},'recent':[]}
            for table,label in [('activity_exports','activity'),('workflow_export_outbox','workflow')]:
                if table not in tables:continue
                telemetry[label]={r[0]:r[1] for r in c.execute('SELECT status,COUNT(*) FROM '+table+' GROUP BY status')}
                for row in c.execute('SELECT id,payload_json,status,last_error,remote_reference FROM '+table+' ORDER BY rowid DESC LIMIT 12'):
                    a=dict(row);event=json.loads(a.pop('payload_json'));trace,span=identities(event);a.update({'name':event.get('trace_name',event.get('name')),'at':event.get('at'),'trace_url':project+'/traces/'+trace if project else None,'observation_id':span,'kind':label});telemetry['recent'].append(a)
            telemetry['native_definitions']=[dict(r) for r in c.execute('SELECT key,status,last_error,evaluator_id,rule_id FROM native_evaluation_definitions ORDER BY key')] if 'native_evaluation_definitions' in tables else []
            telemetry['native_pending']=sum(r['status']!='verified' for r in telemetry['native_definitions'])
            telemetry['pending']=sum(n for label in ['activity','workflow'] for state,n in telemetry[label].items() if state!='verified');telemetry['verified']=sum(telemetry[label].get('verified',0) for label in ['activity','workflow']);telemetry['synchronized']=telemetry['pending']==0 and telemetry['native_pending']==0;result['telemetry']=telemetry
    for agent in result['agents']:
        agent['workflow_ids']=sorted({a['workflow_id'] for a in result['runs'] if a.get('agent_id')==agent['id']});agent['runs']=sum(a.get('agent_id')==agent['id'] for a in result['runs']);agent['memory_count']=sum(m['workflow_id'] in agent['workflow_ids'] for m in records)
    result['usage']['workflow']=usage_summary(workflow_usage);result['usage']['per_workflow']={k:usage_summary(v) for k,v in groups.items()};elapsed_by_turn={}
    for a in result['activity']:
        if a['event_kind']=='end' and a.get('elapsed_seconds') is not None:elapsed_by_turn.setdefault(a['session_id']+':'+str(a['turn_key'] or a['id']),a['elapsed_seconds'])
    measured=list(elapsed_by_turn.values())
    result['usage']['chat_elapsed_seconds']=sum(measured) if measured else None;result['usage']['chat_elapsed_measured_count']=len(measured);result['usage']['chat_population']='Latest2000completion/generation receipts; elapsed includes waiting. Earlier unmeasured records stay missing.'
    result['usage']['per_agent']={a['id']:usage_summary([u for wid in a['workflow_ids'] for u in groups.get(wid,[])]) for a in result['agents']}
    result['usage']['not_combined']='Chat and workflow subtotals are separate to avoid double counting.'
    result['usage']['elapsed_workflow_seconds']=sum(a['elapsed_seconds'] for a in result['runs']);result['usage']['elapsed_scope']='Latest300run intervals; includes waiting; may overlap. Not active compute.'
    result['totals']={'workflows':len(result['workflows']),'agents':len(agents),'skills':len(skills),'production_runs':result.get('run_counts',{}).get('production',0),'candidate_runs':result.get('run_counts',{}).get('candidate',0),'chat_completions':result.get('unique_completions',0),'memory_records':result['memory'].get('total',0),'workflow_lessons':sum(a['scope']=='workflow' and a['status']=='active' for a in records)}
    from .observability.usage import summary as codex_usage
    codex=codex_usage(runtime) if runtime is not None else None
    result['usage']['codex']=codex
    if codex:
        result['usage']['chat']={**result['usage'].get('chat',{}),'input_tokens':codex['totals']['input_tokens'],'output_tokens':codex['totals']['output_tokens'],'cached_input_tokens':codex['totals']['cached_input_tokens'],'reasoning_output_tokens':codex['totals']['reasoning_output_tokens'],'complete':False,'meaning':codex['scope']+' Actual token counters; billed cost remains unknown.','source':'Bound Codex token_count metadata'}
    result['documents']=[_document(home,f.relative_to(home)) for f in [home/'company/profile.md',*sorted((home/'company/strategy').rglob('*'))] if f.is_file() and not f.is_symlink() and f.suffix in {'.md','.json','.txt'}]
    for alias in (home/'company/strategy').glob('*'):
        if alias.is_symlink() and alias.resolve().is_relative_to(home/'company/brand'):
            doc=_document(home,alias.resolve().relative_to(home));doc['alias_path']=alias.relative_to(home).as_posix();result['documents'].append(doc)
    result['enforcement']={'workflow':'Candidates require executable rubric and representative, held-out and negative cases. Runs pin the release; actual output is evaluated and release needs independent review.','improvement':'Exact file scope and actual behavioral evidence required; no self-acceptance.','drafts':'Direct tool/file work is draft evidence, never a qualified production Run.','host_reviews':'Same-host diagnostics required by configured lifecycle; missing model/owner decisions remain missing.'}
    clean=sanitize(result)
    # Classification names such as historical_authorization are categories, not credentials.
    clean['memory']['categories']=result['memory']['categories']
    return clean

def state(home):return _json(Path(home)/'.spielos/report-server.json',{})
def display_url(home):
    a=state(home)
    return a.get('url','Run /report to open the company workspace.')

def report_fingerprint():
    """Restart the read-only server when its loaded report dependencies change."""
    root=Path(__file__).resolve().parent;h=hashlib.sha256()
    files=[root/'reporting.py',root/'runtime/config.py']
    files.extend((root/'report_ui').glob('*'))
    files.extend(p for p in (root/'observability').glob('*') if p.suffix in {'.py','.json'})
    for p in sorted(files):
        if p.is_file():h.update(str(p.relative_to(root)).encode());h.update(p.read_bytes())
    return h.hexdigest()

def ensure_server(home,*,open_browser=False,port=None):
    import urllib.request
    from .platform import locked_file,detached_process
    from .runtime.paths import validate_home_destination
    from .home import write_json
    home=validate_home_destination(home);folder=home/'.spielos/state';folder.mkdir(exist_ok=True)
    with locked_file(folder/'report-start.lock'):
        a=state(home)
        if a:
            try:
                req=urllib.request.Request(a['base_url']+'/api/health',headers={'Authorization':'Bearer '+a['token']})
                with urllib.request.urlopen(req,timeout=1) as response:health=json.load(response);healthy=health.get('home')==str(home)
                expected=report_fingerprint()
                if healthy and a.get('runtime_sha256')!=expected and health.get('pid')==a.get('pid'):
                    import signal
                    os.kill(a['pid'],signal.SIGTERM);time.sleep(.15);healthy=False
                if healthy:
                    if open_browser:
                        import webbrowser;webbrowser.open(a['url'])
                    return {k:a[k] for k in ('url','base_url','pid','custom_ui')}
            except (OSError,ValueError,KeyError):pass
        config=configuration(home);log=os.open(home/'.spielos/state/report-server.log',os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(Path(__file__).resolve().parent.parent)}
        try:
            process=subprocess.Popen([sys.executable,'-B','-m','company','report','--serve','--home',str(home),'--port',str(config['port'] if port is None else port)],cwd=home,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,**detached_process())
        finally:os.close(log)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('Report server exited during startup (code '+str(process.returncode)+'); inspect '+str(home/'.spielos/state/report-server.log'))
            time.sleep(.1);candidate=state(home)
            if candidate and candidate.get('pid')==process.pid:
                if open_browser:
                    import webbrowser;webbrowser.open(candidate['url'])
                return {k:candidate[k] for k in ('url','base_url','pid','custom_ui')}
        # Do not orphan a child after a bounded startup failure.
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    raise RuntimeError('Report server was not ready within 15 seconds; inspect '+str(home/'.spielos/state/report-server.log'))

def serve(home,port=8775):
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    from .home import write_json
    home=Path(home).resolve();snapshot(home);config=configuration(home);token=secrets.token_urlsafe(32);cookie_name='spielos_report_'+hashlib.sha256(str(home).encode()).hexdigest()[:10];runtime_sha=report_fingerprint()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def _authorized(self):
            supplied=self.headers.get('Authorization','').removeprefix('Bearer ')
            if supplied==token:return True
            from http.cookies import SimpleCookie
            try:return SimpleCookie(self.headers.get('Cookie','')).get(cookie_name).value==token
            except (AttributeError,ValueError):return False
        def _send(self,status,data,mime='application/json',cookie=False):
            raw=json.dumps(data,ensure_ascii=False).encode() if mime=='application/json' else data
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            if cookie:self.send_header('Set-Cookie',cookie_name+'='+token+'; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            parsed=urlparse(self.path);query=parse_qs(parsed.query);route=unquote(parsed.path)
            if query.get('token')==[token]:
                query.pop('token');self.send_response(303);self.send_header('Set-Cookie',cookie_name+'='+token+'; HttpOnly; SameSite=Strict; Path=/');self.send_header('Location',parsed.path+('?' + urlencode(query,doseq=True) if query else ''));self.send_header('Referrer-Policy','no-referrer');self.end_headers();return
            if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'} or not self._authorized():self._send(403,{'error':'Open the URL from /report in this browser first.'});return
            try:
                if route=='/api/health':self._send(200,{'standard':VERSION,'home':str(home),'pid':os.getpid(),'runtime_sha256':runtime_sha});return
                if route=='/api/report':self._send(200,snapshot(home));return
                if route=='/api/onboarding':
                    from .onboarding import status
                    self._send(200,status(home));return
                if route=='/api/document':self._send(200,_document(home,query.get('path',[''])[0]));return
                if route in ('/','/index.html'):
                    target='/'+config['ui_root']+'/index.html' if config['ui_root'] else '/_spielos/index.html';self.send_response(303);self.send_header('Location',quote(target,safe='/'));self.end_headers();return
                if route.startswith('/_spielos/'):
                    f=Path(__file__).parent/'report_ui'/route.rsplit('/',1)[1]
                    if f.name not in {'index.html','report.js','report.css','workspace.js','workspace.css','logo.png'}:raise PermissionError('Unknown report asset')
                else:f=permitted_file(home,route)
                mime=mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
                # Range playback supports actual full films without returning whole media for every seek.
                size=f.stat().st_size;range_header=self.headers.get('Range','')
                if range_header.startswith('bytes='):
                    start,end=range_header[6:].split('-',1)
                    if not start:
                        suffix=int(end);start=max(0,size-suffix);end=size-1
                    else:start=int(start);end=min(int(end) if end else size-1,size-1)
                    if not 0<=start<=end<size:self._send(416,{'error':'Invalid range'});return
                    self.send_response(206);self.send_header('Content-Type',mime);self.send_header('Content-Range',f'bytes {start}-{end}/{size}');self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.end_headers()
                    with f.open('rb') as stream:stream.seek(start);self.wfile.write(stream.read(end-start+1))
                else:
                    self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(size));self.send_header('Accept-Ranges','bytes');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers()
                    with f.open('rb') as stream:
                        while chunk:=stream.read(1024*1024):self.wfile.write(chunk)
            except (ValueError,PermissionError,FileNotFoundError,UnicodeError) as exc:self._send(403,{'error':str(exc)})
            except (BrokenPipeError,ConnectionResetError):pass
            except Exception:self._send(500,{'error':'Report unavailable; inspect local runtime health.'})
        def do_POST(self):
            if not self._authorized() or self.headers.get('Origin')!=f'http://{self.headers.get("Host")}' or self.headers.get('X-Spielos-Report')!='1':self._send(403,{'error':'Same-origin explicit action required'});return
            try:
                route=urlparse(self.path).path
                if route not in {'/api/open-file','/api/onboarding/choice','/api/onboarding/connect','/api/onboarding/tour'}:raise PermissionError('Unknown action')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Expected a JSON object')
                if route.startswith('/api/onboarding/'):
                    from .onboarding import choose,connect_langfuse,tour_shown
                    if route.endswith('/choice'):result=choose(home,data.get('choice'))
                    elif route.endswith('/tour'):result=tour_shown(home,data.get('report_url'))
                    else:result=connect_langfuse(home,**{k:data.get(k) for k in ('base_url','project_id','public_key','secret_key','approved_evidence_policy')})
                    self._send(200,result);return
                f=permitted_file(home,data.get('path',''))
                if sys.platform!='darwin':self._send(200,{'path':str(f),'opened':False,'message':'Copy this path into your file manager.'});return
                subprocess.run(['/usr/bin/open','-R',str(f)],check=True,timeout=5);self._send(200,{'opened':True,'path':str(f)})
            except (ValueError,PermissionError,FileNotFoundError) as exc:self._send(403,{'error':str(exc)})
    class LoopbackHTTPServer(ThreadingHTTPServer):
        def server_bind(self):
            # HTTPServer's default bind performs reverse DNS. A loopback-only
            # server needs no resolver and must start on offline/slow-DNS hosts.
            from socketserver import TCPServer
            TCPServer.server_bind(self)
            self.server_name='localhost'
            self.server_port=self.server_address[1]
    server=LoopbackHTTPServer(('127.0.0.1',port),Handler);base='http://127.0.0.1:'+str(server.server_port);path='/'+config['ui_root']+'/index.html' if config['ui_root'] else '/_spielos/index.html';url=base+quote(path,safe='/')+'?'+urlencode({'token':token})
    write_json(home/'.spielos/report-server.json',{'schema':1,'pid':os.getpid(),'home':str(home),'base_url':base,'url':url,'token':token,'custom_ui':bool(config['ui_root']),'started_at':_now(),'runtime_sha256':runtime_sha});protect_private(home/'.spielos/report-server.json')
    try:server.serve_forever()
    finally:server.server_close()
