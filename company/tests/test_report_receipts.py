"""Host receipts carry actual context and once-only review; never invented quality."""
import json,tempfile,unittest,subprocess,sys
from pathlib import Path
from company.runtime.bootstrap import scaffold
from company.mcp import CompanySession
from company.observability.sessions import capture_hook,Sessions
from company.observability.receipts import markdown,context_payload
from company.reporting import snapshot

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name)/'home';scaffold(self.home,keep_stale=True)
        s=CompanySession();v=s.select(str(self.home));self.r=s.runtime(v['company_id']);self.company=s;self.id=v['company_id']
        (self.home/'.spielos/telemetry.json').write_text(json.dumps({'enabled':True,'provider':'langfuse','project_id':'synthetic','base_url':'https://langfuse.invalid','payload_policy':'reviewed_evidence','automatic':{'enabled':True,'judge_runtime':'selected_host'}}))
    def test_real_usage_and_scoped_context_are_recorded_and_reported(self):
        req={'session_id':'synthetic','turn_id':'one','hook_event_name':'UserPromptSubmit','prompt':'Explain synthetic report'}
        info=capture_hook(self.home,req,host='codex',context='Supplied profile',documents={'company/profile.md':'Supplied profile'})
        req.update(hook_event_name='Stop',last_assistant_message='Synthetic answer',model='synthetic-model',usage={'status':'actual','source':'synthetic host receipt','input_tokens':123,'output_tokens':21,'cost':.01,'currency':'USD'})
        capture_hook(self.home,req,host='codex');capture_hook(self.home,req,host='codex');d=snapshot(self.home);self.assertEqual(d['usage']['chat']['input_tokens'],123);self.assertEqual(d['context'][0]['documents'][0]['name'],'company/profile.md')
        receipt=markdown(self.r,info['session_id']);self.assertIn('123 in',receipt);self.assertIn('pending',receipt);self.assertIn('Langfuse trace',receipt);self.assertNotIn('independently accepted',receipt)
    def test_context_avoids_dumping_every_open_improvement(self):
        value=self.company.inspect(self.id,prompt='report');text,docs,update=context_payload(value)
        self.assertIn('Company profile',text);self.assertIn('company/profile.md',docs);self.assertIn('selected memory',update);self.assertNotIn('improvements\": [',text)
    def test_stop_receipt_preserves_same_host_guard(self):
        req={'session_id':'installed','cwd':str(self.home),'turn_id':'one','model':'synthetic-model','hook_event_name':'UserPromptSubmit','prompt':'Show report status'}
        context=self.home/'.codex/hooks/spielos-context.py';observe=self.home/'.codex/hooks/spielos-observe.py'
        subprocess.run([sys.executable,'-B',str(context)],input=json.dumps(req),text=True,capture_output=True,check=True)
        req.update(hook_event_name='Stop',last_assistant_message='Synthetic report status')
        first=json.loads(subprocess.run([sys.executable,'-B',str(observe)],input=json.dumps(req),text=True,capture_output=True,check=True).stdout)
        self.assertEqual(first['decision'],'block');self.assertIn('CURRENT HOST MODEL',first['reason']);self.assertIn('tracking receipt',first['reason']);req['stop_hook_active']=True
        second=json.loads(subprocess.run([sys.executable,'-B',str(observe)],input=json.dumps(req),text=True,capture_output=True,check=True).stdout);self.assertNotIn('decision',second)

    def test_report_slash_command_selects_only_the_current_home(self):
        import importlib.util,io
        from unittest.mock import patch
        script=self.home/'.codex/hooks/spielos-context.py';spec=importlib.util.spec_from_file_location('synthetic_report_hook',script);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        req={'session_id':'slash-fixture','cwd':str(self.home),'hook_event_name':'UserPromptSubmit','prompt':'/report'}
        with patch('sys.stdin',io.StringIO(json.dumps(req))),patch('sys.stdout',new_callable=io.StringIO) as output,patch('company.reporting.ensure_server',return_value={'url':'http://127.0.0.1:9999/synthetic'}) as start:
            mod.main()
            text=json.loads(output.getvalue())['hookSpecificOutput']['additionalContext']
        start.assert_called_once_with(self.home.resolve(),open_browser=True);self.assertIn('clickable link',text)

    def test_local_report_capability_is_not_exported_in_captured_text(self):
        from company.observability.sessions import sanitize
        self.assertNotIn('synthetic-capability',sanitize('Report: http://127.0.0.1:9000/?token=synthetic-capability'))

    def test_recent_telemetry_batches_include_the_pending_trace_root(self):
        from company.observability.automatic import drain,prepare
        prepare(self.r)
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='root-fixture')['id']
        for n in range(60):sessions.record(sid,kind='tool',request_key='old'+str(n),payload={'tool_name':'Old synthetic operation'})
        sessions.turn_key='recent-turn'
        root=sessions.record(sid,kind='context',request_key='root',payload={'documents':{},'reason':'Synthetic selection'})
        for n in range(30):sessions.record(sid,kind='tool',request_key='new'+str(n),payload={'tool_name':'Recent synthetic operation'})
        client=BulkMemory();drain(self.r,seconds=18,limit=40,client=client)
        self.assertTrue(any(o['metadata'].get('event_digest')==root['id'] for o in client.observations))

    def test_workflow_events_are_selected_alongside_activity_backlog(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.tests.test_continuous_evaluation import BulkMemory
        from company.tests.test_bounded_workflow_runs import manifest,identity
        from company.workflows.runs import LocalAdapter
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='fair-queue')['id']
        for n in range(50):sessions.record(sid,kind='tool',request_key=str(n),payload={'tool_name':'Synthetic operation'})
        self.r.adapters['local']=LocalAdapter(identity)
        release=self.r.candidate(manifest());run=self.r.run(release,{'text':'one'},request_key='fair-run',candidate_case='reference')
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        client=BulkMemory()
        with patch('company.observability.evaluators.sync',return_value=None):
            result=drain(self.r,seconds=18,limit=8,client=client)
        with self.r.connect() as c:
            states=[r[0] for r in c.execute('SELECT status FROM workflow_export_outbox WHERE run_id=?',(run['id'],))]
        self.assertTrue(any(state!='pending' for state in states),(states,result))

    def test_broken_suite_setup_does_not_block_unrelated_activity(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.observability.langfuse import ExportError
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='broken-suite')['id']
        ordinary=sessions.record(sid,kind='tool',request_key='ordinary',payload={'tool_name':'Synthetic operation'})
        broken=sessions.record(sid,kind='decision',request_key='suite',payload={'suite_definition':'unavailable-suite'})
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        with patch('company.observability.evaluators.sync',return_value=None), patch('company.evals.harness.enrich_suite_event',side_effect=ExportError('unavailable')):
            result=drain(self.r,seconds=18,limit=16,client=BulkMemory())
        with self.r.connect() as c:
            rows=dict(c.execute('SELECT id,status FROM activity_exports WHERE id IN (?,?)',(ordinary['id'],broken['id'])))
        self.assertNotEqual(rows[ordinary['id']],'pending',result)
        self.assertEqual(rows[broken['id']],'pending')

    def test_deferred_suite_does_not_starve_another_suite(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='suite-fairness')['id']
        first=sessions.record(sid,kind='decision',request_key='suite-one',payload={'suite_definition':'one'})
        second=sessions.record(sid,kind='decision',request_key='suite-two',payload={'suite_definition':'two'})
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        client=BulkMemory();client._rate_path=self.home/'.spielos/telemetry-rate-limit.json'
        with patch('company.observability.evaluators.sync',return_value=None), patch('company.evals.harness.enrich_suite_event',return_value=None) as enrich:
            with patch('company.observability.automatic.time.time',return_value=1000):drain(self.r,seconds=18,limit=16,client=client)
            with patch('company.observability.automatic.time.time',return_value=1016):drain(self.r,seconds=18,limit=16,client=client)
        self.assertEqual({call.args[2]['id'] for call in enrich.call_args_list},{first['id'],second['id']})

    def test_exhausted_unknown_delivery_is_read_back_without_resending(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='exhausted-readback')['id']
        event=sessions.record(sid,kind='tool',request_key='uncertain',payload={'tool_name':'Synthetic operation'})
        with self.r.connect() as c:c.execute("UPDATE activity_exports SET status='exhausted',attempts=30,last_error='Langfuse request failed; result may be unknown' WHERE id=?",(event['id'],))
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        client=BulkMemory()
        with patch('company.observability.evaluators.sync',return_value=None):drain(self.r,seconds=18,limit=16,client=client)
        with self.r.connect() as c:status=c.execute('SELECT status FROM activity_exports WHERE id=?',(event['id'],)).fetchone()[0]
        self.assertEqual(status,'awaiting_readback')
        self.assertFalse(any(item['metadata'].get('event_digest')==event['id'] for item in client.observations))

    def test_stuck_native_definition_does_not_starve_other_definitions(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.observability.evaluators import prepare
        from company.tests.test_continuous_evaluation import BulkMemory
        prepare(self.r)
        with self.r.connect() as c:
            for key in ('synthetic-a','synthetic-b'):c.execute("INSERT INTO native_evaluation_definitions VALUES(?,'{}',NULL,NULL,'pending',NULL)",(key,))
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        client=BulkMemory();client._rate_path=self.home/'.spielos/telemetry-rate-limit.json'
        with patch('company.observability.evaluators.sync',return_value=None) as sync:
            with patch('company.observability.automatic.time.time',return_value=1000):drain(self.r,seconds=18,limit=16,client=client)
            with patch('company.observability.automatic.time.time',return_value=1016):drain(self.r,seconds=18,limit=16,client=client)
        self.assertEqual({call.kwargs['only_key'] for call in sync.call_args_list},{'synthetic-a','synthetic-b'})

    def test_native_creation_retries_only_after_definitely_unsent_failure(self):
        from company.observability.evaluators import sync
        from company.observability.langfuse import ExportError
        from company.tests.test_continuous_evaluation import NativeMemory
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        class Failed(NativeMemory):
            def __init__(self,ambiguous):super().__init__();self.ambiguous=ambiguous
            def request(self,method,path,payload=None):
                if method=='POST' and path=='/api/public/v2/evaluators':raise ExportError('synthetic failure',ambiguous=self.ambiguous)
                return super().request(method,path,payload)
        for ambiguous,expected in [(False,'pending'),(True,'creating_evaluator')]:
            with self.assertRaises(ExportError):sync(self.r,Failed(ambiguous),limit=1)
            with self.r.connect() as c:state=c.execute("SELECT status FROM native_evaluation_definitions WHERE status=?",(expected,)).fetchone()
            self.assertIsNotNone(state)

    def test_definitely_unsent_native_rule_can_retry(self):
        from company.observability.evaluators import sync
        from company.observability.langfuse import ExportError
        from company.tests.test_continuous_evaluation import NativeMemory
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        class FailedRule(NativeMemory):
            def request(self,method,path,payload=None):
                if method=='POST' and path=='/api/public/v2/evaluation-rules':raise ExportError('synthetic throttle',status=429)
                return super().request(method,path,payload)
        with self.assertRaises(ExportError):sync(self.r,FailedRule(),limit=1)
        with self.r.connect() as c:row=c.execute("SELECT status,evaluator_id FROM native_evaluation_definitions WHERE last_error='synthetic throttle'").fetchone()
        self.assertEqual(row['status'],'pending');self.assertIsNotNone(row['evaluator_id'])

    def test_exhausted_resource_can_confirm_late_result_without_resending(self):
        from company.observability.experiments import ensure_resources
        from company.tests.test_continuous_evaluation import BulkMemory
        from company.workflows.runs import digest,canonical
        expected={'name':'Synthetic late dataset','metadata':{'evaluation_digest':'synthetic-digest'}}
        class Late(BulkMemory):
            def request(self,method,path,payload=None):
                if method=='GET' and path.startswith('/api/public/v2/datasets/'):
                    return {**expected,'id':'synthetic-late-dataset'}
                return super().request(method,path,payload)
        client=Late();client._project_verified=True
        key=digest({'project':client.project_id,'kind':'dataset','expected':expected})
        with self.r.connect() as c:c.execute("INSERT INTO workflow_remote_resources VALUES(?,?,?,?,'exhausted',20,NULL,NULL)",(key,client.project_id,'dataset',canonical(expected)))
        found=ensure_resources(self.r,client,[('dataset',expected)])
        self.assertEqual(found[0]['id'],'synthetic-late-dataset');self.assertEqual(client.posts,[])
        with self.r.connect() as c:self.assertEqual(c.execute('SELECT status FROM workflow_remote_resources WHERE key=?',(key,)).fetchone()[0],'verified')

    def test_resource_sync_stops_before_recording_attempt_after_deadline(self):
        import time
        from company.observability.experiments import ensure_resources
        from company.tests.test_continuous_evaluation import BulkMemory
        client=BulkMemory();client._project_verified=True;client.deadline=time.monotonic()-1
        self.assertIsNone(ensure_resources(self.r,client,[('dataset',{'name':'Synthetic'})]))
        with self.r.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM workflow_remote_resources').fetchone()[0],0)

    def test_live_wakes_are_paced_and_resume_on_a_later_wake(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='paced')['id']
        sessions.record(sid,kind='tool',request_key='one',payload={'tool_name':'Synthetic operation'})
        config=json.loads((self.home/'.spielos/telemetry.json').read_text());config['project_id']='synthetic-project'
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        client=BulkMemory();client._rate_path=self.home/'.spielos/telemetry-rate-limit.json'
        with patch('company.observability.evaluators.sync',return_value=None), patch('company.observability.automatic.time.time',return_value=1000):
            first=drain(self.r,seconds=18,limit=16,client=client)
            second=drain(self.r,seconds=18,limit=16,client=client)
        self.assertTrue(first['records']);self.assertEqual(second['state'],'paced')
        with patch('company.observability.evaluators.sync',return_value=None), patch('company.observability.automatic.time.time',return_value=1016):
            third=drain(self.r,seconds=18,limit=16,client=client)
        self.assertEqual(third['state'],'bounded wake completed')

    def test_unresolved_native_setup_never_blocks_activity_transport(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='unresolved-native')['id']
        from company.observability.evaluators import prepare
        prepare(self.r)
        with self.r.connect() as c:c.execute("INSERT INTO native_evaluation_definitions VALUES('synthetic-pending','{}',NULL,NULL,'pending',NULL)")
        with patch('company.observability.evaluators.sync',side_effect=ValueError('An evaluator creation is unresolved')):
            result=drain(self.r,seconds=18,limit=40,client=BulkMemory())
        self.assertIn('unresolved',result['native_definition_issue']);self.assertTrue(result['records'])

    def test_dependency_failure_is_visible_and_successful_retry_clears_it(self):
        from unittest.mock import patch
        from company.observability.automatic import drain
        from company.tests.test_continuous_evaluation import BulkMemory
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='dependency-error')['id']
        record=sessions.record(sid,kind='tool',request_key='dependent',payload={'tool_name':'Synthetic dependency','suite_definition':'synthetic-suite'})
        event_id=record['id']
        client=BulkMemory()
        with patch('company.evals.harness.enrich_suite_event',side_effect=ValueError('Synthetic dataset conflict')):
            drain(self.r,client=client)
        with self.r.connect() as c:
            saved=c.execute('SELECT status,last_error FROM activity_exports WHERE id=?',(event_id,)).fetchone()
        self.assertEqual(saved[0],'pending');self.assertIn('Synthetic dataset conflict',saved[1])
        with patch('company.evals.harness.enrich_suite_event',return_value=None):
            drain(self.r,client=client)
        with self.r.connect() as c:
            saved=c.execute('SELECT status,last_error FROM activity_exports WHERE id=?',(event_id,)).fetchone()
        self.assertEqual(saved[0],'pending');self.assertIn('resources await confirmation',saved[1])
        with patch('company.evals.harness.enrich_suite_event',side_effect=lambda r,c,e:e):
            drain(self.r,client=client)
        with self.r.connect() as c:
            saved=c.execute('SELECT status,last_error FROM activity_exports WHERE id=?',(event_id,)).fetchone()
        self.assertEqual(saved[0],'awaiting_readback');self.assertIsNone(saved[1])

    def test_session_close_cannot_extend_a_completed_turn_or_hide_its_usage(self):
        from unittest.mock import patch
        from datetime import datetime,timezone
        class Clock(datetime):
            value=datetime(2026,11,3,0,0,5,tzinfo=timezone.utc)
            @classmethod
            def now(cls,tz=None):return cls.value
        req={'session_id':'stable-duration','turn_id':'one','hook_event_name':'UserPromptSubmit','prompt':'Inspect a synthetic report'}
        with patch('company.workflows.runs.stamp',return_value='2026-11-03T00:00:00+00:00'):
            info=capture_hook(self.home,req,host='codex')
        req.update(hook_event_name='Stop',last_assistant_message='Synthetic result',usage={'status':'actual','source':'synthetic host receipt','input_tokens':123,'output_tokens':21})
        with patch('datetime.datetime',Clock):capture_hook(self.home,req,host='codex')
        Clock.value=datetime(2026,11,3,2,0,0,tzinfo=timezone.utc)
        req.update(hook_event_name='SessionEnd',usage={'status':'unknown'})
        with patch('datetime.datetime',Clock):capture_hook(self.home,req,host='codex')
        with self.r.connect() as c:
            records=[json.loads(r[0])['payload'] for r in c.execute("SELECT record_json FROM activity_events WHERE session_id=? AND kind='end' ORDER BY rowid",(info['session_id'],))]
        self.assertEqual([r['elapsed_seconds'] for r in records],[5,5])
        receipt=markdown(self.r,info['session_id']);self.assertIn('| Turn elapsed | 5.0s',receipt);self.assertIn('123 in / 21 out',receipt)
        data=snapshot(self.home);self.assertEqual(data['usage']['chat_elapsed_seconds'],5)
        self.assertEqual(data['usage']['chat']['input_tokens'],123)
        # An old inflated close remains immutable evidence; readers prefer the real Stop.
        sessions=Sessions(self.r);sessions.turn_key='one'
        sessions.record(info['session_id'],kind='end',request_key='legacy-inflated-close',payload={'event':'SessionEnd','elapsed_seconds':99999,'usage':{'status':'unknown','scope':'turn_total'}})
        self.assertIn('| Turn elapsed | 5.0s',markdown(self.r,info['session_id']))
        data=snapshot(self.home);self.assertEqual(data['usage']['chat_elapsed_seconds'],5)
        self.assertEqual(data['usage']['chat']['input_tokens'],123)
        with self.r.connect() as c:
            stored=json.loads(c.execute("SELECT record_json FROM activity_events WHERE request_key='legacy-inflated-close'").fetchone()[0])
        self.assertEqual(stored['payload']['elapsed_seconds'],99999)

    def test_both_hosts_request_complete_receipts_even_without_pending_reviews(self):
        for host in ('codex','claude'):
            req={'session_id':'receipt-'+host,'cwd':str(self.home),'turn_id':host,'hook_event_name':'UserPromptSubmit','prompt':'Inspect synthetic status'}
            info=capture_hook(self.home,req,host=host)
            req.update(hook_event_name='Stop',last_assistant_message='Synthetic status')
            capture_hook(self.home,req,host=host)
            with self.r.connect() as c:c.execute("UPDATE host_evaluation_requests SET status='reviewed' WHERE session_id=?",(info['session_id'],))
            script=self.home/('.codex' if host=='codex' else '.claude')/'hooks/spielos-observe.py'
            def run():
                result=subprocess.run([sys.executable,'-X','utf8','-B',str(script)],input=json.dumps(req),text=True,encoding='utf-8',capture_output=True,check=True,timeout=60)
                return json.loads(result.stdout)
            result=run();self.assertEqual(result.get('decision'),'block',result)
            self.assertIn('receipt-only continuation',result['reason'])
            for field in ('Evaluation','Langfuse','Tokens','Cost','Turn elapsed'):self.assertIn('| '+field+' |',result['reason'])
            req['last_assistant_message']='| Turn elapsed | 5s |';self.assertEqual(run().get('decision'),'block')
            req['stop_hook_active']=True;self.assertNotIn('decision',run())
            req.pop('stop_hook_active');req['last_assistant_message']=markdown(self.r,info['session_id']);self.assertNotIn('decision',run())
