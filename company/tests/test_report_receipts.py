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
