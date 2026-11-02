#!/usr/bin/env python3
"""Read-only lean-company context for startup, resume, compaction and prompts."""
from __future__ import annotations
import json,sys
from pathlib import Path


def selected_home(request):
    candidates=[]
    if request.get('cwd'):candidates.append(Path(request['cwd']).expanduser())
    candidates.append(Path(__file__).resolve().parents[2])
    for candidate in candidates:
        for root in (candidate.resolve(),*candidate.resolve().parents):
            if (root/'.spielos/layout.json').is_file() and (root/'.agents/company/__main__.py').is_file():return root
    return None


def main():
    event='UserPromptSubmit'
    try:
        try:request=json.load(sys.stdin)
        except ValueError:request={}
        if not isinstance(request,dict):request={}
        event=str(request.get('hook_event_name') or request.get('hookEventName') or event)
        root=selected_home(request)
        if root is None:return 0
        sys.path.insert(0,str(root/'.agents'))
        from company.mcp import CompanySession
        session=CompanySession();selected=session.select(str(root));value=session.inspect(selected['company_id'],prompt=str(request.get('prompt') or request.get('user_prompt') or ''))
        from company.observability.receipts import context_payload
        text,documents,human_update=context_payload(value,home=root)
        try:
            from company.observability.sessions import capture_hook
            activity=capture_hook(root,request,host='codex',context=text,documents=documents)
            if activity:text+='\nMachine reference: activity_session='+activity['session_id']+'; pass this session when recording operations and workflow runs.'
            if activity:
                from company.observability.automatic import enabled,pending
                from company.mcp import CompanySession
                selected=CompanySession();chosen=selected.select(str(root));runtime=selected.runtime(chosen['company_id'],readonly=True)
                if enabled(runtime):
                    reviews=pending(runtime,session_id=activity['session_id'],limit=3)
                    if reviews:text+='\nEvaluation work: '+str(len(reviews))+' frozen outputs await a bounded review by this host model. Use evaluation pending and evaluation judge; preserve artifact-specific evidence and do not grant independent acceptance.'
                    health=root/'.spielos/telemetry-health.json'
                    if health.is_file():
                        status=json.loads(health.read_text())
                        if not status.get('synchronized'):text+='\nObservability: delivery or native evaluation registration is awaiting Langfuse confirmation; inspect telemetry health for backlog and rate-limit status.'
        except Exception:
            text+='\nActivity recording is incomplete. Do not claim this session is fully observable in Langfuse.'
        prompt=str(request.get('prompt') or request.get('user_prompt') or '').strip()
        if prompt=='/report' or prompt.startswith('/report '):
            from company.reporting import ensure_server
            report=ensure_server(root,open_browser=True)
            text+='\n/report opened the live company dashboard. Give the owner this clickable link: '+report['url']
        text+='\nOwner-facing visibility: give a concise commentary update for relevant context changes. '+human_update+' Do not repeat the full inventory. Link /report for details; preserve the scoped context above.'
        print(json.dumps({'hookSpecificOutput':{'hookEventName':event,'additionalContext':text}},ensure_ascii=False))
    except Exception:
        print(json.dumps({'hookSpecificOutput':{'hookEventName':event,'additionalContext':
            'SpielOS context injection failed. Read company status once from the selected installed home and report the missing projection; do not infer company state.'}}))
    return 0


if __name__=='__main__':raise SystemExit(main())
