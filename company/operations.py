"""Read-only operational readiness and explicit, scoped telemetry configuration."""
import json,os
import sqlite3
from pathlib import Path
from .home import canonical,write_json


def telemetry_status(runtime):
    path=runtime.home/'.spielos/telemetry.json' if runtime.home else None
    config=json.loads(path.read_text()) if path and path.is_file() and not path.is_symlink() else {}
    with runtime.connect() as connection:
        try:
            rows=connection.execute("SELECT 'workflow',status,COUNT(*) FROM workflow_export_outbox GROUP BY status UNION ALL SELECT 'activity',status,COUNT(*) FROM activity_exports GROUP BY status").fetchall()
            counts={state:count for kind,state,count in rows if kind=='workflow'}
            activity={state:count for kind,state,count in rows if kind=='activity'}
        except sqlite3.OperationalError:
            counts=dict(connection.execute('SELECT status,COUNT(*) FROM workflow_export_outbox GROUP BY status'));activity={}
    return {'state':'enabled' if config.get('enabled') is True else 'disabled',
            'provider':config.get('provider'),'project_id':config.get('project_id'),
            'require_verified_release':config.get('require_verified_release',False),
            'payload_policy':config.get('payload_policy'),'evaluation_standard':config.get('evaluation_standard'),
            'events':counts,'activity_events':activity,
            'synchronized':bool(counts or activity) and set(counts)|set(activity)<={'verified'}}


def configure_telemetry(runtime,config):
    actor=runtime._actor('configure')
    required={'enabled','provider','project_id','base_url','payload_policy','require_verified_release'}
    if required-set(config) or set(config)-required-{'credential_ref','evaluation_standard','automatic'} or config['enabled'] is not True or config['provider']!='langfuse' or config['payload_policy'] not in {'digests_only','reviewed_evidence'} or not isinstance(config['require_verified_release'],bool):
        raise ValueError('Choose the exact Langfuse destination, evidence policy and release requirement')
    if config['payload_policy']=='reviewed_evidence' and config['require_verified_release'] is not True:
        raise ValueError('Inspectable evaluation evidence requires verified Langfuse qualification')
    if 'automatic' in config and (not isinstance(config['automatic'],dict) or config['automatic'].get('enabled') is not True or config['automatic'].get('judge_runtime')!='selected_host'):
        raise ValueError('Automatic evaluation must use the selected host model and explicit lifecycle triggers')
    from .observability.langfuse import LangfuseClient
    LangfuseClient(base_url=config['base_url'],project_id=config['project_id'],authorization='Basic validation-only')
    if config.get('credential_ref'):LangfuseClient.from_configuration(runtime.home,config)
    path=runtime.home/'.spielos/telemetry.json'
    if path.is_symlink():raise PermissionError('Telemetry configuration must remain in the selected home')
    write_json(path,config)
    with runtime.connect() as connection:runtime._audit(connection,'telemetry_configure','company',config,actor=actor)
    return telemetry_status(runtime)


def require_activity_telemetry(runtime, session_id):
    """A local pass is not a remotely observable qualification."""
    from .observability.sessions import Sessions, policy
    config=policy(runtime)
    if config.get('payload_policy')!='reviewed_evidence' or not config.get('require_verified_release'):
        raise ValueError('Qualification requires the reviewed-evidence Langfuse policy')
    session=Sessions(runtime).show(session_id)
    prefix=config['base_url'].rstrip('/')+'/project/'+config['project_id']+'/traces/'
    if not session['observable'] or any(not (row['remote_reference'] or '').startswith(prefix) for row in session['telemetry']):
        raise ValueError('Qualification requires exact Langfuse readback for the session evidence')


def require_release_telemetry(runtime,run_ids):
    status=telemetry_status(runtime)
    if status['state']!='enabled' or status['payload_policy']!='reviewed_evidence' or not status['require_verified_release']:
        raise ValueError('New releases require Langfuse reviewed-evidence policy and verified remote evidence')
    from .observability.automatic import enabled
    if enabled(runtime):
        with runtime.connect() as c:
            for identity in run_ids:
                row=c.execute('SELECT release_digest FROM workflow_invocations WHERE id=?',(identity,)).fetchone()
                definition=c.execute('SELECT status FROM native_evaluation_definitions WHERE key=?',('workflow:'+row[0],)).fetchone()
                if not definition or definition[0]!='verified':raise ValueError('Release requires its exact human-readable native Langfuse evaluator and rule definition')
                manifest=runtime.manifest(row[0])
                if manifest.get('resolved_agent'):
                    agent=c.execute('SELECT status FROM native_evaluation_definitions WHERE key=?',('agent:'+manifest['resolved_agent']['id'],)).fetchone()
                    if not agent or agent[0]!='verified':raise ValueError('Release requires the bound agent’s native evaluation definition')
    with runtime.connect() as connection:
        for identity in run_ids:
            events=connection.execute('SELECT status,remote_reference,payload_json FROM workflow_export_outbox WHERE run_id=?',(identity,)).fetchall()
            config=json.loads((runtime.home/'.spielos/telemetry.json').read_text())
            prefix=config['base_url'].rstrip('/')+'/project/'+config['project_id']+'/traces/'
            if not events or any(row[0]!='verified' or not (row[1] or '').startswith(prefix) or json.loads(row[2]).get('context_export')!='reviewed_evidence' for row in events):
                raise ValueError('Release requires verified Langfuse evidence for every candidate run')


def measured_files(root,names):
    """Hash actual files; never accept a caller-supplied hash as file evidence."""
    import hashlib
    root=Path(root).expanduser().resolve();result={}
    if not root.is_dir():raise ValueError('Choose an existing explicit change root')
    for name in names:
        relative=Path(name);path=root/relative
        if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Change evidence must stay inside its explicit root')
        if not path.is_file():raise ValueError('Change evidence needs an actual file: '+name)
        result[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result
