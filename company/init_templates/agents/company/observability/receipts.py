"""Truthful, bounded Markdown receipts for host-owned chat delivery."""
import hashlib,json

def context_payload(value,*,session_id=None,home=None):
    """Only actually supplied profile/selected memories; available strategy is not loaded strategy."""
    ctx=value['context'];memory=ctx.get('memory_projection',{}).get('documents',[])
    lines=['Company work','Company profile\n'+value.get('profile',''), 'Available workflows']
    lines.extend((w.get('purpose') or w.get('id','Workflow'))+' — '+w.get('readiness','draft') for w in value.get('workflows',[]))
    docs={'company/profile.md':value.get('profile','')}
    if home:
        from pathlib import Path
        contract=Path(home)/'company/evaluation-and-learning-contract.md'
        if contract.is_file() and not contract.is_symlink():
            docs['company/evaluation-and-learning-contract.md']=contract.read_text();lines.append('Mandatory company evaluation contract\n'+docs['company/evaluation-and-learning-contract.md'])
    if memory:
        lines.append('Relevant owner/workflow context')
        for row in memory:
            lines.append(row['source']+': '+row['text']);docs['memory/'+row['name']]=row['text']
    pending=ctx.get('pending',[]);improvements=ctx.get('improvements',[])
    lines.append(str(len(pending))+' production runs need attention; '+str(len(improvements))+' Improvements remain open. Inspect /report for the complete history.')
    phrases={'awaiting_provider':'is waiting for its assigned executor','awaiting_evaluation':'has output awaiting evaluation','awaiting_review':'needs independent review'}
    for item in pending[:5]:
        w=next((w for w in value.get('workflows',[]) if w.get('id')==item.get('workflow_id')),{})
        lines.append((w.get('purpose') or 'A workflow run')+' '+phrases.get(item.get('status'),'needs attention')+'.')
    for item in improvements[-3:]:lines.append(item.get('name','Improvement')+' — '+{'act':'implementation in progress','observe':'being investigated','decide':'awaiting a design decision','awaiting_change_review':'awaiting independent review'}.get(item.get('stage'),'pending review'))
    telemetry=ctx.get('telemetry',{});remaining=sum(n for pop in (telemetry.get('events',{}),telemetry.get('activity_events',{})) for s,n in pop.items() if s!='verified')
    lines.append('Langfuse: '+str(remaining)+' events are not yet confirmed. Never call queued evidence synchronized.' if telemetry.get('state')=='enabled' else 'Activity stays local; Langfuse is not connected.')
    if session_id:lines.append('Machine reference: activity_session='+session_id+'; use this session for actual operations. No direct-chat artifact is a qualified workflow Run.')
    lines.append('Machine reference: '+json.dumps({'pending':pending,'counts':ctx.get('counts',{}),'activity_session':session_id},ensure_ascii=False))
    text='\n'.join(lines);docs['runtime/operating-summary']='\n'.join(lines[-6:])
    phrase='Company context ready: profile and '+str(len(memory))+' selected memory records are available for this task.'
    return text,docs,phrase

def markdown(runtime,session_id):
    from ..reporting import display_url
    from .sessions import policy
    with runtime.connect() as c:
        turn=c.execute('SELECT turn_key FROM activity_turn_heads WHERE session_id=?',(session_id,)).fetchone()
        turn=turn[0] if turn else None
        counts=dict(c.execute('SELECT status,COUNT(*) FROM activity_exports WHERE id IN (SELECT id FROM activity_events WHERE session_id=? AND json_extract(record_json,\'$.turn_key\')=?) GROUP BY status',(session_id,turn))) if turn else {}
        reports=c.execute("SELECT COUNT(*) FROM host_evaluation_requests WHERE session_id=? AND turn_key=? AND status='pending'",(session_id,turn)).fetchone()[0] if turn else 0
        judgments=c.execute("SELECT COUNT(*) FROM host_evaluation_requests WHERE session_id=? AND turn_key=? AND status='reviewed'",(session_id,turn)).fetchone()[0] if turn else 0
        usage=c.execute("SELECT record_json FROM activity_events WHERE session_id=? AND kind='end' AND json_extract(record_json,'$.turn_key')=? ORDER BY rowid DESC LIMIT 1",(session_id,turn)).fetchone() if turn else None
    data=json.loads(usage[0])['payload'] if usage else {};u=data.get('usage',{})
    config=policy(runtime);project=config.get('base_url','https://cloud.langfuse.com')+'/project/'+str(config.get('project_id',''))
    trace=hashlib.sha256(('spielos:'+session_id+':turn:'+turn).encode()).hexdigest()[:32] if turn else None
    url=display_url(runtime.home);workspace='[Company report]('+url+')' if url.startswith('http') else 'Open `/report` for the company report'
    delivery=str(counts.get('verified',0))+' confirmed; '+str(sum(n for s,n in counts.items() if s!='verified'))+' pending'
    try:
        from .usage import summary
        observed=summary(runtime)
        current=next((t for t in observed['turns'] if t['session_id']==session_id and t['turn_key']==turn),None) if observed else None
        if current:u=current['usage']
    except (ValueError,KeyError):pass
    tokens=str(u.get('input_tokens','not reported'))+' in / '+str(u.get('output_tokens','not reported'))+' out'
    cost=str(u['cost'])+' '+u.get('currency','') if u.get('cost') is not None else 'Not reported'
    heading='**Work tracked** · '+workspace
    connected=config.get('enabled') is True and bool(config.get('project_id')) and bool(config.get('base_url'))
    if connected and trace:heading+=' · [Langfuse trace]('+project+'/traces/'+trace+')'
    if not trace:return heading
    evaluation=(str(reports)+' frozen reviews pending') if reports else (str(judgments)+' recorded judgments; independent acceptance remains separate') if judgments else 'No judgment recorded; independent acceptance remains separate'
    elapsed=str(round(data['elapsed_seconds'],1))+'s including tool/wait time' if data.get('elapsed_seconds') is not None else 'Not measured'
    rows=[('Evaluation',evaluation),('Langfuse',delivery if connected else 'Not connected; activity stays local'),
          ('Tokens',tokens),('Cost',cost),('Turn elapsed',elapsed)]
    return heading+'\n\n| Tracking | Status |\n| --- | --- |\n'+'\n'.join('| '+name+' | '+value+' |' for name,value in rows)
