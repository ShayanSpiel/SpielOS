import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from company.runtime.bootstrap import scaffold
from company.mcp import CompanySession
from company.observability.sessions import Sessions
from company.observability.usage import read_codex,ingest,summary,estimate

class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve();self.home=self.root/'company';scaffold(self.home,keep_stale=True)
        self.codex=self.root/'codex';(self.codex/'sessions').mkdir(parents=True);self.path=self.codex/'sessions/selected.jsonl';self.env=patch.dict(os.environ,{'CODEX_HOME':str(self.codex)});self.env.start();self.addCleanup(self.env.stop)
        s=CompanySession();v=s.select(str(self.home));self.r=s.runtime(v['company_id']);self.sid=Sessions(self.r).start(host='codex',host_session='selected')['id']
    def data(self):
        counts={'input_tokens':100,'cached_input_tokens':80,'cache_write_input_tokens':0,'output_tokens':20,'reasoning_output_tokens':10,'total_tokens':120}
        return [{'type':'session_meta','payload':{'id':'selected','cwd':str(self.home)}},{'type':'event_msg','timestamp':'2026-11-02T00:00:00Z','payload':{'type':'task_started','turn_id':'t1','started_at':'2026-11-02T00:00:00Z'}},{'type':'turn_context','payload':{'turn_id':'t1','model':'gpt-6.1-sol'}},{'type':'response_item','payload':{'type':'reasoning','summary':'SECRET_REASONING_DO_NOT_COLLECT'}},{'type':'event_msg','timestamp':'2026-11-02T00:00:02Z','payload':{'type':'token_count','info':{'total_token_usage':counts,'last_token_usage':counts}}},{'type':'event_msg','timestamp':'2026-11-02T00:00:03Z','payload':{'type':'task_complete','turn_id':'t1','duration_ms':3000,'completed_at':'2026-11-02T00:00:03Z','last_agent_message':'PRIVATE_MESSAGE_NOT_USAGE'}}]
    def write(self,rows):self.path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    def test_usage_has_cache_reasoning_and_turn_time_without_message_collection(self):
        self.write(self.data());x=read_codex(self.path,host_session='selected',home=self.home);t=x['turns'][0]
        self.assertEqual(t['usage']['total_tokens'],120);self.assertEqual(t['usage']['cached_input_tokens'],80);self.assertEqual(t['usage']['output_tokens'],20);self.assertEqual(t['duration_ms'],3000);self.assertNotIn('SECRET_REASONING',json.dumps(x));self.assertNotIn('PRIVATE_MESSAGE',json.dumps(x))
    def test_import_is_idempotent_and_completed_usage_is_not_a_new_workflow_run(self):
        self.write(self.data());a=ingest(self.r,self.sid,path=self.path,publish=True);b=ingest(self.r,self.sid,path=self.path,publish=True)
        self.assertEqual(a['state'],'recorded');self.assertEqual(b['state'],'unchanged');self.assertEqual(summary(self.r)['totals']['input_tokens'],100)
        with self.r.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM workflow_invocations').fetchone()[0],0);self.assertEqual(c.execute("SELECT COUNT(*) FROM activity_events WHERE kind='generation'").fetchone()[0],1)
    def test_counter_snapshots_are_deltas_not_repeated_totals(self):
        rows=self.data();second=json.loads(json.dumps(rows[4]));second['timestamp']='2026-11-02T00:00:02.5Z'
        for k in second['payload']['info']['total_token_usage']:second['payload']['info']['total_token_usage'][k]*=2
        rows.insert(5,second);rows.insert(6,second);self.write(rows);x=read_codex(self.path,host_session='selected',home=self.home)
        self.assertEqual(x['turns'][0]['usage']['input_tokens'],200);self.assertEqual(x['turns'][0]['usage']['output_tokens'],40)
    def test_other_chat_company_and_symbolic_sources_are_refused(self):
        self.write(self.data())
        with self.assertRaises(PermissionError):read_codex(self.path,host_session='another-chat',home=self.home)
        with self.assertRaises(PermissionError):read_codex(self.path,host_session='selected',home=self.root/'other')
        alias=self.codex/'sessions/alias.jsonl';alias.symlink_to(self.path)
        with self.assertRaises(PermissionError):read_codex(alias,host_session='selected',home=self.home)
    def test_standard_credit_and_api_equivalent_cost_are_separate_from_the_bill(self):
        u={'input_tokens':1000000,'cached_input_tokens':900000,'cache_write_input_tokens':0,'output_tokens':100000,'reasoning_output_tokens':40000}
        p=estimate(u,'gpt-6.1-sol',request_input=1000000);self.assertAlmostEqual(p['standard_reference_credits'],32.25);self.assertAlmostEqual(p['api_standard_equivalent_usd'],2.08);self.assertIsNone(p['actual_bill']);self.assertTrue(p['api_long_context_applied']);self.assertIn('openai.com',p['api_source'])
        self.assertEqual(estimate(u,'unknown-model')['status'],'unknown')

    def test_completion_without_new_tokens_refreshes_usage_and_publishes_once(self):
        rows=self.data();self.write(rows[:-1]);ingest(self.r,self.sid,path=self.path,publish=True)
        self.write(rows);result=ingest(self.r,self.sid,path=self.path,publish=True)
        self.assertEqual(result['state'],'recorded');self.assertIsNotNone(summary(self.r)['turns'][0]['completed_at'])
        with self.r.connect() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM activity_events WHERE kind='generation'").fetchone()[0],1)

    def test_host_epoch_seconds_are_normalized_before_browser_dates(self):
        rows=self.data();rows[1]['payload']['started_at']=1793586042;self.write(rows)
        self.assertTrue(read_codex(self.path,host_session='selected',home=self.home)['turns'][0]['started_at'].startswith('2026-11-02'))
