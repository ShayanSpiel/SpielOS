"""Thin local stdio MCP interface over the same bounded workflow runtime.

Protocol: MCP 2025-06-18, newline-delimited UTF-8 JSON-RPC. No HTTP listener,
no hidden home installation and no company data in the plugin cache.
"""
from __future__ import annotations
import json,os,sys,sqlite3
from pathlib import Path
from .home import CompanyHome
from .security import CompanyAuthority
from .workflows.runs import WorkflowRuntime,LocalFileAdapter,validate
from .runtime.config import VERSION


def tool(name,description,properties,required,*,readonly=False):
    return {'name':name,'description':description,'inputSchema':{'type':'object','properties':properties,
            'required':required,'additionalProperties':False},
            'annotations':{'readOnlyHint':readonly,'destructiveHint':False,'openWorldHint':False}}

STRING={'type':'string'}
OBJECT={'type':'object','additionalProperties':True}
TOOLS=[
 tool('select_company','Select an existing installed company by its absolute folder. Never initializes one.',{'path':STRING},['path'],readonly=True),
 tool('inspect_company','Read the selected company, scoped memory, draft/released inventory and all pending work.',{'company_id':STRING,'prompt':STRING,'workflow_id':STRING},['company_id'],readonly=True),
 tool('build_workflow','Create a bounded improvement record or pin/release a workflow candidate using actual case runs.',
      {'company_id':STRING,'action':{'type':'string','enum':['create_improvement','observe','agree_architecture','attach_candidate','attach_change','reconcile_improvement','revise_improvement','configure_telemetry','classify_memory','add_memory','retire_memory','decide_improvement','candidate','release','brand-candidate','activity-start','activity-record','activity-context','activity-artifact','activity-show','activity-export','activity-import-ratings','evaluation-template','evaluation-register','evaluation-show','evaluation-event','evaluation-compare','evaluation-pending','evaluation-judge']},'payload':OBJECT},['company_id','action','payload']),
 tool('run_workflow','Run an accepted workflow, test a pinned candidate case, claim/deliver host work, or reconcile/cancel a named run.',
      {'company_id':STRING,'action':{'type':'string','enum':['run','claim','deliver','reconcile','cancel','show','wake']},'payload':OBJECT},['company_id','action','payload']),
 tool('review_output','Evaluate actual output or record an independent accept/reject decision. Quality never grants publishing authority.',
      {'company_id':STRING,'action':{'type':'string','enum':['evaluate','review','calibrate-judge','brand-release']},'payload':OBJECT},['company_id','action','payload']),
 tool('approve_action','Record the owner-authorized decision on one exact action, destination, content digest and scope. Does not dispatch it.',
      {'company_id':STRING,'run_id':STRING,'action':OBJECT,'decision':{'type':'string','enum':['approve','reject']}},['company_id','run_id','action','decision']),
]


class CompanySession:
    def __init__(self):self.home=None;self.company_id=None

    def principal(self):
        authority=CompanyAuthority(self.home)
        token=os.environ.get('SPIELOS_PRINCIPAL_TOKEN')
        return authority.authenticate(token) if token else authority.local_owner()

    def select(self,path):
        if not Path(path).is_absolute():raise ValueError('Select an absolute company folder')
        home=CompanyHome(path);home.require_destination()
        if not home.lean:raise ValueError('Select an installed lean company; installation and migration are separate explicit operations')
        authority=CompanyAuthority(home.root)
        token=os.environ.get('SPIELOS_PRINCIPAL_TOKEN')
        principal=authority.authenticate(token) if token else authority.local_owner()
        authority.authorize(principal,'read')
        self.home=home.root;self.company_id=authority.company_id
        return {'company_id':self.company_id,'path':str(self.home),'status':'selected','initialized':False}

    def runtime(self,company_id,*,readonly=False):
        if self.home is None or company_id!=self.company_id:raise PermissionError('Select this company explicitly before using its tools')
        authority=CompanyAuthority(self.home)
        if authority.company_id!=self.company_id:raise PermissionError('Company identity changed; select it again')
        return WorkflowRuntime(self.home/'.spielos/state/workflows.sqlite',home=self.home,
                               principal=self.principal(),readonly=readonly)

    @staticmethod
    def local_adapter(runtime,manifest):
        if manifest['execution']['provider']=='local':runtime.adapters['local']=LocalFileAdapter(runtime.home,manifest)

    def inspect(self,company_id,*,prompt='',workflow_id=None,token_budget=6000):
        if self.home is None or company_id!=self.company_id:raise PermissionError('Select this company explicitly')
        CompanyAuthority(self.home).authorize(self.principal(),'read')
        company=CompanyHome(self.home);inventory=[]
        # Inventory reads declarations as data; it never imports owner Python.
        for path in sorted(company.owner_path('workflows').glob('*/workflow.json')):
            if path.is_symlink() or not path.resolve().is_relative_to(company.content):continue
            try:
                value=json.loads(path.read_text())
                inventory.append({'id':value['id'],'purpose':value.get('purpose'),'version':value.get('version')})
            except (ValueError,KeyError):inventory.append({'path':str(path.relative_to(company.content)),'status':'needs_repair'})
        database=self.home/'.spielos/state/workflows.sqlite'
        if database.is_file():
            from .context.workflow import owner_context
            from .observability.read_model import workflow_scorecard
            runtime=self.runtime(company_id,readonly=True)
            context=owner_context(runtime,prompt=prompt,workflow_id=workflow_id,token_budget=token_budget);scorecard=workflow_scorecard(runtime)
            with runtime.connect() as connection:
                released={row[0] for row in connection.execute('SELECT r.workflow_id FROM workflow_releases r JOIN workflow_release_acceptance a ON a.digest=r.digest')}
            for row in inventory:row['readiness']='released' if row.get('id') in released else 'draft; not qualified for production'
        else:
            context={'text':'Company work\nNo workflows have been run.','pending':[],'counts':{}};scorecard=None
        from .home import CompanyProfile
        return {'company_id':self.company_id,'profile':(company.content/'profile.md').read_text(),
                'profile_contract':CompanyProfile(self.home,self.principal()).read(),
                'workflows':inventory,'context':context,'scorecard':scorecard,'activepieces':'inactive','report':{'command':'report --home '+str(self.home),'url':__import__('company.reporting',fromlist=['display_url']).display_url(self.home),'scope':'Live read-only local dashboard; company-specific extensions are explicit'}}

    def call(self,name,arguments):
        result=self._call(name,arguments)
        if name not in {'select_company','inspect_company'} and self.home and (self.home/'.spielos/telemetry.json').is_file():
            result['host_wake']=self.runtime(self.company_id).wake()
        return result

    def _call(self,name,arguments):
        description=next((row for row in TOOLS if row['name']==name),None)
        if description is None:raise ValueError('Unknown SpielOS tool')
        validate(description['inputSchema'],arguments,'arguments')
        if name=='select_company':return self.select(arguments['path'])
        company_id=arguments['company_id']
        if name=='inspect_company':return self.inspect(company_id,prompt=arguments.get('prompt',''),workflow_id=arguments.get('workflow_id'))
        runtime=self.runtime(company_id)
        payload=arguments.get('payload',{})
        runtime.activity_session_id=payload.get('session_id') or os.environ.get('SPIELOS_SESSION_ID') or getattr(runtime,'activity_session_id',None)
        if name=='build_workflow':
            action=arguments['action']
            if action.startswith('activity-'):
                from .observability.sessions import dispatch_activity
                return dispatch_activity(runtime,action.removeprefix('activity-'),payload)
            if action.startswith('evaluation-'):
                from .evals.harness import dispatch_evaluation
                return dispatch_evaluation(runtime,'evaluate-event' if action=='evaluation-event' else action.removeprefix('evaluation-'),payload)
            if action=='configure_telemetry':
                from .operations import configure_telemetry
                return configure_telemetry(runtime,payload['config'])
            if action in {'classify_memory','add_memory','retire_memory'}:
                from .context.workflow import WorkflowMemory
                memory=WorkflowMemory(runtime)
                if action=='classify_memory':return memory.classify(**payload)
                if action=='add_memory':return memory.add(**payload)
                memory.retire(**payload);return {'retired':True}
            if action=='brand-candidate':
                from .branding import BrandRegistry
                return BrandRegistry(self.home,runtime.principal).candidate(version=payload['version'],files=payload['files'])
            if action=='candidate':
                from .commands.workflows import read_package
                manifest=read_package(self.home,CompanyHome(self.home).content/'workflows'/payload['workflow_id']/'workflow.json')
                self.local_adapter(runtime,manifest)
                return {'release_digest':runtime.candidate(manifest)}
            if action=='release':return {'release_digest':runtime.release(payload['release_digest'],candidate_runs=payload['candidate_runs'])}
            from .improvements import Improvements
            development=Improvements(runtime)
            if action=='create_improvement':return development.create(payload['brief'])
            if action=='observe':return development.observe(payload['improvement_id'],payload['observation'])
            if action=='agree_architecture':return development.agree_architecture(payload['improvement_id'],payload['architecture'])
            if action=='attach_candidate':return development.attach_candidate(payload['improvement_id'],payload['release_digest'],changed_files=payload['changed_files'])
            if action=='attach_change':return development.attach_change(payload['improvement_id'],root=payload['root'],changed_files=payload['changed_files'],evidence_files=payload['evidence_files'])
            if action=='revise_improvement':return development.revise(payload['improvement_id'],reason=payload['reason'])
            if action=='reconcile_improvement':return development.reconcile(payload['improvement_id'],evidence_files=payload['evidence_files'],reason=payload['reason'])
            return development.decide(payload['improvement_id'],decision=payload['decision'],reason=payload['reason'],candidate_runs=payload.get('candidate_runs'))
        if name=='run_workflow':
            action=arguments['action']
            if action=='run':
                manifest=runtime.manifest(payload['release_digest']);self.local_adapter(runtime,manifest)
                return runtime.run(payload['release_digest'],payload['inputs'],request_key=payload['request_key'],candidate_case=payload.get('candidate_case'))
            if action=='wake':
                run_id=payload.get('run_id')
                if run_id:self.local_adapter(runtime,runtime.manifest(runtime.get(run_id)['release_digest']))
                return runtime.wake(run_id=run_id)
            run_id=payload['run_id']
            if action=='show':return runtime.get(run_id)
            if action in {'reconcile','cancel'}:self.local_adapter(runtime,runtime.manifest(runtime.get(run_id)['release_digest']))
            if action=='deliver':return runtime.deliver(run_id,payload['output'],token=payload['token'])
            return getattr(runtime,action)(run_id)
        if name=='review_output':
            if arguments['action']=='brand-release':
                from .branding import BrandRegistry
                return {'brand_release':BrandRegistry(self.home,runtime.principal).release(payload['candidate'],inspection=payload['inspection'])}
            if arguments['action']=='calibrate-judge':
                from .evals.contracts import record_judge_calibration
                return record_judge_calibration(runtime,judge=payload['judge'],ratings=payload['ratings'],reason=payload['reason'],maximum_disagreement=payload.get('maximum_disagreement',0.2))
            if arguments['action']=='evaluate':return runtime.evaluate_run(payload['run_id'],case_id=payload.get('case_id'),verdicts=payload.get('verdicts'))
            return runtime.review(payload['run_id'],decision=payload['decision'])
        return {'action_digest':runtime.approve_action(arguments['run_id'],arguments['action'],decision=arguments['decision'])}


def serve(incoming=None,outgoing=None):
    incoming=incoming or sys.stdin;outgoing=outgoing or sys.stdout
    session=CompanySession();initialized=False
    for line in incoming:
        request=None
        try:
            if len(line.encode())>2*1024*1024:raise ValueError('MCP request exceeds the bounded message size')
            request=json.loads(line)
            if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':raise ValueError('Invalid JSON-RPC request')
            method=request.get('method');params=request.get('params',{})
            if 'id' not in request:continue
            if method=='initialize':
                initialized=True
                result={'protocolVersion':'2025-06-18','capabilities':{'tools':{'listChanged':False}},
                        'serverInfo':{'name':'spielos','version':VERSION},
                        'instructions':'Select an existing company explicitly. Never create one silently. Use four owner concepts: Company, Workflow, Run, Improvement. Exact external actions require separate approval.'}
            elif method=='ping':result={}
            elif not initialized:raise ValueError('Initialize MCP before calling tools')
            elif method=='tools/list':result={'tools':TOOLS}
            elif method=='tools/call':
                try:
                    value=session.call(params['name'],params.get('arguments',{}))
                    summary=('Company folder selected.' if params['name']=='select_company' else
                             value['context']['text'].split('\nMachine reference:')[0] if params['name']=='inspect_company' else
                             'The requested company operation was recorded. Review the returned state before describing its outcome.')
                    result={'content':[{'type':'text','text':summary}],'structuredContent':value,'isError':False}
                except (KeyError,ValueError,PermissionError,RuntimeError,FileNotFoundError) as error:
                    result={'content':[{'type':'text','text':str(error)}],'isError':True}
                except (OSError,sqlite3.Error):
                    result={'content':[{'type':'text','text':'Company storage is unavailable; inspect the selected local home before retrying.'}],'isError':True}
            else:
                outgoing.write(json.dumps({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Method not found'}})+'\n');outgoing.flush();continue
            response={'jsonrpc':'2.0','id':request['id'],'result':result}
        except (ValueError,TypeError,KeyError) as error:
            response={'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,
                      'error':{'code':-32700 if request is None else -32602,'message':str(error)}}
        outgoing.write(json.dumps(response,separators=(',',':'),allow_nan=False)+'\n');outgoing.flush()
    return 0
