"""The owner can distinguish quality acceptance, unknown cost and actual charges."""
from company.observability.read_model import workflow_scorecard
from company.observability.langfuse import observation
from .test_home import scenario
from .test_runtime import WorkspaceJourney,create_release


class ReportingJourneys(WorkspaceJourney):
    @scenario('reporting.workflow_scorecard_denominators')
    def test_an_unexecuted_definition_is_a_draft_in_inventory_and_never_a_run(self):
        card=workflow_scorecard(self.runtime)
        self.assertEqual(card['inventory']['workflows'],1)
        self.assertEqual(card['inventory']['draft_only_workflows'],1)
        self.assertEqual(card['inventory']['released_workflows'],0)
        self.assertEqual(card['inventory']['candidate_versions'],0)
        self.assertEqual(card['runs']['total'],0)

    @scenario('reporting.actual_estimated_unknown_usage','reporting.provider_evaluator_retry_costs','reporting.workflow_scorecard_denominators')
    def test_reports_keep_unknown_costs_separate_and_include_evaluator_and_service_work(self):
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        run=self.runtime.run(release,{'title':'Friday','sales':[12,5]},request_key='friday-costs')
        self.runtime.evaluate_run(run['id']);self.review_runtime.review(run['id'],decision='accept')
        self.runtime.record_usage(run['id'],event_key='service-1',stage='external_service',usage={'status':'actual','source':'synthetic-provider-receipt','cost':0.04,'currency':'USD'})
        self.review_runtime.record_usage(run['id'],event_key='judge-1',stage='evaluation',attempt=1,usage={'status':'actual','source':'synthetic-judge-response','input_tokens':150,'output_tokens':20,'cost':0.01,'currency':'USD'})
        self.review_runtime.record_usage(run['id'],event_key='judge-2',stage='evaluation',attempt=2,usage={'status':'estimated','source':'synthetic-evaluator-estimate','cost':0.02,'currency':'USD'})
        self.runtime.record_usage(run['id'],event_key='media-1',stage='media',usage={'status':'actual','source':'synthetic-media-receipt','cost':0.5,'currency':'EUR'})
        card=workflow_scorecard(self.runtime)
        self.assertEqual(card['inventory']['workflows'],1)
        self.assertEqual(card['runs']['total'],1)
        self.assertEqual(card['runs']['accepted_outputs'],1)
        self.assertEqual(card['runs']['review_rate'],1)
        self.assertEqual(card['versions_used']['production'],[{'release_digest':release,'version':'1','runs':1}])
        self.assertEqual(card['unresolved_operations'],{})
        self.assertIsNone(card['human_judge_disagreement']['rate'])
        self.assertEqual(card['runs']['evaluation_coverage'],1)
        self.assertEqual(card['usage']['record_counts'],{'actual':3,'estimated':1,'unknown':1})
        self.assertEqual(card['usage']['stages']['evaluation'],2)
        self.assertAlmostEqual(card['costs_by_currency']['USD']['actual'],0.05)
        self.assertAlmostEqual(card['costs_by_currency']['USD']['estimated'],0.02)
        self.assertEqual(card['costs_by_currency']['EUR']['actual'],0.5)
        self.assertFalse(card['costs_by_currency']['USD']['complete_total'])
        self.assertEqual(card['business_outcomes']['state'],'unmeasured')
        # A repeated callback cannot bill another usage row for the same event.
        self.runtime.record_usage(run['id'],event_key='service-1',stage='external_service',usage={'status':'actual','source':'synthetic-provider-receipt','cost':0.04,'currency':'USD'})
        with self.assertRaises(ValueError):self.runtime.record_usage(run['id'],event_key='service-1',stage='external_service',usage={'status':'actual','source':'changed','cost':9,'currency':'USD'})
        self.assertEqual(workflow_scorecard(self.runtime)['usage']['record_counts']['actual'],3)

    @scenario('reporting.actual_estimated_unknown_usage')
    def test_a_provider_result_retains_measured_usage_and_exports_its_provenance(self):
        import json
        from company.workflows.runs import WorkflowRuntime
        from .test_runtime import specification,report
        class Metered:
            revision='synthetic-metered-v1'
            def start(self,**kwargs):return {'status':'completed','output':report(kwargs['inputs']),
                'usage':{'status':'actual','source':'synthetic-provider-response','input_tokens':30,'output_tokens':12,'cost':0.003,'currency':'USD'}}
        runtime=WorkflowRuntime(self.database,home=self.root,principal=self.owner,adapters={'metered':Metered()})
        spec=specification('metered');release=runtime.candidate(spec);case=spec['evaluation']['cases'][0]
        run=runtime.run(release,case['input'],request_key='metered',candidate_case=case['id'])
        self.assertEqual(run['usage']['input_tokens'],30)
        with runtime.connect() as connection:event=json.loads(connection.execute('SELECT payload_json FROM workflow_export_outbox WHERE run_id=? ORDER BY rowid DESC LIMIT 1',(run['id'],)).fetchone()[0])
        span=observation(event)['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
        attributes={row['key']:next(iter(row['value'].values())) for row in span['attributes']}
        self.assertEqual(attributes['langfuse.observation.metadata.usage_status'],'actual')
        self.assertEqual(attributes['langfuse.observation.metadata.usage_cost'],0.003)
        self.assertLess(int(span['startTimeUnixNano']),int(span['endTimeUnixNano']))

    @scenario('reporting.outbox_readback_and_bounded_recovery','reporting.normal_host_wake_export')
    def test_host_wakes_flush_stable_events_and_stop_when_remote_readback_stays_unavailable(self):
        from company.tests.test_langfuse_export import MemoryLangfuse
        from .test_runtime import specification
        spec=specification('host');release=self.runtime.candidate(spec);case=spec['evaluation']['cases'][0]
        run=self.runtime.run(release,case['input'],request_key='wake-export',candidate_case=case['id'])
        client=MemoryLangfuse(lost=True,visible=False)
        first=self.runtime.wake(run_id=run['id'],client=client)
        self.assertEqual(first['run']['token'],run['token'])
        self.assertEqual(first['telemetry']['events'][0]['status'],'awaiting_readback')
        second=self.open(self.owner).wake(client=client)
        self.assertEqual(len(client.posts),2)
        third=self.open(self.owner).wake(client=client)
        self.assertEqual(third['telemetry']['events'][0]['status'],'exhausted')
        self.assertEqual(self.open(self.owner).wake(client=client)['telemetry']['events'],[])
        self.assertFalse(self.runtime.get(run['id'])['telemetry']['verified'])
        self.assertEqual(len(client.posts),2)
        client.visible=True
        # An operator explicitly extends the verification budget; it reads back
        # the same remote span rather than ingesting another copy.
        verified=self.runtime.export_pending(client,max_attempts=5)
        self.assertEqual(verified[0]['status'],'verified')
        self.assertEqual(len(client.posts),2)
        self.assertTrue(self.runtime.get(run['id'])['telemetry']['verified'])

    @scenario('reporting.thin_plugin_company_selection')
    def test_a_real_stdio_plugin_process_discovers_tools_and_selects_a_company_without_initializing_one(self):
        import json,os,subprocess,sys
        from pathlib import Path
        from company.runtime.bootstrap import scaffold
        home=self.root/'plugin-company';scaffold(home,keep_stale=True)
        unselected=self.root/'not-a-company';unselected.mkdir()
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'acceptance','version':'1'}}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'inspect_company','arguments':{'company_id':'unselected'}}},
                  {'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'select_company','arguments':{'path':str(unselected)}}},
                  {'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'select_company','arguments':{'path':str(home)}}}]
        source=Path(__file__).resolve().parents[3]
        result=subprocess.run([sys.executable,'-B','-m','company','mcp'],cwd=self.root,
            input='\n'.join(json.dumps(row) for row in messages)+'\n',text=True,capture_output=True,
            env={**os.environ,'PYTHONPATH':str(source)},timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        responses={row['id']:row for row in map(json.loads,result.stdout.splitlines())}
        self.assertEqual(responses[1]['result']['protocolVersion'],'2025-06-18')
        self.assertEqual({row['name'] for row in responses[2]['result']['tools']},
            {'select_company','inspect_company','build_workflow','run_workflow','review_output','approve_action'})
        self.assertTrue(responses[3]['result']['isError'])
        self.assertTrue(responses[4]['result']['isError'])
        self.assertFalse((unselected/'.spielos').exists())
        selected=responses[5]['result']['structuredContent']
        self.assertFalse(selected['initialized'])
        self.assertEqual(Path(selected['path']),home)
        self.assertFalse((home/'.spielos/state/workflows.sqlite').exists())
        # A second independent process tests selection, actual script execution
        # and company mismatch refusal through the MCP tools, not direct methods.
        company_id=selected['company_id']
        from company.mcp import CompanySession
        session=CompanySession();session.select(str(home))
        with self.assertRaises(PermissionError):session.call('inspect_company',{'company_id':'another-company'})
        candidate=session.call('build_workflow',{'company_id':company_id,'action':'candidate','payload':{'workflow_id':'sales-report'}})
        run=session.call('run_workflow',{'company_id':company_id,'action':'run','payload':{
            'release_digest':candidate['release_digest'],'inputs':{'title':'example','sales':[10,20]},'request_key':'plugin-example','candidate_case':'example'}})
        checked=session.call('review_output',{'company_id':company_id,'action':'evaluate','payload':{'run_id':run['id']}})
        self.assertEqual(checked['evaluation']['state'],'pass')

    @scenario('reporting.history_load_measurements')
    def test_representative_histories_measure_context_queries_memory_and_payload(self):
        import json,time,tracemalloc
        from contextlib import contextmanager
        from company.context.workflow import owner_context
        from company.workflows.runs import WorkflowRuntime,canonical,stamp
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        class MeasuredRuntime(WorkflowRuntime):
            query_count=0
            @contextmanager
            def connect(measured):
                with super(MeasuredRuntime,measured).connect() as connection:
                    connection.set_trace_callback(lambda sql:setattr(measured,'query_count',measured.query_count+1))
                    yield connection
        runtime=MeasuredRuntime(self.database,home=self.root,principal=self.owner,adapters={'local':self.adapter})
        self.measurements=[];previous=0
        for size in (1000,10000,100000):
            now=stamp()
            with runtime.connect() as connection:
                connection.executemany('''INSERT INTO workflow_invocations
                    (id,request_key,release_digest,inputs_json,status,generation,token,created_at,updated_at,kind,actor)
                    VALUES(?,?,?,?,?,1,?,?,?,'production',?)''',
                    (('load-'+str(index),'load-request-'+str(index),release,canonical({'title':'Synthetic history','sales':[1]}),
                      'awaiting_review' if index%10==0 else 'failed' if index%10==1 else 'completed',
                      'synthetic-token-'+str(index),now,now,self.owner.subject) for index in range(previous,size)))
                connection.executemany('INSERT INTO workflow_usage_events VALUES(?,?,?,?,?,?,?,?)',
                    (('load-usage-'+str(index),'load-'+str(index),'provider','provider',1,canonical({'status':'unknown'}),self.owner.subject,now) for index in range(previous,size)))
            previous=size;runtime.query_count=0
            tracemalloc.start();started=time.perf_counter()
            context=owner_context(runtime);scorecard=workflow_scorecard(runtime)
            seconds=time.perf_counter()-started;current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            payload_bytes=len(json.dumps({'context':context,'scorecard':scorecard}).encode())
            self.measurements.append({'synthetic_runs':size,'seconds':seconds,'database_statements':runtime.query_count,
                                      'python_peak_bytes':peak,'payload_bytes':payload_bytes})
            self.assertEqual(scorecard['runs']['total'],size)
            # The expanded projection includes development, provenance and telemetry.
            # Keep its query count constant across 1k, 10k and 100k runs.
            self.assertLessEqual(runtime.query_count,30)
            self.assertLess(payload_bytes,50000)
            self.assertEqual(len(context['pending']),30)
        self.assertEqual(self.measurements[-1]['synthetic_runs'],100000)


import unittest


class CleanPluginDistributionJourneys(unittest.TestCase):
    @scenario('reporting.thin_plugin_company_selection','security.exact_action_content_destination_scope')
    def test_clean_wheel_and_stdio_plugin_complete_a_real_local_workflow_without_developer_paths(self):
        import json,os,select,shutil,subprocess,sys,tempfile,venv
        from pathlib import Path
        from company.security import CompanyAuthority
        from company.workflows.runs import digest
        source=Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();staging=root/'product-source';staging.mkdir()
            shutil.copytree(source/'company',staging/'company',ignore=shutil.ignore_patterns('tests','__pycache__','*.pyc'))
            for name in ('pyproject.toml','README.md'):shutil.copy2(source/name,staging/name)
            environment={key:value for key,value in os.environ.items() if key not in {'PYTHONPATH','SPIELOS_HOME','SPIELOS_PRINCIPAL_TOKEN'}}
            wheels=root/'wheels';wheels.mkdir()
            built=subprocess.run([sys.executable,'-B','-m','pip','wheel','--no-deps','--wheel-dir',str(wheels),str(staging)],
                cwd=root,env=environment,capture_output=True,text=True,timeout=90)
            self.assertEqual(built.returncode,0,'Building the isolated product wheel failed; inspect packaging dependencies.')
            artifacts=list(wheels.glob('spielos-*.whl'));self.assertEqual(len(artifacts),1)
            virtual=root/'clean-python';venv.EnvBuilder(with_pip=True).create(virtual)
            python=virtual/'bin/python';launcher=virtual/'bin/spielos'
            installed=subprocess.run([str(python),'-B','-m','pip','install','--no-index','--no-deps','--no-compile',str(artifacts[0])],
                cwd=root,env=environment,capture_output=True,text=True,timeout=30)
            self.assertEqual(installed.returncode,0,'Installing the isolated product wheel failed')
            home=root/'clean-company'
            initialized=subprocess.run([str(launcher),'init','--dir',str(home),'-y','--json'],cwd=root,
                env=environment,capture_output=True,text=True,timeout=30)
            self.assertEqual(initialized.returncode,0,initialized.stderr[-500:])
            self.assertEqual(json.loads(initialized.stdout)['layout'],'lean')
            from tools.build_plugin import build
            package=Path(build(root/'desktop-plugin')['package'])
            plugin=json.loads((package/'mcp.json').read_text())
            binding=plugin['mcpServers']['spielos']
            self.assertEqual(binding['command'],'/bin/sh')
            self.assertEqual(binding['args'],['${PLUGIN_ROOT}/scripts/launch.sh','mcp'])
            self.assertNotIn(str(source),json.dumps(plugin))
            environment['PATH']=str(virtual/'bin')+os.pathsep+environment.get('PATH','')
            environment['SPIELOS_PYTHON']=str(python)
            processes=[]
            def client(token=None):
                env=dict(environment)
                if token:env['SPIELOS_PRINCIPAL_TOKEN']=token
                args=[arg.replace('${PLUGIN_ROOT}',str(package)) for arg in binding['args']]
                process=subprocess.Popen([binding['command'],*args],cwd=root,env=env,
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                processes.append(process);counter=0
                def request(method,params):
                    nonlocal counter
                    counter+=1
                    process.stdin.write(json.dumps({'jsonrpc':'2.0','id':counter,'method':method,'params':params})+'\n');process.stdin.flush()
                    self.assertTrue(select.select([process.stdout],[],[],20)[0],'The clean MCP process did not respond')
                    value=json.loads(process.stdout.readline())
                    self.assertEqual(value['id'],counter)
                    self.assertNotIn('error',value)
                    return value['result']
                request('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'clean-acceptance','version':'1'}})
                self.assertEqual(len(request('tools/list',{})['tools']),6)
                def call(name,arguments,*,expect_error=False):
                    result=request('tools/call',{'name':name,'arguments':arguments})
                    self.assertEqual(result.get('isError',False),expect_error,result.get('content'))
                    return result.get('structuredContent',result)
                return call
            try:
                owner=client()
                invalid=root/'uninitialized';invalid.mkdir()
                owner('select_company',{'path':str(invalid)},expect_error=True)
                self.assertFalse((invalid/'.spielos').exists())
                selected=owner('select_company',{'path':str(home)});company_id=selected['company_id']
                args={'company_id':company_id}
                from company.tests.test_bounded_workflow_runs import prepare_fixture_telemetry,verify_fixture_telemetry
                from company.workflows.runs import WorkflowRuntime
                fixture_authority=CompanyAuthority(home)
                fixture_runtime=WorkflowRuntime(home/'.spielos/state/workflows.sqlite',home=home,principal=fixture_authority.local_owner())
                prepare_fixture_telemetry(fixture_runtime)
                candidate=owner('build_workflow',{**args,'action':'candidate','payload':{'workflow_id':'sales-report'}})['release_digest']
                brief={'name':'Qualify clean installed report','business_need':'A real clean-install reporting journey','owner':'Synthetic founder',
                    'baseline':'unknown','target':'Actual case acceptance','constraints':['Draft only'],'intended_users':['Finance lead'],
                    'outcome_window':'This test','allowed_files':['company/workflows/sales-report/workflow.json']}
                improvement=owner('build_workflow',{**args,'action':'create_improvement','payload':{'brief':brief}})['id']
                owner('build_workflow',{**args,'action':'observe','payload':{'improvement_id':improvement,'observation':{
                    'process':'Run installed script','examples':['Representative and held out'],'failures':['Refund'],
                    'criterion_ids':['named','total','rows','positive'],'evidence_sources':['Installed synthetic package']}}})
                owner('build_workflow',{**args,'action':'agree_architecture','payload':{'improvement_id':improvement,'architecture':{
                    'chosen_provider':'local','alternatives':['Host agent'],'tradeoffs':'Checkable arithmetic','execution_contract':'JSON script',
                    'evaluation_contract':'Pinned cases','cost_envelope':'Local test','permissions':[],'test_plan':['All case splits']}}})
                owner('build_workflow',{**args,'action':'attach_candidate','payload':{'improvement_id':improvement,'release_digest':candidate,'changed_files':brief['allowed_files']}})
                # Actual representative, held-out and negative runs, all through
                # the clean installed MCP process, become the release evidence.
                runs={}
                for case in ('example','unseen','refund'):
                    value=json.loads((home/'company/workflows/sales-report/evaluation/cases'/(case+'.json')).read_text())
                    run=owner('run_workflow',{**args,'action':'run','payload':{'release_digest':candidate,
                        'inputs':value['input'],'request_key':'clean:'+case,'candidate_case':case}})
                    result=owner('review_output',{**args,'action':'evaluate','payload':{'run_id':run['id']}})
                    self.assertEqual(result['evaluation']['state'],value['expected']);runs[case]=run['id']
                verify_fixture_telemetry(fixture_runtime)
                authority=CompanyAuthority(home);local_owner=authority.local_owner()
                reviewer_token=authority.issue(local_owner,subject='independent-quality-reviewer',roles=['reviewer'])
                reviewer=client(reviewer_token);reviewer('select_company',{'path':str(home)})
                owner('build_workflow',{**args,'action':'release','payload':{'release_digest':candidate,'candidate_runs':runs}},expect_error=True)
                reviewer('build_workflow',{**args,'action':'release','payload':{'release_digest':candidate,'candidate_runs':runs}})
                run=owner('run_workflow',{**args,'action':'run','payload':{'release_digest':candidate,
                    'inputs':{'title':'A new production request','sales':[7,8,10]},'request_key':'clean-production'}})
                self.assertEqual(run['output']['total'],25)
                owner('review_output',{**args,'action':'evaluate','payload':{'run_id':run['id']}})
                accepted=reviewer('review_output',{**args,'action':'review','payload':{'run_id':run['id'],'decision':'accept'}})
                self.assertEqual(accepted['status'],'completed')
                action={'action':'publish','destination':'https://synthetic.invalid/one-report','content_digest':digest(run['output']),'scope':'One report only'}
                decision=owner('approve_action',{**args,'run_id':run['id'],'action':action,'decision':'approve'})
                self.assertEqual(decision['action_digest'],digest(action))
                import sqlite3
                from contextlib import closing
                with closing(sqlite3.connect(home/'.spielos/state/workflows.sqlite')) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM workflow_effects').fetchone()[0],0)
                    self.assertFalse(connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'core_%'").fetchall())
                self.assertFalse((home/'.spielos/state/company.sqlite').exists())
            finally:
                for process in processes:
                    if process.stdin:process.stdin.close()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
                    if process.stdout:process.stdout.close()
                    if process.stderr:process.stderr.close()


class ExperimentJourneys(WorkspaceJourney):
    @scenario('reporting.langfuse_experiment_datasets')
    def test_actual_case_runs_have_durable_resources_and_verified_v4_experiment_roots(self):
        import json
        from copy import deepcopy
        from urllib.parse import urlsplit,parse_qs,unquote
        from company.observability.experiments import run_experiment,get_experiment
        from company.observability.langfuse import ExportError
        from company.tests.test_langfuse_export import MemoryLangfuse
        from .test_runtime import specification
        class ExperimentTransport(MemoryLangfuse):
            def __init__(self):
                super().__init__();self.datasets={};self.items={};self.configs=[];self.roots={};self.dataset_posts=0
            def request(self,method,path,payload=None):
                parsed=urlsplit(path);query=parse_qs(parsed.query)
                if parsed.path.startswith('/api/public/v2/datasets/'):
                    name=unquote(parsed.path.rsplit('/',1)[1])
                    if name not in self.datasets:raise ExportError('Absent dataset',status=404)
                    return self.datasets[name]
                if parsed.path=='/api/public/v2/datasets':
                    self.dataset_posts+=1;self.datasets[payload['name']]={**deepcopy(payload),'id':'synthetic-dataset'}
                    # Simulate a real accepted mutation whose response was lost.
                    raise ExportError('Synthetic dataset response lost',ambiguous=True)
                if parsed.path.startswith('/api/public/dataset-items/'):
                    identity=parsed.path.rsplit('/',1)[1]
                    if identity not in self.items:raise ExportError('Absent item',status=404)
                    return self.items[identity]
                if parsed.path=='/api/public/dataset-items':self.items[payload['id']]=deepcopy(payload);return payload
                if parsed.path=='/api/public/score-configs':
                    if method=='GET':return {'data':self.configs,'meta':{'totalPages':1}}
                    value={**deepcopy(payload),'id':'config-'+str(len(self.configs))};self.configs.append(value);return value
                if parsed.path=='/api/public/otel/v1/traces':
                    span=payload['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
                    attributes={row['key']:next(iter(row['value'].values())) for row in span['attributes']}
                    if span['spanId']==attributes.get('langfuse.experiment.item.root_observation_id'):
                        self.roots[span['spanId']]={'id':span['spanId'],'traceId':span['traceId'],'experimentId':attributes['langfuse.experiment.id'],
                            'experimentName':attributes['langfuse.experiment.name'],'experimentDatasetId':attributes['langfuse.experiment.dataset.id'],
                            'experimentItemId':attributes['langfuse.experiment.item.id']}
                if parsed.path=='/api/public/experiments':
                    identity=query['id'][0];rows=[row for row in self.roots.values() if row['experimentId']==identity]
                    return {'data':[{'id':identity,'name':rows[0]['experimentName'],'datasetId':'synthetic-dataset','itemCount':len(rows)}] if rows else []}
                if parsed.path=='/api/public/experiment-items':return {'data':[row for row in self.roots.values() if row['experimentId']==query['experimentId'][0]],'meta':{}}
                return super().request(method,path,payload)
        release=self.runtime.candidate(specification())
        experiment=run_experiment(self.runtime,release,name='Synthetic accounting acceptance',request_key='accounting-experiment')
        self.assertEqual(experiment['state'],'pass')
        self.assertFalse(experiment['production_release_created'])
        self.assertEqual(len(experiment['candidate_runs']),3)
        repeated=run_experiment(self.runtime,release,name='Synthetic accounting acceptance',request_key='accounting-experiment')
        self.assertEqual(experiment['candidate_runs'],repeated['candidate_runs'])
        client=ExperimentTransport()
        for _ in range(5):self.runtime.export_pending(client,limit=100)
        verified=get_experiment(self.runtime,experiment['id'])
        self.assertTrue(verified['remote_verified'])
        self.assertEqual(client.dataset_posts,1)
        self.assertEqual(len(client.items),3)
        self.assertEqual(len(client.roots),3)
        self.assertEqual(len(client.configs),4)
        self.assertTrue(all('digest' in row['input'] and 'sales' not in row['input'] for row in client.items.values()))
        self.assertTrue(all(row.get('configId') for row in client.scores))
        self.assertEqual({row['value'] for row in client.scores},{'pass','fail'})
