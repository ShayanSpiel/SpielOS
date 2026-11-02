"""A desktop install carries its runtime and never stores a company in its cache."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('spielos_plugin_build',ROOT/'tools/build_plugin.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


class PluginDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name).resolve()
        cls.result=builder.build(cls.root/'export');cls.package=Path(cls.result['package'])

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def cli(self,*args,fail=False):
        env={**os.environ,'SPIELOS_PYTHON':sys.executable,'PYTHONPATH':'/missing/untrusted/source','PYTHONDONTWRITEBYTECODE':'1'}
        for key in ('SPIELOS_HOME','SPIELOS_TEMPLATE_DIR','SPIELOS_PRINCIPAL_TOKEN'):env.pop(key,None)
        result=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(self.package/'scripts/entry.py'),*map(str,args)],
            cwd=self.root,env=env,text=True,encoding='utf-8',capture_output=True,timeout=45)
        if fail:self.assertNotEqual(result.returncode,0,result.stdout)
        else:self.assertEqual(result.returncode,0,result.stderr)
        return result

    def test_archive_has_real_logo_onboarding_and_no_global_cli_dependency(self):
        manifest=json.loads((self.package/'plugin.json').read_text());ext=manifest['extensions']['com.openai']
        self.assertLessEqual(len(ext['interface']['shortDescription']),30)
        self.assertTrue((self.package/ext['onboardingSkill']).is_file())
        image=self.package/ext['interface']['logo'];self.assertEqual(image.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
        import struct
        width,height=struct.unpack('>II',image.read_bytes()[16:24]);self.assertEqual(width,height);self.assertGreaterEqual(width,256)
        self.assertEqual(ext['interface']['logo'],ext['interface']['composerIcon'])
        config=json.loads((self.package/'mcp.json').read_text())['mcpServers']['spielos']
        self.assertEqual(config['command'],'python3');self.assertIn('scripts/entry.py',config['args'])
        self.assertEqual(config['cwd'],'.')
        self.assertFalse((self.package/'hooks').exists())
        with zipfile.ZipFile(self.result['archive']) as z:
            names=z.namelist();self.assertTrue(all(n.startswith('spielos/') for n in names))
            self.assertFalse(any(set(Path(n).parts)&{'tests','__pycache__','.spielos','.env','node_modules'} for n in names))
        self.assertEqual(self.cli('--version').stdout.strip(),'spielos '+manifest['version'])

    def test_fresh_setup_status_report_and_actual_workflow_need_no_installed_package(self):
        home=self.root/'fresh-company'
        self.cli('init','--dir',home,'-y','--json')
        self.assertTrue((home/'.spielos/runtime/company/__main__.py').is_file())
        status=json.loads(self.cli('status','--home',home,'--json').stdout);self.assertIn('company_id',status)
        report=json.loads(self.cli('report','--snapshot','--home',home,'--json').stdout)
        self.assertEqual(report['totals']['production_runs'],0)
        candidate=json.loads(self.cli('workflow','candidate','--home',home,'--manifest',home/'company/workflows/sales-report/workflow.json','--json').stdout)
        experiment=json.loads(self.cli('workflow','experiment','--home',home,'--release',candidate['release_digest'],
            '--name','Actual bundled plugin cases','--request-key','plugin-first-journey','--json').stdout)
        self.assertEqual(experiment['state'],'pass');self.assertEqual(len(experiment['runs']),3)
        self.assertFalse((self.package/'.spielos').exists())

    def test_bundled_runtime_is_the_canonical_dashboard_and_receipt_product(self):
        for source in builder.files(ROOT/'company'):
            relative=source.relative_to(ROOT/'company')
            if relative.parts[0] in {'tests','init_templates'}:continue
            self.assertEqual((self.package/'runtime/company'/relative).read_bytes(),source.read_bytes(),str(relative))
        self.assertFalse((self.package/'src').exists())
        self.assertFalse((self.package/'vendor').exists())
        for name in ('setup','director','dashboard','help'):
            self.assertTrue((self.package/'skills'/name/'SKILL.md').is_file())
        manifest=json.loads((self.package/'plugin.json').read_text())
        self.assertEqual(json.loads((self.package/'.codex-plugin/plugin.json').read_text())['version'],manifest['version'])

    def test_packaged_dashboard_serves_authenticated_actual_records(self):
        import urllib.request,signal
        home=self.root/'dashboard-company';self.cli('init','--dir',home,'-y','--json')
        result=json.loads(self.cli('report','--home',home,'--no-open','--port','0','--json').stdout)
        try:
            opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            with opener.open(result['url'],timeout=5) as response:
                self.assertIn('Company report',response.read().decode())
            with opener.open(result['base_url']+'/api/report',timeout=5) as response:
                self.assertEqual(json.load(response)['totals']['production_runs'],0)
        finally:os.kill(result['pid'],signal.SIGTERM)

    def test_packaged_context_stop_evaluation_and_token_receipt_share_one_home(self):
        self.check_host_capture('codex')

    def test_claude_context_stop_evaluation_and_token_receipt_share_one_home(self):
        self.check_host_capture('claude')

    def check_host_capture(self,host):
        home=self.root/('receipt-company-'+host);self.cli('init','--dir',home,'-y','--json')
        setup=json.loads(self.cli('setup-local-capture','--home',home).stdout)
        self.assertTrue(setup['local_capture']);self.assertTrue(setup['bounded_review'])
        self.assertFalse(setup['export_enabled'])
        self.assertIn('primary Director',(home/'AGENTS.md').read_text())
        self.assertTrue((home/'.codex/agents/director.toml').is_file())
        hooks=json.loads((home/('.codex/hooks.json' if host=='codex' else '.claude/settings.json')).read_text())['hooks']
        self.assertTrue({'SessionStart','UserPromptSubmit','PostToolUse','Stop'}<=set(hooks))
        request={'session_id':'packaged-synthetic','turn_id':'one','cwd':str(home),'model':'synthetic-model',
            'hook_event_name':'UserPromptSubmit','prompt':'Inspect synthetic company work'}
        def hook(name):
            import shlex
            from company.platform import hook_arguments
            command=next(entry['command'] for groups in hooks.values() for group in groups for entry in group['hooks'] if Path(hook_arguments(entry['command'])[-1]).name==name)
            self.assertEqual(hook_arguments(command)[0],sys.executable)
            result=subprocess.run(shlex.split(command),
                input=json.dumps(request),text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        context=hook('spielos-context.py')['hookSpecificOutput']['additionalContext']
        self.assertIn('Company profile',context);self.assertNotIn('injection failed',context)
        request.update(hook_event_name='Stop',last_assistant_message='Synthetic company work status',
            usage={'status':'actual','source':'Synthetic host metadata','input_tokens':123,'output_tokens':21})
        stop=hook('spielos-observe.py')
        self.assertEqual(stop['decision'],'block');self.assertIn('CURRENT HOST MODEL',stop['reason'])
        self.assertIn('tracking receipt',stop['reason']);self.assertIn('123 in / 21 out',stop['reason'])
        self.assertIn('Not connected; activity stays local',stop['reason'])
        self.assertNotIn('[Langfuse trace]',stop['reason'])
        request['stop_hook_active']=True;self.assertNotIn('decision',hook('spielos-observe.py'))
        report=json.loads(self.cli('report','--snapshot','--home',home,'--json').stdout)
        self.assertEqual(report['usage']['chat']['input_tokens'],123)
        self.assertTrue(report['context']);self.assertEqual(report['totals']['chat_completions'],1)
        self.assertFalse(report['telemetry']['enabled']);self.assertIsNone(report['telemetry']['project_url'])
        self.assertTrue(all(row['trace_url'] is None for row in report['telemetry']['recent']))
        self.assertEqual(report['evaluation_requests'][0]['status'],'pending')
        self.assertTrue(report['evaluation_requests'][0]['criteria'])
        reviews=json.loads(self.cli('evaluation','pending','--home',home,'--json').stdout)['requests']
        self.assertTrue(reviews)
        review=reviews[0]
        verdict={'request_id':review['id'],'model':'synthetic-model','verdicts':{
            criterion['id']:{'state':'missing','reason':'Synthetic transport check; no semantic qualification.',
                'evidence':'Frozen output: Synthetic company work status'} for criterion in review['request']['rubric']}}
        payload=self.root/'synthetic-verdict.json';payload.write_text(json.dumps(verdict))
        result=json.loads(self.cli('evaluation','judge','--home',home,'--payload',payload,'--json').stdout)
        self.assertFalse(result['independent_acceptance'])
        updated=json.loads(self.cli('report','--snapshot','--home',home,'--json').stdout)
        self.assertEqual(len(updated['evaluations']),1)
        self.assertEqual(updated['evaluation_requests'][0]['status'],'reviewed')

    def test_local_setup_preserves_existing_capture_and_export_policy(self):
        home=self.root/'existing-policy-company';self.cli('init','--dir',home,'-y','--json')
        path=home/'.spielos/telemetry.json';original='{"enabled":false,"payload_policy":"digests_only"}\n'
        path.write_text(original)
        result=json.loads(self.cli('setup-local-capture','--home',home).stdout)
        self.assertTrue(result['existing_policy_preserved']);self.assertFalse(result['local_capture'])
        self.assertEqual(path.read_text(),original)
        self.cli('setup-local-capture','--home',self.package,fail=True)
        self.assertFalse((self.package/'.spielos/telemetry.json').exists())

    def test_public_marketplace_exports_both_hosts_and_distinct_mcp_path_contracts(self):
        output=self.root/'both-host-marketplace'
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/export_plugin_marketplace.py'),'--out',str(output)],
            cwd=self.root,capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        codex=json.loads((output/'.agents/plugins/marketplace.json').read_text())
        claude=json.loads((output/'.claude-plugin/marketplace.json').read_text())
        self.assertEqual(codex['plugins'][0]['source']['path'],claude['plugins'][0]['source'])
        self.assertTrue((output/'docs/tester-guide.md').is_file())
        config=json.loads((output/'spielos/.mcp.json').read_text())['mcpServers']['spielos']
        self.assertIn('${CLAUDE_PLUGIN_ROOT}/scripts/entry.py',config['args'])
        self.assertNotIn('cwd',config)
        manifest=json.loads((output/'spielos/.codex-plugin/plugin.json').read_text())
        self.assertEqual(manifest['mcpServers'],'./mcp.json')

    def test_cache_and_source_are_refused_as_company_destinations(self):
        for home in (self.package/'accidental-company',ROOT/'accidental-company'):
            result=self.cli('init','--dir',home,'-y',fail=True)
            self.assertIn('separate SpielOS home',result.stdout+result.stderr)
            self.assertFalse(home.exists())

    def test_mcp_starts_and_lists_six_tools_without_selecting_a_company(self):
        request='\n'.join(json.dumps(row) for row in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'synthetic-plugin-review','version':'1'}}},
            {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'inspect_company','arguments':{'company_id':'not-selected'}}}])+'\n'
        env={**os.environ,'SPIELOS_PYTHON':sys.executable,'PYTHONPATH':'/missing/untrusted/source'}
        config=json.loads((self.package/'mcp.json').read_text())['mcpServers']['spielos']
        result=subprocess.run([config['command'],*config['args']],input=request,cwd=self.package/config['cwd'],
            env=env,capture_output=True,text=True,encoding='utf-8',timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        rows={row['id']:row for row in map(json.loads,result.stdout.splitlines())}
        self.assertEqual(len(rows[2]['result']['tools']),6)
        self.assertTrue(rows[3].get('error') or rows[3].get('result',{}).get('isError'))
        self.assertFalse((self.package/'.spielos').exists())
