"""Feedback scope, real context changes, artifacts, roles and remote failures."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from company.runtime.bootstrap import scaffold
from company.security import CompanyAuthority
from company.workflows.runs import WorkflowRuntime
from company.observability.sessions import Sessions, sanitize
from company.observability.langfuse import observation,scores
from company.tests.test_langfuse_export import MemoryLangfuse


class SessionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.home=Path(self.directory.name)/'home';scaffold(self.home,keep_stale=True)
        authority=CompanyAuthority(self.home)
        self.runtime=WorkflowRuntime(self.home/'.spielos/state/workflows.sqlite',home=self.home,principal=authority.local_owner())
        config={'enabled':True,'provider':'langfuse','project_id':'synthetic-project','base_url':'https://langfuse.invalid','payload_policy':'reviewed_evidence','require_verified_release':True}
        (self.home/'.spielos/telemetry.json').write_text(json.dumps(config))
        self.sessions=Sessions(self.runtime)
        self.session=self.sessions.start(host='codex',host_session='synthetic-host-session',role='director')

    def test_host_and_director_are_distinct_and_restart_preserves_one_session(self):
        same=self.sessions.start(host='codex',host_session='synthetic-host-session',role='director')
        agent=self.sessions.start(host='codex',host_session='synthetic-host-session',role='agent')
        self.assertEqual(same['id'],self.session['id']);self.assertNotEqual(agent['id'],same['id'])
        self.assertEqual(same['host'],'codex');self.assertEqual(same['role'],'director')

    def test_resume_retains_original_explicit_coverage(self):
        original=self.sessions.start(host='codex',host_session='explicit-coverage-session',coverage={'source':'Captured after work began; earlier activity is unknown'})
        resumed=self.sessions.start(host='codex',host_session='explicit-coverage-session')
        self.assertEqual(resumed['id'],original['id'])
        self.assertEqual(len(resumed['events']),1)
        self.assertEqual(resumed['events'][0]['record']['payload']['coverage'],original['events'][0]['record']['payload']['coverage'])

    def test_context_changes_include_actual_supplied_content_and_removals(self):
        self.sessions.context(self.session['id'],documents={'brief':'Draft order','brand':'Restrained motion'},request_key='before',reason='Initial order')
        self.sessions.context(self.session['id'],documents={'brief':'Slower transition for this order'},request_key='after',reason='Owner correction')
        value=self.sessions.show(self.session['id'])['events'][-1]['record']['payload']
        self.assertEqual(value['removed'],['brand']);self.assertEqual(value['added_or_changed'],['brief'])
        self.assertEqual(value['documents']['brief']['text'],'Slower transition for this order')

    def test_feedback_requires_a_scope_target_interpretation_and_effect(self):
        from company.tests.test_bounded_workflow_runs import manifest,identity
        from company.workflows.runs import LocalAdapter
        self.runtime.adapters['local']=LocalAdapter(identity)
        release=self.runtime.candidate(manifest())
        run=self.runtime.run(release,{'text':'one'},request_key='order',candidate_case='reference')
        target={'kind':'run','id':run['id']}
        with self.assertRaises(ValueError):self.sessions.record(self.session['id'],kind='feedback',request_key='bad',payload={'message':'Slower'})
        event=self.sessions.record(self.session['id'],kind='feedback',request_key='correction',target=target,
            payload={'message':'Slower for this order only','scope':'run','interpretation':'Revise this order’s preview','effect':'Create another preview; reusable workflow stays pinned'})
        self.assertEqual(event['payload']['scope'],'run')
        self.assertEqual(self.runtime.get(run['id'])['inputs'],{'text':'one'})
        self.assertEqual(self.runtime.get(run['id'])['release_digest'],release)
        with self.assertRaisesRegex(ValueError,'different evidence'):
            self.sessions.record(self.session['id'],kind='feedback',request_key='correction',target=target,
                payload={'message':'Different correction','scope':'run','interpretation':'Another correction','effect':'New preview'})

    def test_artifact_lineage_measures_bytes_and_rejects_external_or_secret_files(self):
        path=self.home/'.spielos/artifacts/preview.html';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('<h1>Draft preview</h1>')
        context=self.sessions.context(self.session['id'],documents={'brief':'Readable title'},request_key='brief',reason='Order')
        event=self.sessions.artifact(self.session['id'],path=path,purpose='Actual preview for readable-title review',request_key='preview',caused_by=context['id'])
        self.assertEqual(event['payload']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):self.sessions.artifact(self.session['id'],path=self.home/'.spielos/security/authority.key',purpose='Should never export',request_key='secret')
        outside=Path(self.directory.name)/'outside.txt';outside.write_text('Outside')
        with self.assertRaises(ValueError):self.sessions.artifact(self.session['id'],path=outside,purpose='Outside',request_key='outside')

    def test_sent_is_not_verified_and_loss_does_not_duplicate_observations(self):
        client=MemoryLangfuse(lost=True)
        self.sessions.export(client)
        self.assertFalse(self.sessions.show(self.session['id'])['observable'])
        self.sessions.export(client)
        self.assertTrue(self.sessions.show(self.session['id'])['observable'])
        self.assertEqual(len(client.observations),1)

    def test_inspectable_trace_contains_actual_context_and_unknown_tokens_remain_unknown(self):
        self.sessions.context(self.session['id'],documents={'brief':'Readable title'},request_key='context',reason='Current order')
        with self.runtime.connect() as connection:
            event=json.loads(connection.execute('SELECT payload_json FROM activity_exports ORDER BY rowid DESC LIMIT 1').fetchone()[0])
        wire=json.dumps(observation(event))
        self.assertIn('Readable title',wire);self.assertIn('reviewed_evidence',wire)
        self.assertNotIn('gen_ai.usage.input_tokens',wire)
        self.assertEqual(sanitize({'api_key':'private-value','text':'NPM_TOKEN=private-value'}),{'api_key':'[redacted]','text':'[redacted]'})

    def test_local_system_change_cannot_claim_remote_qualification(self):
        from company.operations import require_activity_telemetry
        with self.assertRaisesRegex(ValueError,'readback'):require_activity_telemetry(self.runtime,self.session['id'])

    def test_numeric_rating_scores_the_actual_target_observation(self):
        from company.observability.langfuse import identities
        event=self.sessions.context(self.session['id'],documents={'brief':'Readable title'},request_key='rated-context',reason='Review')
        rating=self.sessions.record(self.session['id'],kind='rating',request_key='owner-rating',target={'kind':'event','id':event['id']},payload={
            'criterion':'context-fidelity','value':1.0,'reason':'The captured brief preserves the requested readable title.'})
        with self.runtime.connect() as connection:
            target=json.loads(connection.execute('SELECT payload_json FROM activity_exports WHERE id=?',(event['id'],)).fetchone()[0])
            rated=json.loads(connection.execute('SELECT payload_json FROM activity_exports WHERE id=?',(rating['id'],)).fetchone()[0])
        score=scores(rated)[0];trace,span=identities(target)
        self.assertEqual((score['traceId'],score['observationId']),(trace,span))
        self.assertEqual(score['dataType'],'NUMERIC');self.assertEqual(score['value'],1.0)

    def test_private_file_tool_results_are_excluded_before_journaling(self):
        from company.observability.sessions import capture_hook
        opaque='0123456789abcdef'*4
        activity=capture_hook(self.home,{'session_id':'private-tool-fixture','hook_event_name':'PostToolUse',
            'tool_name':'read_file','tool_use_id':'one','tool_input':{'path':str(self.home/'.spielos/security/authority.key')},'tool_response':opaque},host='codex')
        snapshot=self.sessions.show(activity['session_id'])
        self.assertNotIn(opaque,json.dumps(snapshot))
        self.assertIn('arguments and result excluded',json.dumps(snapshot))

    def test_pending_system_change_can_be_revised_without_erasing_prior_evidence(self):
        from company.improvements import Improvements
        self.runtime.activity_session_id=self.session['id'];development=Improvements(self.runtime)
        item=development.create({'name':'Synthetic privacy correction','business_need':'Preserve draft revision evidence','owner':'Synthetic owner','baseline':'unknown','target':'A revised draft with preserved history','constraints':['Draft only'],'intended_users':['Reviewer'],'outcome_window':'This test','allowed_files':['policy.md']})
        development.observe(item['id'],{'process':'Edit a bounded policy','examples':['Private files excluded'],'failures':['A raw secret was journaled'],'criterion_ids':['private-file-exclusion'],'evidence_sources':['Actual local check']})
        development.agree_architecture(item['id'],{'chosen_provider':'local','alternatives':['No change'],'tradeoffs':'Preserve the earlier report','execution_contract':'Bounded policy change','evaluation_contract':'Actual content comparison','cost_envelope':'Local test','permissions':[],'test_plan':['Policy comparison']})
        policy=self.home/'policy.md';policy.write_text('Exclude private files.')
        evidence=self.home/'.spielos/acceptance/privacy-check.json';evidence.parent.mkdir(exist_ok=True)
        evidence.write_text(json.dumps({'standard':'spielos-evaluation/2','subject':'system_improvement','checks':[{
            'question':'Does the policy exclude private files?','expected':'Exclude private files.','actual':policy.read_text(),'evidence':'Actual policy content comparison','passed':policy.read_text()=='Exclude private files.'}]}))
        previous=development.attach_change(item['id'],root=self.home,changed_files=['policy.md'],evidence_files=[str(evidence)])['change_evidence']
        revised=development.revise(item['id'],reason='Add an explicit credential-result exclusion before review')
        self.assertEqual(revised['stage'],'act');self.assertEqual(revised['revisions'][0]['previous_evidence'],previous)
        self.assertIn('fresh evidence',revised['revisions'][0]['acceptance'])
        self.assertNotEqual(revised['stage'],'accepted')

    def test_operation_and_run_can_be_traced_to_their_session(self):
        from company.improvements import Improvements
        self.runtime.activity_session_id=self.session['id']
        item=Improvements(self.runtime).create({'name':'Synthetic correction','business_need':'Exercise traced operation','owner':'Synthetic owner','baseline':'unknown','target':'Recorded causal decision','constraints':['Draft'],'intended_users':['Reviewer'],'outcome_window':'This test','allowed_files':['policy.md']})
        event=self.sessions.show(self.session['id'])['events'][-1]['record']['payload']
        self.assertEqual(event['operation'],'improvement_create');self.assertEqual(event['subject'],item['id'])
