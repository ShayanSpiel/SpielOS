"""Actual report server/metric boundaries using isolated, synthetic company homes."""
import json,os,signal,tempfile,unittest,urllib.request,urllib.error
from pathlib import Path
from company.runtime.bootstrap import scaffold
from company.mcp import CompanySession
from company.reporting import snapshot,ensure_server,state,permitted_file,usage_summary
from company.context.workflow import WorkflowMemory
from company.tests.test_bounded_workflow_runs import manifest,identity
from company.workflows.runs import LocalAdapter

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name)/'home';scaffold(self.home,keep_stale=True)
        s=CompanySession();v=s.select(str(self.home));self.r=s.runtime(v['company_id'])
    def server(self):
        try:result=ensure_server(self.home,port=0)
        except RuntimeError as exc:
            log=self.home/'.spielos/state/report-server.log'
            self.fail(str(exc)+'\nSynthetic server log:\n'+(log.read_text()[-4000:] if log.is_file() else 'No log created'))
        def stop():
            try:os.kill(result['pid'],signal.SIGTERM)
            except ProcessLookupError:pass  # route selection may already restart it
        self.addCleanup(stop);return state(self.home)
    def request(self,s,path,*,auth=True,method='GET',headers=None,data=None):
        h={'Authorization':'Bearer '+s['token']} if auth else {};h.update(headers or {})
        return urllib.request.urlopen(urllib.request.Request(s['base_url']+path,method=method,headers=h,data=json.dumps(data).encode() if data else None),timeout=10)
    def test_recorded_candidate_remains_visible_without_definition(self):
        spec=manifest();spec['id']='historical-candidate';spec['purpose']='Synthetic recorded candidate'
        self.r.adapters['local']=LocalAdapter(identity)
        release=self.r.candidate(spec)
        self.r.run(release,{'text':'one'},request_key='historical',candidate_case='reference')
        data=snapshot(self.home)
        rows=[w for w in data['workflows'] if w['id']=='historical-candidate']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['candidate_runs'],1)
        self.assertEqual(rows[0]['readiness'],'recorded candidate; definition unavailable')
        self.assertIsNone(rows[0]['path'])

    def test_builtin_selection_preserves_custom_history_and_updates_server_route(self):
        from company.reporting import select_ui,configuration
        folder=self.home/'.spielos/artifacts/custom-history';folder.mkdir(parents=True)
        page=folder/'index.html';page.write_text('Synthetic preserved custom history')
        (self.home/'.spielos/report.json').write_text(json.dumps({'ui_root':'.spielos/artifacts/custom-history','custom_name':'Synthetic history','port':0}))
        old=self.server();self.assertTrue(old['custom_ui'])
        select_ui(self.home,'builtin');new=self.server()
        self.assertFalse(new['custom_ui']);self.assertIn('/_spielos/index.html',new['url'])
        self.assertEqual(page.read_text(),'Synthetic preserved custom history')
        self.assertEqual(configuration(self.home)['ui_root'],'.spielos/artifacts/custom-history')
        select_ui(self.home,'custom');self.assertEqual(configuration(self.home)['preferred_ui'],'custom')

    def test_old_pending_reviews_and_more_than_twelve_context_receipts_remain_visible(self):
        from company.observability.automatic import request_judgment
        from company.observability.sessions import Sessions
        first=request_judgment(self.r,'synthetic-session','old',subject='Old pending output',inputs={},output='Frozen result',rubric=[{'id':'quality','question':'Is this supported?'}])
        for n in range(35):
            rid=request_judgment(self.r,'synthetic-session',str(n),subject='Recent result',inputs={},output='Frozen result',rubric=[])
            with self.r.connect() as c:c.execute("UPDATE host_evaluation_requests SET status='reviewed' WHERE id=?",(rid,))
        sessions=Sessions(self.r);sid=sessions.start(host='manual',host_session='context-window')['id']
        for n in range(15):sessions.context(sid,documents={'synthetic.md':str(n)},request_key=str(n),reason='Synthetic supplied document')
        data=snapshot(self.home);review=next(r for r in data['evaluation_requests'] if r['id']==first)
        self.assertEqual(data['evaluation_counts']['pending'],1);self.assertIn('identity',review['blocker'])
        self.assertTrue(review['output_captured']);self.assertEqual(review['output_preview'],'Frozen result')
        self.assertEqual(len(data['context']),15);self.assertFalse(data['context_truncated'])

    def test_loopback_server_starts_without_reverse_dns(self):
        from unittest.mock import patch
        from company.reporting import serve
        with patch('socket.getfqdn',side_effect=AssertionError('Loopback must not require DNS')), \
                patch('http.server.ThreadingHTTPServer.serve_forever'):
            serve(self.home,port=0)
        self.assertTrue(state(self.home)['base_url'].startswith('http://127.0.0.1:'))

    def test_occupied_port_reports_child_exit_instead_of_hiding_startup_failure(self):
        import socket
        occupied=socket.socket();self.addCleanup(occupied.close)
        occupied.bind(('127.0.0.1',0));occupied.listen()
        with self.assertRaisesRegex(RuntimeError,'exited during startup'):
            ensure_server(self.home,port=occupied.getsockname()[1])
        self.assertIn('Address already in use',(self.home/'.spielos/state/report-server.log').read_text())

    def test_fresh_home_report_and_plain_memory_summary_need_no_database(self):
        import subprocess,sys
        home=Path(self.temp.name)/'fresh-home';scaffold(home,keep_stale=True)
        database=home/'.spielos/state/workflows.sqlite'
        self.assertFalse(database.exists())
        d=snapshot(home)
        self.assertEqual(d['totals']['production_runs'],0)
        self.assertEqual(d['totals']['workflows'],1)
        for args in (['report','--snapshot','--json'],['memory','summary']):
            result=subprocess.run([sys.executable,'-B','-m','company',*args,'--home',str(home)],
                capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            if args[0]=='report':self.assertEqual(json.loads(result.stdout)['totals']['workflows'],1)
            else:self.assertIn('0 owner preferences',result.stdout)
        self.assertFalse(database.exists(),'Read-only inspection must not initialize workflow state')

    def test_server_authentication_current_documents_and_reuse(self):
        s=self.server()
        with self.assertRaises(urllib.error.HTTPError) as e:self.request(s,'/api/report',auth=False)
        self.assertEqual(e.exception.code,403)
        with self.request(s,'/api/report') as x:d=json.load(x)
        self.assertEqual(d['totals']['workflows'],1);self.assertEqual(d['totals']['production_runs'],0)
        (self.home/'company/profile.md').write_text('Synthetic revised profile')
        with self.request(s,'/api/report') as x:d=json.load(x)
        self.assertTrue(any(x['text']=='Synthetic revised profile' for x in d['documents']))
        self.assertEqual(ensure_server(self.home)['pid'],s['pid'])
        with self.request(s,'/_spielos/design-system.css') as response:
            self.assertIn('--radius-md:6px',response.read().decode())
        with self.request(s,'/_spielos/outfit-latin.woff2') as response:
            self.assertEqual(response.read(4),b'wOF2')
    def test_path_and_cross_origin_boundaries_and_media_range(self):
        s=self.server();folder=self.home/'.spielos/artifacts/clip';folder.mkdir(parents=True);(folder/'test.mp4').write_bytes(b'0123456789')
        for path in ['/.spielos/telemetry.json','/company/strategy/../../.spielos/security/authority.key','/api/document?path=company/connections/private.json']:
            with self.assertRaises(urllib.error.HTTPError):self.request(s,path)
        with self.request(s,'/.spielos/artifacts/clip/test.mp4',headers={'Range':'bytes=2-5'}) as x:self.assertEqual(x.status,206);self.assertEqual(x.read(),b'2345')
        with self.assertRaises(urllib.error.HTTPError):self.request(s,'/api/open-file',method='POST',data={'path':'company/profile.md'},headers={'Origin':'https://untrusted.invalid','X-Spielos-Report':'1'})
        (self.home/'company/strategy/link.md').symlink_to(self.home/'.spielos/layout.json')
        with self.assertRaises(PermissionError):permitted_file(self.home,'company/strategy/link.md')
    def test_memory_categories_source_and_context_are_distinct(self):
        WorkflowMemory(self.r).add(scope='owner',claim='Use concise synthetic reports',source='Explicit synthetic owner direction',category='preference',topics=['report'])
        d=snapshot(self.home);self.assertEqual(d['memory']['categories']['preference'],1);self.assertEqual(d['totals']['workflow_lessons'],0);self.assertEqual(d['context'],[])
        self.assertEqual(d['memory']['records'][0]['claim'],'Use concise synthetic reports')
        WorkflowMemory(self.r).add(scope='owner',claim='Historical synthetic permission, never active approval',source='Synthetic lineage',category='historical_authorization')
        self.assertEqual(snapshot(self.home)['memory']['categories']['historical_authorization'],1)
    def test_missing_usage_is_never_zero_and_currencies_are_separate(self):
        u=usage_summary([{'status':'unknown'},{'status':'actual','input_tokens':0,'output_tokens':12,'cost':.1,'currency':'USD'},{'status':'estimated','cost':.2,'currency':'EUR'}])
        self.assertFalse(u['complete']);self.assertEqual(u['input_tokens'],0);self.assertEqual(u['output_tokens'],12);self.assertEqual(u['costs']['USD']['actual'],.1);self.assertEqual(u['costs']['EUR']['estimated'],.2)
        self.assertIsNone(usage_summary([{'status':'unknown'}])['input_tokens'])
    def test_custom_ui_is_declared_and_never_traverses(self):
        root=self.home/'.spielos/artifacts/custom';root.mkdir(parents=True);(root/'index.html').write_text('<h1>Synthetic custom UI</h1>')
        (self.home/'.spielos/report.json').write_text(json.dumps({'ui_root':'.spielos/artifacts/custom','custom_name':'Synthetic custom extension'}))
        self.assertEqual(snapshot(self.home)['extension']['custom_name'],'Synthetic custom extension')
        (self.home/'.spielos/report.json').write_text(json.dumps({'ui_root':'../../other-company'}))
        with self.assertRaises(ValueError):snapshot(self.home)
    def test_evaluation_is_required_before_candidate_and_production(self):
        self.r.adapters['local']=LocalAdapter(identity)
        m=manifest();m.pop('evaluation')
        with self.assertRaises((ValueError,KeyError)):self.r.candidate(m)
        m=manifest();m['evaluation']['cases']=[c for c in m['evaluation']['cases'] if c['split']!='negative']
        with self.assertRaises(ValueError):self.r.candidate(m)
        release=self.r.candidate(manifest())
        with self.assertRaises((ValueError,PermissionError)):self.r.run(release,{'text':'one'},request_key='unreleased')
