"""SpielOS public surface: Company, Workflow, Run and Improvement."""
from __future__ import annotations
import argparse,json,os,sqlite3,sys
from pathlib import Path
if not __package__:
    sys.path[0]=str(Path(__file__).resolve().parent.parent)
    __package__='company'
from .platform import owned_path
from .runtime.config import VERSION
from .runtime.paths import find_project_root,validate_home_destination

PROJECT_ROOT=find_project_root()
DEFAULT_DB=PROJECT_ROOT/'.spielos/state/workflows.sqlite'
RETIRED={'goal','runner','tasks','notifications','evidence','approve'}


def build_parser():
    parser=argparse.ArgumentParser(prog='spielos',description='Company context and governed bounded workflows.')
    parser.add_argument('--db',help='explicit workflow database inside the selected company state folder')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('mcp',help='local MCP server; select a company through its tools')
    report=commands.add_parser('report',help='open the live company dashboard on an authenticated loopback server')
    report.add_argument('--home',required=True);report.add_argument('--json',action='store_true');report.add_argument('--serve',action='store_true');report.add_argument('--snapshot',action='store_true');report.add_argument('--no-open',action='store_true');report.add_argument('--port',type=int)
    activity=commands.add_parser('activity',help='inspect and record host/Director activity, context, feedback and artifacts')
    activity.add_argument('activity_command',choices=('start','show','record','context','artifact','export','import-ratings','import-usage'))
    activity.add_argument('--payload',help='JSON evidence object');activity.add_argument('--session')
    activity.add_argument('--home',required=True);activity.add_argument('--json',action='store_true')
    evaluation=commands.add_parser('evaluation',help='standard suites and comparable evaluation experiments')
    evaluation.add_argument('evaluation_command',choices=('template','register','show','evaluate-event','compare','pending','judge'))
    evaluation.add_argument('--session')
    evaluation.add_argument('--subject',choices=('director','build','system_improvement','workflow','agent'))
    evaluation.add_argument('--payload');evaluation.add_argument('--home',required=True);evaluation.add_argument('--json',action='store_true')
    init=commands.add_parser('init',help='create a separate lean company home')
    init.add_argument('--dir',default='.');init.add_argument('--force',action='store_true')
    init.add_argument('-y','--yes',action='store_true');init.add_argument('--json',action='store_true')
    update=commands.add_parser('update',help='refresh product files while preserving company content')
    update.add_argument('--dir',default='.');update.add_argument('--keep-stale',action='store_true');update.add_argument('--json',action='store_true')
    migrate=commands.add_parser('migrate',help='preview or apply an exact lean migration')
    migrate.add_argument('--dir',required=True);migrate.add_argument('--plan');migrate.add_argument('--digest');migrate.add_argument('--json',action='store_true')
    for name in ('status','overview','context','catalog','departments','layout'):
        item=commands.add_parser(name,help='read selected company '+name)
        item.add_argument('--home',default=None);item.add_argument('--json',action='store_true')
        if name=='context':
            item.add_argument('--prompt',default='');item.add_argument('--owner');item.add_argument('--workflow');item.add_argument('--token-budget',type=int,default=6000)
    brand=commands.add_parser('brand',help='pin actual company brand references and independently review a rendered example')
    brand_sub=brand.add_subparsers(dest='brand_command',required=True)
    brand_candidate=brand_sub.add_parser('candidate');brand_candidate.add_argument('--version',required=True);brand_candidate.add_argument('--files',required=True)
    brand_release=brand_sub.add_parser('release');brand_release.add_argument('--candidate',required=True);brand_release.add_argument('--inspection',required=True)
    brand_show=brand_sub.add_parser('show');brand_show.add_argument('release_digest')
    for item in brand_sub.choices.values():item.add_argument('--home',required=True);item.add_argument('--json',action='store_true')
    profile=commands.add_parser('profile',help='read or record explicit company identity, responsibilities and boundaries')
    profile_sub=profile.add_subparsers(dest='profile_command',required=True)
    profile_sub.add_parser('show')
    profile_set=profile_sub.add_parser('set');profile_set.add_argument('--fields',required=True);profile_set.add_argument('--source',required=True)
    for item in profile_sub.choices.values():item.add_argument('--home',required=True);item.add_argument('--json',action='store_true')
    history=commands.add_parser('history',help='read preserved legacy records; never resume or replay them')
    history.add_argument('--home',required=True);history.add_argument('--kind',choices=('goals','runs','evidence','work_orders','memory','approvals'),default='goals')
    history.add_argument('--limit',type=int,default=50);history.add_argument('--json',action='store_true')
    workflow=commands.add_parser('workflow',help='build, release, run and review bounded workflows')
    sub=workflow.add_subparsers(dest='workflow_command',required=True)
    candidate=sub.add_parser('candidate');candidate.add_argument('--manifest',required=True)
    release=sub.add_parser('release');release.add_argument('--release',required=True);release.add_argument('--runs',required=True);release.add_argument('--reviewer')
    run=sub.add_parser('run');run.add_argument('--release',required=True);run.add_argument('--inputs',required=True);run.add_argument('--request-key',required=True);run.add_argument('--candidate-case')
    wake=sub.add_parser('wake');wake.add_argument('--run',dest='wake_run')
    experiment=sub.add_parser('experiment',help='execute representative, held-out and negative candidate cases')
    experiment.add_argument('--release',required=True);experiment.add_argument('--name',required=True);experiment.add_argument('--request-key',required=True)
    experiment_show=sub.add_parser('experiment-show');experiment_show.add_argument('experiment_id')
    measurement=sub.add_parser('measure',help='record an explicit business observation separately from quality')
    measurement.add_argument('--measurement',required=True)
    calibration=sub.add_parser('calibrate-judge',help='record independent ratings of actual artifacts for a pinned model judge')
    calibration.add_argument('--judge',required=True);calibration.add_argument('--ratings',required=True);calibration.add_argument('--reason',required=True);calibration.add_argument('--maximum-disagreement',type=float,default=0.2)
    sub.add_parser('scorecard',help='read workflow, quality, usage and outcome populations')
    export=sub.add_parser('export',help='export pending events to the explicitly configured Langfuse project')
    export.add_argument('--limit',type=int,default=10);export.add_argument('--max-attempts',type=int,default=20)
    telemetry=sub.add_parser('configure-telemetry');telemetry.add_argument('--config',required=True)
    for name in ('show','claim','deliver','reconcile','cancel','evaluate','review','approve-action'):
        item=sub.add_parser(name);item.add_argument('run_id')
        if name=='deliver':item.add_argument('--output',required=True);item.add_argument('--token',required=True)
        if name=='evaluate':item.add_argument('--case');item.add_argument('--verdicts');item.add_argument('--evaluator')
        if name in {'review','approve-action'}:
            item.add_argument('--reviewer');item.add_argument('--decision',required=True,choices=('accept','reject') if name=='review' else ('approve','reject'))
        if name=='approve-action':item.add_argument('--action',required=True)
    for item in sub.choices.values():item.add_argument('--home',required=True);item.add_argument('--json',action='store_true');item.add_argument('--session')
    memory=commands.add_parser('memory',help='explicit owner preferences, strategy and evidence-backed workflow lessons')
    sub=memory.add_subparsers(dest='memory_command',required=True)
    summary=sub.add_parser('summary');summary.add_argument('--workflow')
    add=sub.add_parser('add');add.add_argument('--scope',choices=('owner','strategy','workflow'),required=True)
    add.add_argument('--claim',required=True);add.add_argument('--workflow');add.add_argument('--run',action='append',default=[]);add.add_argument('--source')
    retire=sub.add_parser('retire');retire.add_argument('memory_id');retire.add_argument('--reason',required=True)
    classify=sub.add_parser('classify');classify.add_argument('memory_id');classify.add_argument('--category',required=True);classify.add_argument('--topic',action='append',default=[]);classify.add_argument('--critical',action='store_true');classify.add_argument('--reason',required=True)
    for item in sub.choices.values():item.add_argument('--home',required=True);item.add_argument('--json',action='store_true')
    improvement=commands.add_parser('improvement',help='bounded GODAE development without autonomous pursuit')
    sub=improvement.add_subparsers(dest='improvement_command',required=True)
    create=sub.add_parser('create');create.add_argument('--brief',required=True)
    show=sub.add_parser('show');show.add_argument('improvement_id')
    for name in ('observe','agree-architecture','attach-candidate','attach-change','reconcile','revise','decide'):
        item=sub.add_parser(name);item.add_argument('improvement_id')
        if name=='observe':item.add_argument('--observation',required=True)
        if name=='agree-architecture':item.add_argument('--architecture',required=True)
        if name=='attach-candidate':item.add_argument('--release',required=True);item.add_argument('--changed-files',required=True)
        if name=='attach-change':
            item.add_argument('--root',required=True);item.add_argument('--changed-files',required=True);item.add_argument('--evidence-files',required=True)
        if name=='revise':item.add_argument('--reason',required=True)
        if name=='reconcile':
            item.add_argument('--evidence-files',required=True);item.add_argument('--reason',required=True)
        if name=='decide':item.add_argument('--decision',choices=('accept','revise','reject'),required=True);item.add_argument('--reason',required=True);item.add_argument('--runs')
    for item in sub.choices.values():item.add_argument('--home',required=True);item.add_argument('--json',action='store_true');item.add_argument('--session')
    export=commands.add_parser('export',help='export a workflow and its declarative dependency closure')
    export.add_argument('workflow_id');export.add_argument('--out',required=True);export.add_argument('--package-id',required=True);export.add_argument('--version',default='1')
    export.add_argument('--home',required=True);export.add_argument('--json',action='store_true')
    incoming=commands.add_parser('import',help='preview a portable package or apply its exact reviewed plan')
    incoming.add_argument('folder',nargs='?');incoming.add_argument('--plan');incoming.add_argument('--digest')
    incoming.add_argument('--home',required=True);incoming.add_argument('--json',action='store_true')
    return parser


def read_json(path):return json.loads(Path(path).expanduser().read_text())


def authority_for(home):
    from .security import CompanyAuthority
    authority=CompanyAuthority(home);token=os.environ.get('SPIELOS_PRINCIPAL_TOKEN')
    principal=authority.authenticate(token) if token else authority.local_owner()
    authority.authorize(principal,'read')
    return authority,principal


def runtime_for(args,*,readonly=False):
    from .workflows.runs import WorkflowRuntime
    home=validate_home_destination(args.home or PROJECT_ROOT)
    authority,principal=authority_for(home)
    database=Path(args.db).expanduser() if args.db else home/'.spielos/state/workflows.sqlite'
    runtime=WorkflowRuntime(database,home=home,principal=principal,readonly=readonly)
    runtime.activity_session_id=getattr(args,'session',None) or os.environ.get('SPIELOS_SESSION_ID') or getattr(runtime,'activity_session_id',None)
    return runtime


def legacy_history(home,*,kind='goals',limit=50):
    """A fresh in-memory SQLite snapshot keeps WAL history read-only."""
    if kind not in {'goals','runs','evidence','work_orders','memory','approvals'} or not 1<=limit<=500:raise ValueError('Choose a bounded legacy history population')
    home=validate_home_destination(home)
    if (home/'.spielos/layout.json').is_file():authority_for(home)
    elif os.environ.get('SPIELOS_PRINCIPAL_TOKEN') or not owned_path(home):
        raise PermissionError('Legacy history requires its local filesystem owner until migration establishes company authority')
    path=home/'.spielos/state/company.sqlite'
    if not path.is_file():return {'records':[],'policy':'read_only; never resumed or replayed'}
    if path.is_symlink() or not path.resolve().is_relative_to(home):raise ValueError('Legacy history must remain in its selected company')
    source=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);snapshot=sqlite3.connect(':memory:')
    try:
        source.backup(snapshot);snapshot.row_factory=sqlite3.Row
        rows=[dict(row) for row in snapshot.execute('SELECT * FROM core_'+kind+' ORDER BY rowid DESC LIMIT ?',(limit,))]
        return {'kind':kind,'records':rows,'policy':'read_only; never resumed or replayed'}
    finally:source.close();snapshot.close()


def owner_text(command,output):
    if command in {'status','overview','context'}:return output['context']['text'].split('\nMachine reference:')[0]
    if command=='catalog':return '\n'.join(row.get('purpose') or 'Workflow definition needs repair.' for row in output['workflows']) or 'No workflows have been defined.'
    if command=='brand':return 'The brand candidate is ready for independent rendered review.' if output.get('status')=='candidate' else 'The approved brand version is available for workflow use.'
    if command=='history':return str(len(output['records']))+' preserved historical records. They remain read-only and will not be replayed.'
    if command=='activity' and 'events' in output:
        return ('The '+output.get('role','company')+' activity is recorded. '+str(len(output['events']))+' events are available. '+('Langfuse evidence is verified.' if output.get('observable') else 'Langfuse verification is pending.'))
    if command=='evaluation' and output.get('state'):
        return {'verified_pass':'The experiment passed and its Langfuse evidence is verified.','awaiting_telemetry':'The experiment passed locally; Langfuse verification is pending.','failed':'The experiment found a quality failure.','awaiting_evidence':'The experiment needs execution or evaluation evidence.'}.get(output['state'],'The evaluation specification is recorded.')
    if output.get('qualification_state')=='awaiting_telemetry':return 'The output was accepted locally; Langfuse verification is pending.'
    if isinstance(output,dict) and 'status' in output:
        return {'awaiting_provider':'The work is waiting for its executor.','awaiting_evaluation':'The output is ready for quality checks.',
                'awaiting_review':'The output passed quality checks and needs independent review.','completed':'The output was accepted.',
                'failed':'The run needs revision.','cancelled':'The run was cancelled.','awaiting_reconciliation':'The provider result needs checking before any further action.'}.get(output['status'],'The company operation was recorded.')
    if isinstance(output,dict) and 'release_digest' in output:return 'The workflow version was recorded. Review its acceptance state before production use.'
    if isinstance(output,dict) and 'action_digest' in output:return 'The exact-action decision was recorded. It has not been dispatched.'
    if command=='layout':return 'Company layout is valid.' if output['ok'] else 'Company layout needs attention: '+str(len(output['violations']))+' issues.'
    if command=='profile':
        from .home import CompanyProfile
        return 'Company facts are recorded.' if not output['missing_fields'] else 'Company profile needs owner input: '+', '.join(CompanyProfile.SECTIONS[key].lower() for key in output['missing_fields'])+'.'
    if command=='memory':
        if 'counts' in output:return str(output['counts']['owner'])+' owner preferences, '+str(output['counts']['workflow'])+' workflow lessons and '+str(output['counts']['strategy'])+' strategic directions are recorded. Detailed claims retain their evidence references.'
        return 'The explicit memory change was recorded.'
    if command in {'import','migrate'}:return 'The reviewable plan is ready.' if 'plan' in output else 'The reviewed operation completed.'
    return 'The company operation completed.'


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    os.environ.setdefault('PYTHONUTF8','1')
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv in (['--version'],['-V']):print('spielos '+VERSION);return 0
    # Clear retirement is preferable to accidentally initializing the old loop.
    command_args=argv[2:] if argv and argv[0]=='--db' else argv[1:] if argv and argv[0].startswith('--db=') else argv
    if command_args and command_args[0] in RETIRED:
        print('Autonomous Goal pursuit and the product runner are retired. Use a bounded workflow or read preserved history.',file=sys.stderr);return 1
    if argv in (['--version'],['-V']):print(VERSION);return 0
    if not argv:argv=['status']
    args=build_parser().parse_args(argv)
    try:
        if args.command=='report':
            from .reporting import ensure_server,serve,snapshot
            if args.serve:return serve(args.home,args.port if args.port is not None else 8775)
            output=snapshot(args.home) if args.snapshot else ensure_server(args.home,open_browser=not args.no_open,port=args.port)
            print(json.dumps(output,indent=2,ensure_ascii=False) if args.json else ('Company dashboard: '+output['url'] if not args.snapshot else json.dumps(output,ensure_ascii=False)))
            return 0
        if args.command=='activity':
            from .observability.sessions import dispatch_activity
            output=dispatch_activity(runtime_for(args,readonly=args.activity_command=='show'),args.activity_command,
                                     read_json(args.payload) if args.payload else {},session_id=args.session)
            print(json.dumps(output,indent=2,ensure_ascii=False) if args.json else owner_text(args.command,output))
            return 0
        if args.command=='evaluation':
            from .evals.harness import dispatch_evaluation
            output=dispatch_evaluation(runtime_for(args),args.evaluation_command,
                read_json(args.payload) if args.payload else ({'session_id':args.session} if args.evaluation_command=='pending' and args.session else {}),subject=args.subject)
            print(json.dumps(output,indent=2,ensure_ascii=False) if args.json else owner_text(args.command,output))
            return 0
        if args.command=='mcp':
            from .mcp import serve
            return serve()
        if args.command=='init':
            from .runtime.onboard import run_init
            return run_init(dir=args.dir,force=args.force,assume_yes=args.yes,as_json=args.json)
        if args.command=='update':
            from .runtime.onboard import run_update
            return run_update(dir=args.dir,as_json=args.json,keep_stale=args.keep_stale)
        if args.command=='migrate':
            from .home import CompanyHome,fingerprint
            home=CompanyHome(args.dir)
            if args.plan:
                if not args.digest:raise ValueError('Applying migration requires the reviewed plan digest')
                output=home.apply_migration(read_json(args.plan),expected_digest=args.digest)
            else:
                if args.digest:raise ValueError('Choose the reviewed plan when applying migration')
                plan=home.migration_plan();output={'plan':plan,'digest':fingerprint(plan)}
        elif args.command=='history':output=legacy_history(args.home,kind=args.kind,limit=args.limit)
        elif args.command in {'status','overview','context','catalog','departments','layout'}:
            from .runtime.boundary import restricted_repository
            home=Path(args.home or PROJECT_ROOT).expanduser().resolve()
            boundary=restricted_repository(home)
            if boundary:
                print('This is a '+boundary[1]+' repository. Select a separate installed company home.');return 0
            if args.command=='layout':
                from .layout import audit
                output=audit(home)
            else:
                from .mcp import CompanySession
                session=CompanySession();selected=session.select(str(home));output=session.inspect(selected['company_id'],prompt=getattr(args,'prompt',''),workflow_id=getattr(args,'workflow',None),token_budget=getattr(args,'token_budget',6000))
                if args.command=='departments':output={'departments':[path.name for path in (home/'company/departments').iterdir() if path.is_dir()]}
        elif args.command in {'import','export'}:
            from .portability import PortablePackages
            home=validate_home_destination(args.home);authority,principal=authority_for(home);packages=PortablePackages(home,principal)
            if args.command=='export':output=packages.export_workflow(args.workflow_id,args.out,package_id=args.package_id,version=args.version)
            elif args.plan:
                if not args.digest:raise ValueError('Import requires the reviewed plan digest')
                output=packages.install(read_json(args.plan),expected_digest=args.digest)
            else:
                if not args.folder:raise ValueError('Choose a package folder to preview')
                output=packages.preview(args.folder)
        elif args.command=='brand':
            from .branding import BrandRegistry
            home=validate_home_destination(args.home);authority,principal=authority_for(home);registry=BrandRegistry(home,principal)
            if args.brand_command=='candidate':output=registry.candidate(version=args.version,files=read_json(args.files))
            elif args.brand_command=='release':output={'brand_release':registry.release(read_json(args.candidate),inspection=read_json(args.inspection))}
            else:output=registry.resolve(args.release_digest)
        elif args.command=='profile':
            from .home import CompanyProfile
            home=validate_home_destination(args.home);authority,principal=authority_for(home);profile=CompanyProfile(home,principal)
            output=profile.read() if args.profile_command=='show' else profile.update(read_json(args.fields),source=args.source,runtime=runtime_for(args))
        elif args.command=='memory':
            database=Path(args.db) if args.db else Path(args.home)/'.spielos/state/workflows.sqlite'
            if args.memory_command=='summary' and not database.is_file():
                authority_for(validate_home_destination(args.home));output={'claims':[],'counts':{'owner':0,'workflow':0,'strategy':0}}
            else:
                from .context.workflow import WorkflowMemory
                runtime=runtime_for(args,readonly=args.memory_command=='summary');memory=WorkflowMemory(runtime)
                if args.memory_command=='summary':output=memory.summary(args.workflow)
                elif args.memory_command=='add':output=memory.add(scope=args.scope,claim=args.claim,workflow_id=args.workflow,evidence_runs=args.run,source=args.source)
                elif args.memory_command=='classify':output=memory.classify(args.memory_id,topics=args.topic,category=args.category,critical=args.critical,reason=args.reason)
                else:memory.retire(args.memory_id,reason=args.reason);output={'retired':True}
        elif args.command=='improvement':
            from .improvements import Improvements
            development=Improvements(runtime_for(args,readonly=args.improvement_command=='show'));verb=args.improvement_command
            if verb=='create':output=development.create(read_json(args.brief))
            elif verb=='show':output=development.get(args.improvement_id)
            elif verb=='observe':output=development.observe(args.improvement_id,read_json(args.observation))
            elif verb=='agree-architecture':output=development.agree_architecture(args.improvement_id,read_json(args.architecture))
            elif verb=='attach-candidate':output=development.attach_candidate(args.improvement_id,args.release,changed_files=read_json(args.changed_files))
            elif verb=='attach-change':output=development.attach_change(args.improvement_id,root=args.root,changed_files=read_json(args.changed_files),evidence_files=read_json(args.evidence_files))
            elif verb=='reconcile':output=development.reconcile(args.improvement_id,evidence_files=read_json(args.evidence_files),reason=args.reason)
            elif verb=='revise':output=development.revise(args.improvement_id,reason=args.reason)
            else:output=development.decide(args.improvement_id,decision=args.decision,reason=args.reason,candidate_runs=read_json(args.runs) if args.runs else None)
        else:
            from .workflows.runs import LocalFileAdapter
            runtime=runtime_for(args,readonly=args.workflow_command in {'show','scorecard','experiment-show'});verb=args.workflow_command
            specification=(read_json(args.manifest) if verb=='candidate' else runtime.manifest(args.release) if verb in {'run','experiment'} else
                runtime.manifest(runtime.get(args.run_id)['release_digest']) if verb in {'reconcile','cancel'} else None)
            if verb=='candidate' and set(specification.get('evaluation',{}))=={'rubric','cases'}:
                from .commands.workflows import read_package
                specification=read_package(runtime.home,args.manifest)
            if specification and specification['execution']['provider']=='local':runtime.adapters['local']=LocalFileAdapter(runtime.home,specification)
            if verb=='calibrate-judge':
                from .evals.contracts import record_judge_calibration
                output=record_judge_calibration(runtime,judge=read_json(args.judge),ratings=read_json(args.ratings),maximum_disagreement=args.maximum_disagreement,reason=args.reason)
            elif verb=='experiment':
                from .observability.experiments import run_experiment
                output=run_experiment(runtime,args.release,name=args.name,request_key=args.request_key)
            elif verb=='experiment-show':
                from .observability.experiments import get_experiment
                output=get_experiment(runtime,args.experiment_id)
            elif verb=='measure':
                from .observability.read_model import record_outcome
                output=record_outcome(runtime,read_json(args.measurement))
            elif verb=='scorecard':
                from .observability.read_model import workflow_scorecard
                output=workflow_scorecard(runtime)
            elif verb=='configure-telemetry':
                from .operations import configure_telemetry
                output=configure_telemetry(runtime,read_json(args.config))
            elif verb=='candidate':output={'release_digest':runtime.candidate(specification)}
            elif verb=='release':output={'release_digest':runtime.release(args.release,candidate_runs=read_json(args.runs),reviewer=args.reviewer)}
            elif verb=='run':output=runtime.run(args.release,read_json(args.inputs),request_key=args.request_key,candidate_case=args.candidate_case)
            elif verb=='show':output=runtime.get(args.run_id)
            elif verb=='claim':output=runtime.claim(args.run_id)
            elif verb=='deliver':output=runtime.deliver(args.run_id,read_json(args.output),token=args.token)
            elif verb=='reconcile':output=runtime.reconcile(args.run_id)
            elif verb=='cancel':output=runtime.cancel(args.run_id)
            elif verb=='evaluate':output=runtime.evaluate_run(args.run_id,case_id=args.case,verdicts=read_json(args.verdicts) if args.verdicts else None,evaluator=args.evaluator)
            elif verb=='review':output=runtime.review(args.run_id,reviewer=args.reviewer,decision=args.decision)
            elif verb=='approve-action':output={'action_digest':runtime.approve_action(args.run_id,read_json(args.action),reviewer=args.reviewer,decision=args.decision)}
            elif verb=='wake':output=runtime.wake(run_id=args.wake_run)
            else:
                from .observability.langfuse import LangfuseClient
                config_path=runtime.home/'.spielos/telemetry.json'
                client=LangfuseClient.from_configuration(runtime.home,read_json(config_path)) if config_path.is_file() else LangfuseClient.from_environment()
                output={'events':runtime.export_pending(client,limit=args.limit,max_attempts=args.max_attempts)}
            if verb not in {'show','scorecard','experiment-show','export','wake'} and (runtime.home/'.spielos/telemetry.json').is_file():output['host_wake']=runtime.wake()
        print(json.dumps(output,indent=2,ensure_ascii=False,default=str) if args.json else owner_text(args.command,output))
        return 0
    except (ValueError,KeyError,PermissionError,RuntimeError,FileExistsError,FileNotFoundError,sqlite3.Error) as error:
        print(str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
