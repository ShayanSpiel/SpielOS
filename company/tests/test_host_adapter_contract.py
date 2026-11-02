"""Real host context journeys for the bounded workflow product."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tempfile,unittest
from company.runtime.bootstrap import scaffold
from company.security import CompanyAuthority
from company.agents.loader import AgentCatalog
from company.workflows.runs import WorkflowRuntime
from company.tests.scenarios.test_runtime import specification,create_release

SOURCE=Path(__file__).resolve().parents[2]
HOSTS=SOURCE/'company/init_templates/hosts'


class HostContextContracts(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.home=Path(self.directory.name).resolve()/'company-home';scaffold(self.home,keep_stale=True)

    def hook(self,host,event='UserPromptSubmit',*,cwd=None,script=None):
        path=script or self.home/('.'+host)/'hooks/spielos-context.py'
        result=subprocess.run([sys.executable,'-B',str(path)],cwd=self.directory.name,
            input=json.dumps({'cwd':str(cwd or self.home),'hook_event_name':event,'prompt':'Continue the sales report'}),
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def pending(self):
        authority=CompanyAuthority(self.home);owner=authority.local_owner()
        catalog=AgentCatalog(self.home,owner)
        catalog.create_skill(name='sales-summary',description='Summarize supplied sales accurately.',instructions='Keep the requested title and explicit sum and row count. Draft only.')
        catalog.create_agent({'id':'finance-reporter','description':'Prepare bounded sales reports.','skill_ids':['sales-summary'],'permissions':['read_company','write_artifacts']})
        token=authority.issue(owner,subject='independent-reviewer',roles=['reviewer'])
        path=self.home/'.spielos/state/workflows.sqlite'
        runtime=WorkflowRuntime(path,home=self.home,principal=owner)
        review=WorkflowRuntime(path,home=self.home,principal=authority.authenticate(token))
        release,_=create_release(runtime,specification('host'),reviewer_runtime=review)
        run=runtime.run(release,{'title':'Owner request','sales':[2,7]},request_key='pending-host-context')
        return runtime,run

    def test_fresh_startup_resume_and_compaction_have_profile_and_workflows_without_creating_state(self):
        for host in ('codex','claude'):
            for event in ('SessionStart','UserPromptSubmit'):
                with self.subTest(host=host,event=event):
                    output=self.hook(host,event)['hookSpecificOutput']
                    self.assertEqual(output['hookEventName'],event)
                    self.assertIn('Company profile',output['additionalContext'])
                    self.assertIn('Available workflows',output['additionalContext'])
                    self.assertIn('sales summary',output['additionalContext'])
        self.assertFalse((self.home/'.spielos/state/company.sqlite').exists())
        self.assertFalse((self.home/'.spielos/state/workflows.sqlite').exists())

    def test_pending_work_survives_host_restart_and_readonly_context_does_not_mutate_it(self):
        runtime,run=self.pending();database=runtime.path
        before=hashlib.sha256(database.read_bytes()).hexdigest()
        for host in ('codex','claude'):
            text=self.hook(host,'SessionStart')['hookSpecificOutput']['additionalContext']
            human,machine=text.rsplit('\nMachine reference: ',1)
            self.assertIn('waiting for its assigned executor',human)
            self.assertNotIn(run['id'],human);self.assertNotIn('awaiting_provider',human)
            self.assertIn(run['id'],machine)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(),before)
        self.assertEqual(runtime.get(run['id'])['status'],'awaiting_provider')

    def test_template_hook_in_an_unrelated_folder_never_initializes_or_reads_a_company(self):
        unrelated=Path(self.directory.name)/'unrelated';unrelated.mkdir()
        for host in ('codex','claude'):
            self.assertIsNone(self.hook(host,cwd=unrelated,script=HOSTS/host/'hooks/spielos-context.py'))
        self.assertFalse((unrelated/'.spielos').exists())

    def test_authentication_failure_is_visible_without_blocking_host_startup(self):
        (self.home/'.spielos/security/authority.key').chmod(0o644)
        text=self.hook('codex')['hookSpecificOutput']['additionalContext']
        self.assertIn('injection failed',text)
        self.assertNotIn('authority.key',text)
        self.assertNotIn('bearer',text)

    def test_update_retires_only_owned_polling_hooks_and_preserves_owner_hooks(self):
        for host,filename in [('codex','hooks.json'),('claude','settings.json')]:
            path=self.home/('.'+host)/filename
            value=json.loads(path.read_text())
            old_command=('python3 '+str(self.home/'.codex/hooks/spielos-attention.py') if host=='codex'
                         else 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/spielos-attention.py"')
            value['hooks']['Stop']=[{'hooks':[{'type':'command','command':old_command},
                {'type':'command','command':'owner-check --keep'}]}]
            value['owner_setting']='keep this'
            path.write_text(json.dumps(value))
        scaffold(self.home,force=True,keep_stale=True)
        for host,filename in [('codex','hooks.json'),('claude','settings.json')]:
            value=json.loads((self.home/('.'+host)/filename).read_text())
            self.assertEqual(value['owner_setting'],'keep this')
            commands=[entry['command'] for groups in value['hooks'].values() for group in groups for entry in group['hooks']]
            self.assertIn('owner-check --keep',commands)
            self.assertFalse(any('spielos-attention.py' in command for command in commands))
            self.assertEqual(sum('spielos-context.py' in command for command in commands),2)

    def test_retired_attention_scripts_are_noops(self):
        for host in ('codex','claude'):
            result=subprocess.run([sys.executable,'-B',str(self.home/('.'+host)/'hooks/spielos-attention.py')],input='{}',capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0);self.assertEqual(result.stdout,'')
        self.assertFalse((self.home/'.spielos/state/workflows.sqlite').exists())

    def test_opencode_context_hook_executes_the_real_company_reader_without_idle_polling(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node is required for the OpenCode adapter acceptance harness')
        script=r'''const fs=require('node:fs');const cp=require('node:child_process');const {Readable}=require('node:stream');
const {pathToFileURL}=require('node:url');
(async()=>{
 const settings=JSON.parse(process.argv[1]);let handler;
 global.Bun={file:path=>({exists:async()=>fs.existsSync(path)}),spawn:options=>{
  const child=cp.spawn(options.cmd[0],options.cmd.slice(1),{cwd:options.cwd,env:options.env,stdio:['ignore','pipe','pipe']});
  return {stdout:Readable.toWeb(child.stdout),stderr:Readable.toWeb(child.stderr),exited:new Promise(resolve=>child.on('exit',resolve))};}};
 const module=await import(pathToFileURL(settings.plugin).href);
 if(module.default.id!=='spielos-notifications')throw new Error('Host plugin identity changed');
 await module.default.setup({session:{hook:async(name,callback)=>{if(name!=='context')throw new Error('Unexpected hook');handler=callback;}}});
 const event={directory:settings.home,system:[]};await handler(event);
 console.log(JSON.stringify(event.system));
})().catch(error=>{console.error(error);process.exitCode=1;});'''
        result=subprocess.run([node,'--experimental-strip-types','-e',script,json.dumps({'plugin':str(HOSTS/'opencode/plugins/spielos-notifications.ts'),'home':str(self.home)})],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        values=json.loads(result.stdout)
        self.assertEqual(len(values),1)
        self.assertIn('Company profile',values[0]['text'])
        self.assertIn('Available workflows',values[0]['text'])
        self.assertNotIn('injection failed',values[0]['text'])
