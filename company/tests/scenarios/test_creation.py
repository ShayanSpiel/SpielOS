"""A team creates reusable methods and an agent, then receives a real assignment."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from company.agents.loader import AgentCatalog,available_agents
from company.workflows.runs import WorkflowRuntime
from .test_home import scenario
from .test_runtime import WorkspaceJourney,specification,report


class AgentCreationJourneys(WorkspaceJourney):
    @scenario('creation.agent_creation_validates_skills_permissions','creation.skill_creation_and_execution_context','runtime.host_agent_real_assignment')
    def test_reporter_receives_its_pinned_skill_in_a_claimed_bounded_assignment(self):
        spec=specification('host');release=self.runtime.candidate(spec)
        case=spec['evaluation']['cases'][0]
        pending=self.runtime.run(release,case['input'],request_key='agent-assignment',candidate_case=case['id'])
        assignment=pending['assignment']
        self.assertEqual(assignment['agent']['id'],'finance-reporter')
        documents=assignment['context']['documents']
        skill=next(row for row in documents if row['name']=='skills/sales-summary/SKILL.md')
        self.assertIn('Do not infer revenue impact',skill['text'])
        self.assertEqual(assignment['inputs'],case['input'])
        with self.assertRaises(PermissionError):self.runtime.deliver(pending['id'],report(case['input']),token=pending['token'])
        claimed=self.runtime.claim(pending['id'])
        with self.assertRaises(RuntimeError):self.runtime.claim(pending['id'])
        with self.assertRaises(RuntimeError):self.runtime.deliver(pending['id'],report(case['input']),token=pending['token'])
        self.runtime.deliver(pending['id'],report(case['input']),token=claimed['token'])
        self.assertEqual(self.runtime.evaluate_run(pending['id'])['evaluation']['state'],'pass')
        self.assertIn('finance-reporter',available_agents(self.root))

    @scenario('creation.agent_creation_validates_skills_permissions')
    def test_malformed_and_overprivileged_agent_declarations_do_not_get_installed(self):
        catalog=AgentCatalog(self.root,self.owner)
        invalid=[{'id':'invalid','description':'Missing skill','skill_ids':['missing']},
                 {'id':'invalid','description':'Wrong field shape','skill_ids':12},
                 {'id':'invalid','description':'Too much authority','permissions':['publish_anything']},
                 {'id':'../escape','description':'Path traversal'}]
        for declaration in invalid:
            with self.subTest(declaration=declaration):
                with self.assertRaises(ValueError):catalog.create_agent(declaration)
        self.assertFalse((self.root/'company/agents/installed/invalid.json').exists())
        # An old malformed installed file is diagnosed without crashing discovery.
        (self.root/'company/agents/installed/broken.json').write_text('{"id":"broken","skill_ids":12}')
        self.assertNotIn('broken',available_agents(self.root))

    @scenario('creation.immutable_release_resolves_dependencies','context.profile_strategy_brand_scoped')
    def test_context_revisions_resolve_actual_company_content_and_stay_pinned(self):
        strategy=self.root/'company/strategy/direction.md'
        strategy.write_text('Prefer repeat customers. Do not publish customer records.\n')
        unrelated=self.root/'company/strategy/unrelated.md'
        unrelated.write_text('An unrelated confidential initiative.\n')
        spec=specification('host')
        name='strategy/direction.md';spec['context_versions']={name:hashlib.sha256(strategy.read_bytes()).hexdigest()}
        spec['execution']['critical_context']=[name]
        release=self.runtime.candidate(spec)
        strategy.write_text('A later changed direction.\n')
        case=spec['evaluation']['cases'][0]
        run=self.runtime.run(release,case['input'],request_key='pinned',candidate_case=case['id'])
        texts='\n'.join(row['text'] for row in run['assignment']['context']['documents'])
        self.assertIn('Do not publish customer records',texts)
        self.assertNotIn('later changed',texts)
        self.assertNotIn('unrelated confidential',texts)
        with self.assertRaisesRegex(ValueError,'revision'):
            spec['version']='2';self.runtime.candidate(spec)

    @scenario('creation.workflow_brief_examples_and_rubric','evaluation.reference_output_reproducible')
    def test_clean_installed_example_runs_the_script_and_checks_the_reference(self):
        from company.runtime.bootstrap import scaffold
        from company.commands.workflows import read_package
        from company.workflows.runs import LocalFileAdapter
        from company.security import CompanyAuthority
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();scaffold(root,keep_stale=True)
            spec=read_package(root,root/'company/workflows/sales-report/workflow.json')
            self.assertIn('baseline',spec['brief'])
            self.assertEqual(set(spec['definition_sources']),{'workflow.json','brief.md','evaluation/rubric.json',
                'evaluation/cases/example.json','evaluation/cases/unseen.json','evaluation/cases/refund.json'})
            authority=CompanyAuthority(root)
            runtime=WorkflowRuntime(root/'.spielos/state/workflows.sqlite',home=root,principal=authority.local_owner(),
                adapters={'local':LocalFileAdapter(root,spec)})
            release=runtime.candidate(spec)
            expected=json.loads((root/'company/workflows/sales-report/examples/output.json').read_text())
            run=runtime.run(release,json.loads((root/'company/workflows/sales-report/examples/input.json').read_text()),
                request_key='reproduce-example',candidate_case='example')
            self.assertEqual(run['output'],expected)
            self.assertEqual(runtime.evaluate_run(run['id'])['evaluation']['state'],'pass')
            script=root/'company/workflows/sales-report/execution/report.py'
            script.write_text(script.read_text()+'\n# Changed implementation\n')
            runtime.adapters['local']=LocalFileAdapter(root,spec)
            with self.assertRaisesRegex(ValueError,'changed'):
                runtime.run(release,{'title':'Later','sales':[1]},request_key='changed-code',candidate_case=None)

    @scenario('creation.bounded_godae_improvement')
    def test_godae_changes_a_workflow_with_two_harnesses_and_an_exact_file_boundary(self):
        from company.tests.test_bounded_workflow_runs import prepare_fixture_telemetry,verify_fixture_telemetry
        prepare_fixture_telemetry(self.runtime)
        from company.improvements import Improvements
        from .test_runtime import create_release
        build=Improvements(self.runtime);review=Improvements(self.review_runtime)
        brief={'name':'Accurate sales summary','business_need':'Finance needs a reliable report','owner':'Finance lead',
               'baseline':'unknown','target':'Correct sums and row counts','constraints':['Draft only'],
               'intended_users':['Finance lead'],'outcome_window':'Next weekly reporting cycle',
               'allowed_files':['workflows/sales-report/workflow.json','workflows/sales-report/execution/report.py']}
        item=build.create(brief)
        with self.assertRaises(ValueError):build.attach_candidate(item['id'],'invented',changed_files=['workflows/sales-report/workflow.json'])
        spec=specification()
        build.observe(item['id'],{'process':'Lead pastes the weekly rows','examples':['Provided report example'],
            'failures':['Missing rows','Negative total presented as growth'],'criterion_ids':[row['id'] for row in spec['evaluation']['criteria']],
            'evidence_sources':['Synthetic acceptance fixture; no real company baseline']})
        build.agree_architecture(item['id'],{'chosen_provider':'local','alternatives':['Host agent'],
            'tradeoffs':'Deterministic arithmetic is directly checkable','execution_contract':'JSON stdin/stdout',
            'evaluation_contract':'Independent accounting rules','cost_envelope':'Host subscription cost remains unknown',
            'permissions':[],'test_plan':['Representative','Held out','Refund negative','Timeout']})
        release=self.runtime.candidate(spec)
        with self.assertRaisesRegex(ValueError,'boundary'):build.attach_candidate(item['id'],release,changed_files=['AGENTS.md'])
        build.attach_candidate(item['id'],release,changed_files=brief['allowed_files'])
        with self.assertRaises(ValueError):review.decide(item['id'],decision='accept',reason='Looks plausible',candidate_runs={})
        runs={}
        for case in spec['evaluation']['cases']:
            run=self.runtime.run(release,case['input'],request_key='improvement-'+case['id'],candidate_case=case['id'])
            self.runtime.evaluate_run(run['id']);runs[case['id']]=run['id']
        verify_fixture_telemetry(self.runtime)
        accepted=review.decide(item['id'],decision='accept',reason='Actual cases and failure checks meet the agreed brief',candidate_runs=runs)
        self.assertEqual(accepted['stage'],'accepted')
        self.assertEqual(accepted['brief']['baseline'],'unknown')
        with self.runtime.connect() as connection:
            self.assertFalse(connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'core_goal%'").fetchall())
