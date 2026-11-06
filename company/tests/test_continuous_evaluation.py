"""Repeat actual installed lifecycle paths; fixtures do not pretend to be model judgments."""
import json,os,subprocess,sys,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from company.runtime.bootstrap import scaffold
from company.mcp import CompanySession
from company.observability.sessions import Sessions,capture_hook
from company.observability.automatic import pending,submit,drain
from company.observability.evaluators import sync,desired
from company.tests.test_langfuse_export import MemoryLangfuse
from company.tests.test_bounded_workflow_runs import manifest,identity
from company.workflows.runs import LocalAdapter

class BulkMemory(MemoryLangfuse):
    def __init__(self):
        super().__init__();self.batch_calls=0
    def request(self,method,path,payload=None):
        if path=='/api/public/otel/v1/traces':
            self.batch_calls+=1
            for resource in payload['resourceSpans']:
                super().request(method,path,{'resourceSpans':[resource]})
            return {}
        return super().request(method,path,payload)

class NativeMemory(BulkMemory):
    def __init__(self):super().__init__();self.evaluators=[];self.rules=[]
    def request(self,method,path,payload=None):
        for suffix,rows in [('evaluators',self.evaluators),('evaluation-rules',self.rules)]:
            route='/api/public/v2/'+suffix
            if path.split('?')[0]==route:
                if method=='GET':return {'data':deepcopy(rows),'meta':{}}
                row={**deepcopy(payload),'id':suffix+'-'+str(len(rows)),'status':'active'};rows.append(row);return row
            if path.startswith(route+'/'):
                return deepcopy(next(r for r in rows if r['id']==path.rsplit('/',1)[1]))
        return super().request(method,path,payload)

class ContinuousEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name).resolve()/'home';scaffold(self.home,keep_stale=True)
        self.selection=CompanySession();chosen=self.selection.select(str(self.home));self.company_id=chosen['company_id'];self.runtime=self.selection.runtime(self.company_id)
        (self.home/'.spielos/telemetry.json').write_text(json.dumps({'enabled':True,'provider':'langfuse','project_id':'synthetic-project','base_url':'https://langfuse.invalid','payload_policy':'reviewed_evidence','require_verified_release':True,'automatic':{'enabled':True,'judge_runtime':'selected host model'}}))

    def event(self,event,turn,**values):
        return capture_hook(self.home,{'session_id':'synthetic-host','hook_event_name':event,'turn_id':turn,'model':'synthetic-model',**values},host='codex',context='The actual supplied test brief.' if event=='UserPromptSubmit' else None)

    def test_every_turn_freezes_a_distinct_review_without_manual_experiment(self):
        for n in range(2):
            self.event('UserPromptSubmit','turn-'+str(n),prompt='Order '+str(n)+': explain the captured result')
            self.event('Stop','turn-'+str(n),last_assistant_message='Actual synthetic answer '+str(n))
        reviews=pending(self.runtime);self.assertEqual(len(reviews),2)
        self.assertNotEqual(reviews[0]['request']['artifact_digest'],reviews[1]['request']['artifact_digest'])
        self.assertTrue(all(r['request']['model']=='synthetic-model' for r in reviews))
        with self.runtime.connect() as c:
            events=[json.loads(r[0]) for r in c.execute("SELECT payload_json FROM activity_exports WHERE json_extract(payload_json,'$.category')='director_turn'")]
        self.assertEqual(len({e['trace_run_id'] for e in events}),2)
        self.assertTrue(all('Order' in e['trace_name'] for e in events))
        self.assertTrue(all(e['evaluation']['state']=='missing' for e in events))

    def test_absent_answer_records_capture_gap_without_unjudgeable_request(self):
        self.event('UserPromptSubmit','capture-gap',prompt='Synthetic question')
        self.event('Stop','capture-gap')
        self.assertEqual(pending(self.runtime),[])
        with self.runtime.connect() as c:
            records=[json.loads(r[0]) for r in c.execute("SELECT record_json FROM activity_events WHERE kind='evaluation'")]
        self.assertTrue(any(r['payload']['output']['quality_review']=='Capture incomplete; no final answer exposed' for r in records))

    def test_reassignment_preserves_frozen_artifact_and_prevents_old_submission(self):
        from company.observability.automatic import reassign
        self.event('UserPromptSubmit','reassign',prompt='Review this synthetic result')
        self.event('Stop','reassign',last_assistant_message='Frozen synthetic result')
        old=pending(self.runtime)[0]
        replacement=reassign(self.runtime,old['id'],model='synthetic-new-model',reason='Original judge unavailable',model_source='Explicit synthetic host metadata')
        with self.runtime.connect() as c:
            new=json.loads(c.execute('SELECT request_json FROM host_evaluation_requests WHERE id=?',(replacement['id'],)).fetchone()[0])
            original=json.loads(c.execute('SELECT request_json FROM host_evaluation_requests WHERE id=?',(old['id'],)).fetchone()[0])
        self.assertEqual(new['output'],original['output']);self.assertEqual(new['artifact_digest'],original['artifact_digest'])
        self.assertEqual(new['rubric'],original['rubric']);self.assertEqual(original['model'],'synthetic-model')
        self.assertEqual(reassign(self.runtime,old['id'],model='synthetic-new-model',reason='Same request',model_source='Synthetic metadata')['id'],replacement['id'])
        verdicts={c['id']:{'state':'missing','reason':'Synthetic missing evidence','evidence':['Frozen artifact']} for c in original['rubric']}
        with self.assertRaisesRegex(ValueError,'reassigned'):submit(self.runtime,old['id'],verdicts=verdicts,model='synthetic-model')
        result=submit(self.runtime,replacement['id'],verdicts=verdicts,model='synthetic-new-model')
        self.assertFalse(result['independent_acceptance']);self.assertEqual(pending(self.runtime),[])

    def test_bulk_reconciliation_confirms_scoreless_events_without_remote_writes(self):
        from company.observability.automatic import reconcile_delivery
        sessions=Sessions(self.runtime);sid=sessions.start(host='manual',host_session='bulk-readback')['id']
        for n in range(120):sessions.record(sid,kind='tool',request_key=str(n),payload={'tool_name':'Synthetic operation'})
        client=BulkMemory();drain(self.runtime,client=client,limit=100)
        posts=len(client.posts)
        result=reconcile_delivery(self.runtime,limit=1000,client=client)
        self.assertGreater(result['verified'],0);self.assertEqual(len(client.posts),posts)
        self.assertLessEqual(result['checked'],1000)

    def test_host_judgment_has_reasons_evidence_and_numeric_rating_and_preserves_frozen_output(self):
        self.event('UserPromptSubmit','review',prompt='Explain the result')
        info=self.event('Stop','review',last_assistant_message='The actual frozen answer.')
        request=pending(self.runtime)[0]
        verdicts={c['id']:{'state':'pass','reason':'Synthetic test verdict only','evidence':['The frozen answer is the source artifact.'],'score':0.8} for c in request['request']['rubric']}
        with self.assertRaises(ValueError):submit(self.runtime,request['id'],verdicts=verdicts,model='invented-model')
        result=submit(self.runtime,request['id'],verdicts=verdicts,model='synthetic-model',source='Explicit synthetic fixture; not an actual Codex quality qualification')
        self.assertFalse(result['independent_acceptance']);self.assertEqual(pending(self.runtime),[])
        self.event('Stop','review',last_assistant_message='The actual frozen answer.',stop_hook_active=True)
        self.assertEqual(pending(self.runtime),[])
        with self.runtime.connect() as c:
            frozen=json.loads(c.execute('SELECT request_json FROM host_evaluation_requests WHERE id=?',(request['id'],)).fetchone()[0])
        self.assertEqual(frozen['output'],'The actual frozen answer.')

    def test_installed_stop_requests_only_one_same_host_review_pass(self):
        context=self.home/'.codex/hooks/spielos-context.py';observer=self.home/'.codex/hooks/spielos-observe.py'
        request={'session_id':'installed-smoke','cwd':str(self.home),'turn_id':'one','model':'synthetic-model','hook_event_name':'UserPromptSubmit','prompt':'Explain the captured result'}
        subprocess.run([sys.executable,'-B',str(context)],input=json.dumps(request),text=True,capture_output=True,check=True,timeout=15)
        request.update(hook_event_name='Stop',last_assistant_message='The captured result.')
        first=subprocess.run([sys.executable,'-B',str(observer)],input=json.dumps(request),text=True,capture_output=True,check=True,timeout=15)
        value=json.loads(first.stdout);self.assertEqual(value['decision'],'block');self.assertIn('CURRENT HOST MODEL',value['reason']);self.assertIn('one pass',value['reason'])
        request['stop_hook_active']=True
        second=subprocess.run([sys.executable,'-B',str(observer)],input=json.dumps(request),text=True,capture_output=True,check=True,timeout=15)
        self.assertNotIn('decision',json.loads(second.stdout))

    def test_workflow_output_is_evaluated_at_delivery_and_registers_its_definition(self):
        sessions=Sessions(self.runtime);session=sessions.start(host='manual',host_session='workflow-fixture',role='builder')
        self.runtime.activity_session_id=session['id'];self.runtime.adapters['local']=LocalAdapter(identity)
        release=self.runtime.candidate(manifest());run=self.runtime.run(release,{'text':'one'},request_key='actual-output',candidate_case='reference')
        self.assertEqual(run['evaluation']['state'],'pass');self.assertEqual(run['status'],'awaiting_review')
        self.assertEqual(self.runtime.evaluate_run(run['id'])['evaluation'],run['evaluation'])
        with self.runtime.connect() as c:
            definition=json.loads(c.execute('SELECT definition_json FROM workflow_evaluation_definitions WHERE release_digest=?',(release,)).fetchone()[0])
        self.assertEqual(definition['rubric']['standard'],'spielos-evaluation/2')
        self.assertEqual(definition['execution']['provider'],'local')

    def test_batched_wakes_drain_more_than_two_records_without_duplicate_spans(self):
        sessions=Sessions(self.runtime);session=sessions.start(host='manual',host_session='backlog-fixture')
        for n in range(59):sessions.record(session['id'],kind='tool',request_key=str(n),payload={'tool_name':'Actual fixture operation '+str(n)})
        client=BulkMemory()
        for _ in range(5):drain(self.runtime,seconds=18,limit=100,client=client)
        self.assertTrue(sessions.show(session['id'])['observable'])
        self.assertEqual(len(client.observations),60);self.assertLess(client.batch_calls,5)

    def test_native_definitions_are_readable_scoped_and_idempotent(self):
        client=NativeMemory();first=sync(self.runtime,client);second=sync(self.runtime,client)
        self.assertEqual(len(first),4);self.assertEqual(len(client.evaluators),4);self.assertEqual(len(client.rules),4)
        self.assertTrue(all(r['sampling']==1 and r['enabled'] for r in client.rules))
        self.assertTrue(all(any(f.get('key')=='company_id' and f['value']==self.company_id for f in r['filter']) for r in client.rules))
        self.assertTrue(any('Codex / host model' in e['name'] for e in client.evaluators))

    def test_long_definition_fits_remote_limit_without_discarding_local_contract(self):
        from company.observability.evaluators import register_agent
        agent={'id':'synthetic-long-contract','description':'Detailed synthetic responsibility 🧪 '*250}
        register_agent(self.runtime,agent)
        client=NativeMemory();sync(self.runtime,client)
        wire=next(e for e in client.evaluators if 'Synthetic Long Contract' in e['name'])
        self.assertLessEqual(len(wire['description'].encode('utf-16-le'))//2,2000)
        self.assertIn('SHA-256:',wire['description'])
        with self.runtime.connect() as c:
            saved=json.loads(c.execute('SELECT definition_json FROM agent_evaluation_definitions WHERE agent_id=?',(agent['id'],)).fetchone()[0])
        self.assertEqual(saved['description'],agent['description'])

    def test_legacy_definite_creation_failure_recovers_but_unknown_does_not(self):
        from company.observability.evaluators import prepare
        from company.workflows.runs import canonical
        prepare(self.runtime);plan=desired(self.runtime)[0]
        with self.runtime.connect() as c:
            c.execute("INSERT INTO native_evaluation_definitions VALUES(?,?,NULL,NULL,'creating_evaluator',?)",(plan['key'],canonical(plan),'Langfuse request failed (HTTP 400)'))
        client=NativeMemory();sync(self.runtime,client,only_key=plan['key'])
        self.assertEqual(len(client.evaluators),1)
        with self.runtime.connect() as c:
            c.execute("UPDATE native_evaluation_definitions SET status='creating_evaluator',last_error='Langfuse request failed; result may be unknown' WHERE key=?",(plan['key'],))
        unseen=NativeMemory()
        with self.assertRaisesRegex(ValueError,'unresolved'):sync(self.runtime,unseen,only_key=plan['key'])
        self.assertEqual(unseen.evaluators,[])

    def test_new_agent_always_registers_its_own_native_definition(self):
        from company.agents.loader import AgentCatalog
        AgentCatalog(self.home,self.selection.principal()).create_agent({'id':'motion-designer','description':'Design readable, restrained motion for the supplied order','permissions':['write_artifacts'],'produces':['motion-preview']})
        definitions=desired(self.runtime)
        self.assertTrue(any(d['key']=='agent:motion-designer' for d in definitions))
        plan=next(d for d in definitions if d['key']=='agent:motion-designer')
        self.assertIn('Motion Designer',plan['evaluator']['name'])
        self.assertTrue(any(f.get('key')=='agent_id' and f['value']=='motion-designer' for f in plan['rule']['filter']))

    def test_native_setup_rate_limit_does_not_stop_activity_delivery(self):
        from company.observability.langfuse import ExportError
        from company.observability.evaluators import register_agent
        class Limited(NativeMemory):
            def request(self,method,path,payload=None):
                if path.startswith('/api/public/v2/evaluators'):raise ExportError('Synthetic definition rate limit',status=429,retry_after=60)
                return super().request(method,path,payload)
        register_agent(self.runtime,{'id':'test-agent','description':'Actual rate-limit fixture'})
        session=Sessions(self.runtime).start(host='manual',host_session='rate-limit-delivery')
        client=Limited();result=drain(self.runtime,seconds=18,client=client)
        self.assertEqual(client.batch_calls,1)
        self.assertIn('rate limited',result['native_definition_issue'])
