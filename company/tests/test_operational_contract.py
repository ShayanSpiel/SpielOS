"""Reproductions of the installed-company failures found in the operational audit."""
import json,subprocess,sys
from pathlib import Path
from company.context.workflow import WorkflowMemory,owner_context
from company.improvements import Improvements
from company.operations import configure_telemetry
from company.tests.scenarios.test_runtime import WorkspaceJourney,specification,report
from company.tests.test_bounded_workflow_runs import attach_development
from company.tests.test_langfuse_export import MemoryLangfuse


class OperationalContractTests(WorkspaceJourney):
    def cases(self):
        spec=specification();release=self.runtime.candidate(spec);runs={}
        for case in spec['evaluation']['cases']:
            run=self.runtime.run(release,case['input'],request_key='audit-'+case['id'],candidate_case=case['id'])
            self.runtime.evaluate_run(run['id']);runs[case['id']]=run['id']
        return release,runs

    def test_release_without_development_and_unverified_remote_evidence_is_refused(self):
        from company.tests.test_bounded_workflow_runs import prepare_fixture_telemetry
        prepare_fixture_telemetry(self.runtime)
        release,runs=self.cases()
        with self.assertRaisesRegex(ValueError,'Improvement'):self.review_runtime.release(release,candidate_runs=runs)
        attach_development(self.runtime,release)
        configure_telemetry(self.runtime,{'enabled':True,'provider':'langfuse','base_url':'https://langfuse.invalid',
            'project_id':'synthetic-project','payload_policy':'reviewed_evidence','require_verified_release':True})
        with self.assertRaisesRegex(ValueError,'Langfuse'):self.review_runtime.release(release,candidate_runs=runs)
        client=MemoryLangfuse()
        for _ in range(4):self.runtime.export_pending(client,limit=100)
        self.review_runtime.release(release,candidate_runs=runs)
        with self.runtime.connect() as connection:
            self.assertEqual(connection.execute('SELECT stage FROM workflow_improvements').fetchone()[0],'accepted')
        other=MemoryLangfuse();other.project_id='wrong-project'
        with self.assertRaises(PermissionError):self.runtime.export_pending(other)

    def test_context_includes_relevant_claims_and_hides_historical_permissions(self):
        memory=WorkflowMemory(self.runtime)
        wanted=memory.add(scope='owner',claim='Use native Persian for ExampleCo social posts.',source='Explicit owner direction',topics=['exampleco'])
        memory.add(scope='owner',claim='Unrelated finance glossary.',source='Owner',topics=['finance'])
        old=memory.add(scope='owner',claim='Publish the old ExampleCo launch now.',source='Historical owner request')
        memory.classify(old['id'],category='historical_authorization',reason='Earlier approval is not current permission')
        text=owner_context(self.runtime,prompt='Create ExampleCo social posts')['text']
        self.assertIn(wanted['claim'],text)
        self.assertNotIn('Unrelated finance glossary',text)
        self.assertNotIn(old['claim'],text)
        self.assertIn('never external permission',text)
        self.assertNotIn(wanted['claim'],owner_context(self.runtime,prompt='Prepare finance totals')['text'])
        memory.classify(wanted['id'],topics=['exampleco'],critical=True,reason='Mandatory owner constraint')
        with self.assertRaisesRegex(ValueError,'mandatory'):owner_context(self.runtime,prompt='ExampleCo',token_budget=1)

    def test_invalid_memory_classification_cannot_leave_a_saved_claim(self):
        memory=WorkflowMemory(self.runtime)
        for fields in ({'category':'invalid'},{'topics':['']},{'critical':'yes'}):
            with self.assertRaises(ValueError):
                memory.add(scope='owner',claim='Rejected synthetic claim',source='Synthetic direction',**fields)
        with self.runtime.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM workflow_memories').fetchone()[0],0)
        saved=memory.add(scope='owner',claim='Valid synthetic claim',source='Synthetic direction',topics=['privacy'],critical=True)
        claim=next(r for r in memory.active(None) if r['id']==saved['id'])
        self.assertTrue(claim['classification']['critical'])
        self.assertEqual(claim['classification']['topics'],['privacy'])

    def test_mandatory_memory_survives_topic_filter_and_fails_closed_on_budget(self):
        memory=WorkflowMemory(self.runtime)
        mandatory=memory.add(scope='owner',claim='Never expose customer identifiers.',
            source='Synthetic owner constraint',topics=['privacy'],critical=True)
        memory.add(scope='owner',claim='Use a monthly finance glossary.',
            source='Synthetic preference',topics=['finance'])
        text=owner_context(self.runtime,prompt='Prepare weekly sales totals')['text']
        self.assertIn(mandatory['claim'],text)
        self.assertNotIn('monthly finance glossary',text)
        with self.assertRaisesRegex(ValueError,'mandatory'):
            owner_context(self.runtime,prompt='Prepare weekly sales totals',token_budget=1)
        memory.retire(mandatory['id'],reason='Synthetic replacement of old constraint')
        self.assertNotIn(mandatory['claim'],owner_context(self.runtime,prompt='Sales totals')['text'])

    def test_unreviewed_imported_claims_do_not_become_current_instructions(self):
        memory=WorkflowMemory(self.runtime)
        old=memory.add(scope='owner',claim='Use the obsolete Legacy serif theme.',source='Historical import')
        with self.runtime.connect() as connection:
            connection.execute('CREATE TABLE workflow_memory_origins (memory_id TEXT PRIMARY KEY,origin_json TEXT NOT NULL)')
            connection.execute('INSERT INTO workflow_memory_origins VALUES(?,?)',(old['id'],json.dumps({'original_authority':'historical; not approval'})))
        self.assertNotIn(old['claim'],owner_context(self.runtime,prompt='Legacy serif theme')['text'])
        memory.classify(old['id'],category='project_instruction',topics=['archive'],reason='Only for a deliberate archive reproduction')
        self.assertNotIn(old['claim'],owner_context(self.runtime,prompt='New website theme')['text'])
        self.assertIn(old['claim'],owner_context(self.runtime,prompt='Reproduce archive')['text'])

    def test_status_exposes_development_candidate_review_and_expected_negative_result(self):
        release,_=self.cases();attach_development(self.runtime,release)
        context=owner_context(self.runtime)
        self.assertEqual(len(context['improvements']),1)
        self.assertEqual(len(context['candidates']),3)
        self.assertEqual(sum(c['expected_rejection'] for c in context['candidates']),1)
        self.assertIn('2 candidate outputs await independent review',context['text'])
        self.assertIn('Langfuse export is disabled',context['text'])
        self.assertIn('No production runs are registered',context['text'])

    def test_system_change_acceptance_requires_real_unchanged_files_and_another_reviewer(self):
        release,_=self.cases();attach_development(self.runtime,release)
        build=Improvements(self.runtime)
        with self.runtime.connect() as c:identity=c.execute('SELECT id FROM workflow_improvements').fetchone()[0]
        # The fixture has reached evaluate; a separate real file change uses its own brief.
        brief=build.get(identity)['brief'];brief['name']='Change an actual file';brief['allowed_files']=['policy.md']
        item=build.create(brief)
        build.observe(item['id'],{'process':'Edit policy','examples':['Old policy'],'failures':['Missing constraint'],
            'criterion_ids':['policy'],'evidence_sources':['Actual file']})
        build.agree_architecture(item['id'],{'chosen_provider':'local','alternatives':['No change'],'tradeoffs':'Explicit constraint',
            'execution_contract':'Edit file','evaluation_contract':'Read file and tests','cost_envelope':'Local','permissions':[],'test_plan':['Policy check']})
        (self.root/'policy.md').write_text('Never publish private records.')
        evidence=self.root/'test-result.json';evidence.write_text('{"policy_check":"passed"}')
        build.attach_change(item['id'],root=self.root,changed_files=['policy.md'],evidence_files=[str(evidence)])
        with self.assertRaises(PermissionError):build.decide(item['id'],decision='accept',reason='Self approval')
        (self.root/'policy.md').write_text('A changed constraint')
        with self.assertRaisesRegex(ValueError,'differ'):Improvements(self.review_runtime).decide(item['id'],decision='accept',reason='Independent review')
        (self.root/'policy.md').write_text('Never publish private records.')
        result=Improvements(self.review_runtime).decide(item['id'],decision='accept',reason='Reviewed actual file and test evidence')
        self.assertEqual(result['stage'],'accepted')

    def test_actual_installed_hook_delivers_memory_and_workflow_readiness(self):
        from company.runtime.bootstrap import scaffold
        from company.mcp import CompanySession
        home=self.root/'hook-home';scaffold(home,keep_stale=True)
        session=CompanySession();selected=session.select(str(home));runtime=session.runtime(selected['company_id'])
        WorkflowMemory(runtime).add(scope='owner',claim='ExampleCo visuals use the selected English wordmark.',source='Explicit synthetic owner rule',topics=['exampleco'])
        for event in ('SessionStart','UserPromptSubmit'):
            output=subprocess.run([sys.executable,'-B',str(home/'.codex/hooks/spielos-context.py')],
                input=json.dumps({'cwd':str(home),'hook_event_name':event,'prompt':'Create ExampleCo visuals'}),capture_output=True,text=True,check=True)
            text=json.loads(output.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('ExampleCo visuals use the selected English wordmark.',text)
            self.assertIn('draft; not qualified for production',text)
            self.assertNotIn('injection failed',text)
        self.assertNotIn('ExampleCo visuals',session.inspect(selected['company_id'],prompt='Finance summary')['context']['text'])
