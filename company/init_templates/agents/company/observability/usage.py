"""Bound, metadata-only Codex usage import. Never discovers or exports conversations."""
from __future__ import annotations
import hashlib,json,os,math
from datetime import datetime,timezone
from pathlib import Path

SCHEMA='''CREATE TABLE IF NOT EXISTS host_usage_sources(session_id TEXT PRIMARY KEY,path TEXT NOT NULL,host_session TEXT NOT NULL,metadata_digest TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS host_usage_turns(session_id TEXT NOT NULL,turn_key TEXT NOT NULL,record_json TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(session_id,turn_key));'''
FIELDS=('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens','total_tokens')

def host_time(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):return datetime.fromtimestamp(value/1000 if value>1e12 else value,timezone.utc).isoformat()
    return value

def pricebook():return json.loads(Path(__file__).with_name('pricing.json').read_text())
def estimate(usage,model,*,request_input=None):
    book=pricebook();p=book['models'].get(model)
    if not p:return {'status':'unknown','model':model,'reason':'No verified reference price for this exact model.'}
    i=usage['input_tokens'];cache=usage.get('cached_input_tokens');write=usage.get('cache_write_input_tokens');o=usage['output_tokens']
    if cache is None or write is None or cache+write>i:return {'status':'unknown','reason':'Cache accounting is incomplete or inconsistent.'}
    credits=((i-cache)*p['codex_standard_credits_per_million']['input']+cache*p['codex_standard_credits_per_million']['cached_input']+o*p['codex_standard_credits_per_million']['output'])/1e6
    long=request_input is not None and request_input>p['api_long_context']['above_input_tokens'];a=2 if long else 1;b=1.5 if long else 1;rate=p['api_per_million']
    equivalent=((i-cache-write)*rate['input']*a+cache*rate['cached_input']*a+write*rate['cache_write_input']*a+o*rate['output']*b)/1e6 if request_input is not None else None
    return {'status':'estimated','actual_bill':None,'standard_reference_credits':credits,'api_standard_equivalent_usd':equivalent,'price_verified_at':book['verified_at'],'api_source':p['api_source'],'codex_source':p['codex_source'],'basis':book['basis'],'assumptions':p['assumptions'],'api_long_context_applied':long}

def read_codex(path,*,host_session,home):
    """Only explicit host/user supplied source, exact session and home. Whitelist metadata fields."""
    path=Path(path).expanduser();root=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex'))).resolve();home=Path(home).resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root) or path.suffix!='.jsonl' or not path.is_file() or path.stat().st_uid!=os.getuid():raise PermissionError('Usage source must be an explicitly bound local Codex log')
    relative=path.resolve().relative_to(root)
    if not relative.parts or relative.parts[0] not in {'sessions','archived_sessions'}:raise PermissionError('Usage source is outside Codex session metadata')
    if any((root/Path(*relative.parts[:i])).is_symlink() for i in range(1,len(relative.parts)+1)):raise PermissionError('Usage source cannot traverse symbolic paths')
    turns={};current='unattributed-prefix';model=None;previous={k:0 for k in FIELDS};seen=set();meta=None;events=0;resets=0;digest=hashlib.sha256(b'codex-metadata-v2-utc')
    with path.open() as stream:
        for line in stream:
            # Message, tool and reasoning records are neither decoded nor retained.
            if not any(t in line[:180] for t in ('"session_meta"','"turn_context"','"event_msg"')):continue
            if not any(t in line for t in ('"session_meta"','"turn_context"','"token_count"','"task_started"','"task_complete"')):continue
            try:r=json.loads(line)
            except ValueError:continue
            payload=r.get('payload',{});kind=r.get('type')
            if kind=='session_meta':
                meta={'id':payload.get('id'),'cwd':payload.get('cwd')}
                if meta['id']!=host_session or Path(meta['cwd'] or '/').resolve()!=home:raise PermissionError('Usage metadata belongs to another chat or company')
                continue
            if meta is None:continue
            if kind=='turn_context':current=payload.get('turn_id') or current;model=payload.get('model') or model
            elif kind=='event_msg' and payload.get('type')=='task_started':current=payload.get('turn_id') or current;model=None
            elif kind!='event_msg' or payload.get('type') not in {'token_count','task_complete'}:continue
            turn=turns.setdefault(current,{'turn_key':current,'model':model,'started_at':None,'completed_at':None,'duration_ms':None,'usage':{k:0 for k in FIELDS},'pricing':{'standard_reference_credits':0.0,'api_standard_equivalent_usd':0.0,'api_unpriced_events':0},'events':0})
            turn['model']=model
            if kind=='event_msg' and payload.get('type')=='task_started':turn['started_at']=host_time(payload.get('started_at') or r.get('timestamp'));continue
            if kind=='event_msg' and payload.get('type')=='task_complete':
                turn['completed_at']=host_time(payload.get('completed_at') or r.get('timestamp'));turn['duration_ms']=payload.get('duration_ms');digest.update(json.dumps([current,turn['completed_at'],turn['duration_ms']]).encode());continue
            if kind!='event_msg' or payload.get('type')!='token_count':continue
            info=payload.get('info') or {};total=info.get('total_token_usage');last=info.get('last_token_usage') or {}
            if not isinstance(total,dict) or any(k not in total or not isinstance(total[k],int) or isinstance(total[k],bool) or total[k]<0 for k in FIELDS):continue
            clean={k:total[k] for k in FIELDS}
            if clean['total_tokens']!=clean['input_tokens']+clean['output_tokens']:raise ValueError('Total tokens must include input and output exactly once')
            identity=json.dumps([r.get('timestamp'),current,clean],sort_keys=True)
            if identity in seen:continue
            seen.add(identity)
            if any(clean[k]<previous[k] for k in FIELDS):previous={k:0 for k in FIELDS};resets+=1
            delta={k:clean[k]-previous[k] for k in FIELDS};previous=clean
            if not delta['total_tokens']:continue
            if delta['cached_input_tokens']+delta['cache_write_input_tokens']>delta['input_tokens'] or delta['reasoning_output_tokens']>delta['output_tokens']:raise ValueError('Codex token counters are inconsistent')
            for k in FIELDS:turn['usage'][k]+=delta[k]
            pricing=estimate(delta,model,request_input=last.get('input_tokens') if last.get('input_tokens')==delta['input_tokens'] else None)
            if pricing['status']=='estimated':
                turn['pricing']['standard_reference_credits']+=pricing['standard_reference_credits']
                if pricing['api_standard_equivalent_usd'] is not None:turn['pricing']['api_standard_equivalent_usd']+=pricing['api_standard_equivalent_usd']
                else:turn['pricing']['api_unpriced_events']+=1
            else:turn['pricing']['api_unpriced_events']+=1
            turn['events']+=1;turn['last_usage_at']=r.get('timestamp');digest.update(identity.encode());events+=1
    if meta is None:raise ValueError('Codex session identity is missing')
    return {'source':str(path),'host_session':host_session,'metadata_digest':digest.hexdigest(),'turns':[t for t in turns.values() if t['events']],'token_events':events,'counter_resets':resets,'pricing_reference':pricebook(),'privacy':'Only session identity, model, turn timestamps and token counters; no conversation or reasoning bodies.'}

def ingest(runtime,session_id,*,path=None,publish=False):
    from .sessions import Sessions
    from ..workflows.runs import canonical,stamp,digest
    runtime._actor('run')
    with runtime.connect() as c:
        c.executescript(SCHEMA);session=c.execute('SELECT * FROM activity_sessions WHERE id=?',(session_id,)).fetchone();old=c.execute('SELECT * FROM host_usage_sources WHERE session_id=?',(session_id,)).fetchone()
    if not session or session['host']!='codex':raise ValueError('Usage import needs the selected Codex session')
    path=path or (old['path'] if old else None)
    if not path:return {'state':'unavailable','reason':'No explicit bound usage source supplied'}
    result=read_codex(path,host_session=session['host_session'],home=runtime.home)
    if old and Path(old['path']).resolve()!=Path(path).resolve():raise ValueError('The session usage source is already bound')
    if old and old['metadata_digest']==result['metadata_digest']:return {'state':'unchanged','turns':len(result['turns'])}
    from .automatic import prepare
    prepare(runtime)
    now=stamp();sessions=Sessions(runtime)
    with runtime.connect() as c:
        c.execute('INSERT OR REPLACE INTO host_usage_sources VALUES(?,?,?,?,?)',(session_id,result['source'],session['host_session'],result['metadata_digest'],now))
        for t in result['turns']:c.execute('INSERT OR REPLACE INTO host_usage_turns VALUES(?,?,?,?)',(session_id,t['turn_key'],canonical(t),now))
    if publish:
        for t in result['turns']:
            if not t['completed_at']:continue
            event_key='codex-usage:'+digest({'turn':t['turn_key'],'usage':t['usage']})
            with runtime.connect() as c:exists=c.execute('SELECT 1 FROM activity_events WHERE session_id=? AND request_key=?',(session_id,event_key)).fetchone()
            if exists:continue
            sessions.turn_key=t['turn_key'];u={**t['usage'],'status':'actual','source':'Codex host token_count metadata','scope':'turn_total'}
            sessions.record(session_id,kind='generation',request_key=event_key,payload={'source':'Bound Codex usage metadata only','model':t['model'],'usage':u,'pricing_reference':t['pricing'],'price_source':result['pricing_reference'],'billing':'Actual paid cost unknown; standard reference prices are estimates','duration_ms':t['duration_ms']})
    return {'state':'recorded','turns':len(result['turns']),'token_events':result['token_events'],'counter_resets':result['counter_resets'],'metadata_digest':result['metadata_digest']}

def summary(runtime):
    with runtime.connect() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='host_usage_turns'").fetchone():return None
        rows=[{**json.loads(r[1]),'session_id':r[0]} for r in c.execute("SELECT session_id,record_json FROM host_usage_turns ORDER BY json_extract(record_json,'$.started_at') DESC")];sources=[{'session_id':r[0],'host_session':r[1],'updated_at':r[2]} for r in c.execute('SELECT session_id,host_session,updated_at FROM host_usage_sources')]
    if not rows:return None
    totals={k:sum(t['usage'][k] for t in rows) for k in FIELDS}
    return {'totals':totals,'turns':rows,'sources':sources,'standard_reference_credits':sum(t['pricing']['standard_reference_credits'] for t in rows),'api_standard_equivalent_usd':sum(t['pricing']['api_standard_equivalent_usd'] for t in rows),'api_unpriced_events':sum(t['pricing']['api_unpriced_events'] for t in rows),'actual_bill':None,'pricing_reference':pricebook(),'scope':'Only explicitly bound Codex chats; other hosts or unbound sessions remain unmeasured.'}
