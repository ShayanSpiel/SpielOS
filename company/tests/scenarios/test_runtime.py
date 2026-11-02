"""A finance lead requests bounded reports and recovers work through real restarts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import json,sqlite3,tempfile,threading,time,unittest
from company.home import CompanyHome
from company.security import CompanyAuthority
from company.workflows.runs import WorkflowRuntime,LocalAdapter,digest
from .test_home import scenario


def report(inputs):
    return {'title':inputs['title'],'total':sum(inputs['sales']),'rows':len(inputs['sales'])}


def slow_report(inputs):
    time.sleep(4)
    return report(inputs)


def specification(provider='local'):
    input_schema={'type':'object','properties':{'title':{'type':'string'},'sales':{'type':'array','items':{'type':'number'}}},'required':['title','sales']}
    output_schema={'type':'object','properties':{'title':{'type':'string'},'total':{'type':'number'},'rows':{'type':'integer'}},'required':['title','total','rows']}
    rules=[('named','nonempty','/title',{}),('total','sum_input','/total',{'input_path':'/sales'}),
           ('rows','length_input','/rows',{'input_path':'/sales'}),('positive','range','/total',{'min':0})]
    criteria=[{'id':name,'source':'report brief v1','anchors':{'pass':'The report obeys the '+name+' accounting rule','fail':'The report violates the '+name+' accounting rule'},
               'question':'Does the report satisfy the '+name+' accounting rule?', 'dimension':'output', 'severity':'block','evaluator':'check','check':{'kind':kind,'path':path,**options}} for name,kind,path,options in rules]
    cases=[]
    for name,split,values,expected in [('example','representative',[10,20],'pass'),('unseen','held_out',[3,8,1],'pass'),('refund','negative',[-5],'fail')]:
        inputs={'title':name,'sales':values}
        cases.append({'id':name,'split':split,'input':inputs,'reference':report(inputs),'expected':expected,'intent':'Check accounting accuracy for '+name,**({'failure_criteria':['positive']} if expected=='fail' else {})})
    return {'id':'sales-report','version':'1','purpose':'Give the finance lead an accurate bounded sales summary',
            'owner':'finance-lead','input_schema':input_schema,'output_schema':output_schema,
            'dependencies':{},'context_versions':{},
            'execution':{'provider':provider,'binding':'agent:finance-reporter' if provider=='host' else 'sales-report-v1','timeout_seconds':5,'retry_budget':0,'effect_permissions':[]},
            'evaluation':{'standard':'spielos-evaluation/2','subject':'workflow','objective':'Report the exact sum, row count and requested title; reject negative totals','version':'1','criteria':criteria,'cases':cases}}


def create_release(runtime,spec=None,reviewer_runtime=None):
    from company.tests.test_bounded_workflow_runs import prepare_fixture_telemetry,verify_fixture_telemetry
    prepare_fixture_telemetry(runtime)
    spec=spec or specification()
    release=runtime.candidate(spec);runs={}
    from company.tests.test_bounded_workflow_runs import attach_development
    attach_development(runtime,release)
    for case in spec['evaluation']['cases']:
        run=runtime.run(release,case['input'],request_key=release+':'+case['id'],candidate_case=case['id'])
        if spec['execution']['provider']=='host':
            if runtime.authority:run=runtime.claim(run['id'])
            runtime.deliver(run['id'],report(case['input']),token=run['token'])
        runtime.evaluate_run(run['id'])
        runs[case['id']]=run['id']
    verify_fixture_telemetry(runtime)
    (reviewer_runtime or runtime).release(release,candidate_runs=runs)
    return release,runs


class WorkspaceJourney(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        CompanyHome(self.root).initialize_content()
        self.authority=CompanyAuthority(self.root);self.authority.bootstrap()
        self.owner=self.authority.local_owner()
        from company.agents.loader import AgentCatalog
        catalog=AgentCatalog(self.root,self.owner)
        catalog.create_skill(name='sales-summary',description='Summarize supplied sales rows with explicit accounting boundaries.',
            instructions='Sum the supplied sales rows and report the row count. Preserve the requested title. Mark refunds separately; negative totals fail this draft workflow. Do not infer revenue impact or publish the result.')
        catalog.create_agent({'id':'finance-reporter','description':'Prepare bounded sales reports from the supplied rows.',
            'skill_ids':['sales-summary'],'permissions':['read_company','write_artifacts'],'produces':['sales-report']})
        reviewer_token=self.authority.issue(self.owner,subject='quality-reviewer',roles=['reviewer'])
        self.reviewer=self.authority.authenticate(reviewer_token)
        self.database=self.root/'.spielos/state/workflows.sqlite'
        self.adapter=LocalAdapter(report)
        self.runtime=self.open(self.owner)
        self.review_runtime=self.open(self.reviewer)

    def open(self,principal):
        return WorkflowRuntime(self.database,home=self.root,principal=principal,adapters={'local':self.adapter})


class ReportRuntimeJourneys(WorkspaceJourney):
    @scenario('runtime.new_inputs_execute_and_evaluate','runtime.no_goal_or_daemon_needed','evaluation.technical_quality_not_business_impact')
    def test_finance_lead_gets_a_new_report_with_real_checks_and_independent_review(self):
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        run=self.runtime.run(release,{'title':'Friday receipts','sales':[120.25,30.5,8.25]},request_key='friday')
        self.assertEqual(run['output'],{'title':'Friday receipts','total':159.0,'rows':3})
        checked=self.runtime.evaluate_run(run['id'])
        self.assertEqual(checked['evaluation']['state'],'pass')
        self.assertEqual(checked['evaluation']['business_outcome'],'unmeasured')
        self.assertEqual(self.review_runtime.review(run['id'],decision='accept')['status'],'completed')
        with self.runtime.connect() as connection:
            self.assertFalse(connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'core_%'").fetchall())

    @scenario('creation.real_candidate_execution_provenance','creation.negative_and_held_out_examples')
    def test_outputs_submitted_by_the_builder_cannot_replace_actual_acceptance_runs(self):
        from company.tests.test_bounded_workflow_runs import prepare_fixture_telemetry,verify_fixture_telemetry
        prepare_fixture_telemetry(self.runtime)
        release=self.runtime.candidate(specification())
        with self.assertRaises(ValueError):self.runtime.run(release,{'title':'Early production','sales':[1]},request_key='early')
        with self.assertRaises(ValueError):
            self.review_runtime.release(release,candidate_runs={'example':'invented','unseen':'invented2','refund':'invented3'})
        runs={}
        for case in specification()['evaluation']['cases']:
            run=self.runtime.run(release,case['input'],request_key=case['id'],candidate_case=case['id'])
            self.runtime.evaluate_run(run['id']);runs[case['id']]=run['id']
        from company.tests.test_bounded_workflow_runs import attach_development
        attach_development(self.runtime,release)
        verify_fixture_telemetry(self.runtime)
        self.review_runtime.release(release,candidate_runs=runs)
        with self.runtime.connect() as connection:
            review=json.loads(connection.execute('SELECT review_json FROM workflow_release_acceptance').fetchone()[0])
        self.assertEqual({item['case_id'] for item in review['reports']},{'example','unseen','refund'})
        self.assertTrue(review['independent'])

    @scenario('runtime.duplicate_request_one_dispatch')
    def test_two_requests_for_the_same_report_dispatch_once(self):
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        before=self.adapter.dispatch_count
        def request(_):return self.open(self.owner).run(release,{'title':'Same receipts','sales':[5,6]},request_key='one-shared-request')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(request,range(2)))
        self.assertEqual(len({row['id'] for row in results}),1)
        self.assertEqual(self.adapter.dispatch_count-before,1)
        with self.assertRaises(ValueError):self.runtime.run(release,{'title':'Changed','sales':[8]},request_key='one-shared-request')

    @scenario('runtime.timeout_enforced')
    def test_slow_pure_code_is_stopped_at_its_deadline(self):
        self.adapter=LocalAdapter(slow_report);runtime=self.open(self.owner)
        spec=specification();spec['execution']['timeout_seconds']=1
        release=runtime.candidate(spec)
        started=time.monotonic()
        run=runtime.run(release,spec['evaluation']['cases'][0]['input'],request_key='slow',candidate_case='example')
        self.assertLess(time.monotonic()-started,2.5)
        self.assertEqual(run['status'],'failed')
        self.assertIn('deadline',run['error'])
        self.assertIsNone(run['output'])

    @scenario('runtime.active_lease_not_preempted')
    def test_a_status_wake_does_not_steal_a_provider_that_is_still_starting(self):
        entered=threading.Event();finish=threading.Event()
        class Waiting:
            revision='synthetic-wait-v1'
            def start(self,**kwargs):
                entered.set();finish.wait(3)
                return {'status':'completed','output':report(kwargs['inputs'])}
            def inspect(self,**kwargs):raise AssertionError('Live dispatch was preempted')
        runtime=WorkflowRuntime(self.database,home=self.root,principal=self.owner,adapters={'waiting':Waiting()})
        spec=specification('waiting');release=runtime.candidate(spec)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(runtime.run,release,spec['evaluation']['cases'][0]['input'],request_key='pending',candidate_case='example')
            self.assertTrue(entered.wait(2))
            with runtime.connect() as connection:run_id=connection.execute("SELECT id FROM workflow_invocations WHERE request_key='pending'").fetchone()[0]
            initial=runtime.get(run_id);reconciled=runtime.reconcile(run_id)
            self.assertEqual(initial['token'],reconciled['token'])
            self.assertEqual(initial['generation'],reconciled['generation'])
            finish.set();self.assertEqual(future.result(timeout=3)['status'],'awaiting_evaluation')

    @scenario('runtime.unknown_execution_not_blindly_replayed')
    def test_response_loss_reconciles_the_same_request_without_starting_again(self):
        class Lost:
            revision='synthetic-loss-v1'
            def __init__(self):self.starts=0;self.inspected=[]
            def start(self,**kwargs):self.starts+=1;raise OSError('response lost')
            def inspect(self,**kwargs):self.inspected.append(kwargs['request_id']);return {'status':'unknown'}
        adapter=Lost();runtime=WorkflowRuntime(self.database,home=self.root,principal=self.owner,adapters={'lost':adapter})
        spec=specification('lost');release=runtime.candidate(spec)
        run=runtime.run(release,spec['evaluation']['cases'][0]['input'],request_key='lost',candidate_case='example')
        restarted=WorkflowRuntime(self.database,home=self.root,principal=self.owner,adapters={'lost':adapter})
        self.assertEqual(restarted.reconcile(run['id'])['status'],'awaiting_reconciliation')
        self.assertEqual(adapter.starts,1);self.assertEqual(adapter.inspected,[run['id']])

    @scenario('runtime.cancel_and_restart_recovery','runtime.stale_completion_fenced')
    def test_cancelled_host_work_stays_cancelled_after_restart_and_rejects_late_delivery(self):
        spec=specification('host');release=self.runtime.candidate(spec)
        case=spec['evaluation']['cases'][0]
        run=self.runtime.run(release,case['input'],request_key='host-cancel',candidate_case=case['id'])
        run=self.runtime.claim(run['id'])
        self.assertEqual(self.runtime.cancel(run['id'])['status'],'cancelled')
        restarted=self.open(self.owner)
        self.assertEqual(restarted.get(run['id'])['status'],'cancelled')
        with self.assertRaises(RuntimeError):restarted.deliver(run['id'],report(case['input']),token=run['token'])
        self.assertEqual(restarted.get(run['id'])['status'],'cancelled')

    @scenario('evaluation.independent_review_and_self_judging_label','security.immutable_actor_audit')
    def test_builder_cannot_self_accept_and_the_actor_history_cannot_be_rewritten(self):
        release,runs=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        with self.assertRaises(PermissionError):self.runtime.release(release,candidate_runs=runs)
        run=self.runtime.run(release,{'title':'Review me','sales':[4,9]},request_key='review')
        self.runtime.evaluate_run(run['id'])
        with self.assertRaises(PermissionError):self.runtime.review(run['id'],decision='accept')
        with self.assertRaises(PermissionError):self.runtime.review(run['id'],reviewer='quality-reviewer',decision='accept')
        self.review_runtime.review(run['id'],decision='accept')
        with self.runtime.connect() as connection:
            self.assertGreater(connection.execute('SELECT COUNT(*) FROM workflow_actor_audit').fetchone()[0],0)
            with self.assertRaises(sqlite3.IntegrityError):connection.execute('DELETE FROM workflow_actor_audit')

    @scenario('runtime.sequential_input_output_mapping')
    def test_two_released_deterministic_steps_map_prior_outputs_without_an_extra_engine(self):
        child=specification();child['id']='sales-calculation'
        child['evaluation']['review_policy']='release_only'
        child['evaluation']['criteria']=[row for row in child['evaluation']['criteria'] if row['id']!='positive']
        negative=child['evaluation']['cases'][-1]
        negative['failure_criteria']=['named']
        negative['input']={'title':'','sales':[1]};negative['reference']=report(negative['input'])
        child_release,_=create_release(self.runtime,child,reviewer_runtime=self.review_runtime)
        parent=specification('sequential');parent['id']='weekly-report-sequence'
        parent['execution']['binding']='sequence-v1'
        parent['execution']['steps']=[{'release':child_release,'inputs':{'title':{'input':'/title'},'sales':{'input':'/sales'}}},
            {'release':child_release,'inputs':{'title':{'step':0,'path':'/title'},'sales':{'input':'/sales'}}}]
        parent['execution']['output']={'title':{'step':1,'path':'/title'},'total':{'step':1,'path':'/total'},'rows':{'step':0,'path':'/rows'}}
        release,_=create_release(self.runtime,parent,reviewer_runtime=self.review_runtime)
        run=self.runtime.run(release,{'title':'Two-step report','sales':[5,7,3]},request_key='two-step')
        self.assertEqual(run['output'],{'title':'Two-step report','total':15,'rows':3})
        self.assertEqual(self.runtime.evaluate_run(run['id'])['evaluation']['state'],'pass')
        repeated=self.runtime.run(release,{'title':'Two-step report','sales':[5,7,3]},request_key='two-step')
        self.assertEqual(repeated['id'],run['id'])
        with self.runtime.connect() as connection:
            children=connection.execute('SELECT COUNT(*) FROM workflow_invocations WHERE request_key LIKE ?',(run['id']+':step:%',)).fetchone()[0]
        self.assertEqual(children,2)
        invalid=deepcopy(parent);invalid['version']='2';invalid['execution']['steps'][0]['inputs']['title']={'step':1,'path':'/title'}
        with self.assertRaisesRegex(ValueError,'earlier'):self.runtime.candidate(invalid)
