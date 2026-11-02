"""Explicit first-use choices and a private, project-verified Langfuse connection."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .home import write_json
from .platform import is_link,protect_private


def _read(path):
    if is_link(path):raise PermissionError('Onboarding files cannot be links')
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def status(home):
    home=Path(home).resolve()
    state=_read(home/'.spielos/onboarding.json')
    policy=_read(home/'.spielos/telemetry.json')
    configured=policy.get('enabled') is True and bool(policy.get('project_id')) and bool(policy.get('base_url'))
    return {'langfuse_choice':state.get('langfuse_choice'),'ask_langfuse':not configured and not state.get('langfuse_choice'),
        'langfuse_configured':configured,'connection_verified_at':state.get('connection_verified_at'),
        'dashboard_tour_shown':state.get('dashboard_tour_shown') is True,
        'local_capture':policy.get('payload_policy')=='reviewed_evidence',
        'project_url':policy['base_url'].rstrip('/')+'/project/'+str(policy['project_id']) if configured else None}


def _runtime(home):
    from .mcp import CompanySession
    selected=CompanySession();info=selected.select(str(home))
    runtime=selected.runtime(info['company_id']);runtime._actor('configure')
    return runtime


def _save(home,changes):
    from .workflows.runs import stamp
    home=Path(home).resolve();path=home/'.spielos/onboarding.json'
    value=_read(path);value.update(changes);value['updated_at']=stamp()
    write_json(path,value);protect_private(path)
    return status(home)


def choose(home,choice):
    runtime=_runtime(home)
    if choice not in {'local','connect'}:raise ValueError('Choose local use or an explicit Langfuse connection')
    return _save(runtime.home,{'langfuse_choice':choice})


def tour_shown(home,report_url):
    runtime=_runtime(home)
    from .reporting import display_url
    current=display_url(runtime.home)
    supplied=urlsplit(report_url or '')
    actual=urlsplit(current)
    if not isinstance(report_url,str) or supplied.scheme!='http' or supplied.hostname!='127.0.0.1' or (supplied.netloc,supplied.path)!=(actual.netloc,actual.path):
        raise ValueError('Present the actual dashboard link and reading guide before recording its tour')
    return _save(runtime.home,{'dashboard_tour_shown':True,'dashboard_path':urlsplit(report_url).path})


def connect_langfuse(home,*,base_url,project_id,public_key,secret_key,approved_evidence_policy):
    """Only called after an authenticated local form is explicitly submitted."""
    runtime=_runtime(home)
    if approved_evidence_policy!='reviewed_evidence':
        raise ValueError('Explicitly approve the recorded evidence policy for this destination before connecting')
    if not isinstance(project_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',project_id):
        raise ValueError('Choose the exact Langfuse project ID')
    if not all(isinstance(key,str) and 1<=len(key)<=4096 for key in (public_key,secret_key)):
        raise ValueError('Enter the selected project credentials in this local form')
    from .observability.langfuse import LangfuseClient
    client=LangfuseClient(base_url=base_url,project_id=project_id,public_key=public_key,secret_key=secret_key,timeout=5)
    try:projects=client.request('GET','/api/public/projects')
    except Exception as error:raise ValueError('Could not verify the Langfuse connection; export remains unchanged') from error
    if not isinstance(projects,dict) or not isinstance(projects.get('data'),list) or not any(isinstance(row,dict) and row.get('id')==project_id for row in projects['data']):
        raise ValueError('These credentials did not verify the selected project; export remains unchanged')
    # Credentials are never echoed in report data, status, chat or audit payloads.
    reference='.spielos/security/langfuse.json'
    path=runtime.home/reference
    if is_link(path):raise PermissionError('Connection credentials cannot be links')
    write_json(path,{'public_key':public_key,'secret_key':secret_key});protect_private(path)
    from .operations import configure_telemetry
    configure_telemetry(runtime,{'enabled':True,'provider':'langfuse','base_url':client.base_url,'project_id':project_id,
        'payload_policy':'reviewed_evidence','require_verified_release':True,'credential_ref':reference,
        'automatic':{'enabled':True,'judge_runtime':'selected_host'}})
    from .workflows.runs import stamp
    return _save(runtime.home,{'langfuse_choice':'connect','connection_verified_at':stamp()})
