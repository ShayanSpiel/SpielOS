"""A repeat request receives causal learning and the owner's current constraints."""
from company.context.workflow import WorkflowMemory,projection,owner_context
from .test_home import scenario
from .test_runtime import WorkspaceJourney,specification,create_release,report


class ContextJourneys(WorkspaceJourney):
    @scenario('context.memory_citations_and_versions','context.owner_preferences_do_not_starve_learning','context.retired_unrelated_memory_excluded')
    def test_next_report_uses_a_cited_lesson_even_with_many_preferences(self):
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        first=self.runtime.run(release,{'title':'First week','sales':[3,8]},request_key='first')
        self.runtime.evaluate_run(first['id'])
        memory=WorkflowMemory(self.runtime)
        lesson=memory.add(scope='workflow',workflow_id='sales-report',claim='Keep refund rows explicit before interpreting positive totals.',evidence_runs=[first['id']])
        retired=memory.add(scope='workflow',workflow_id='sales-report',claim='An outdated accounting rule.',evidence_runs=[first['id']])
        memory.retire(retired['id'],reason='The owner replaced this accounting rule.')
        for index in range(30):memory.add(scope='owner',claim='Display preference '+str(index),source='Explicit owner preference')
        with self.assertRaises(ValueError):
            memory.add(scope='workflow',workflow_id='another-report',claim='Unrelated learning',evidence_runs=[first['id']])
        # Different workflow learning is not allowed to enter this report's scope.
        with self.runtime.connect() as connection:
            connection.execute("INSERT INTO workflow_memories(id,scope,workflow_id,claim,evidence_json,source,actor,created_at,status) VALUES('unrelated','workflow','another-report','Private unrelated lesson','[]',NULL,'fixture','2026','active')")
        next_run=self.runtime.run(release,{'title':'Next week','sales':[13]},request_key='second')
        claims=next_run['memory_snapshot']
        self.assertIn(lesson['claim'],[row['claim'] for row in claims])
        self.assertNotIn(retired['claim'],[row['claim'] for row in claims])
        self.assertNotIn('Private unrelated lesson',[row['claim'] for row in claims])
        cited=next(row for row in claims if row['id']==lesson['id'])
        self.assertEqual(cited['evidence'][0]['run_id'],first['id'])
        self.assertEqual(cited['evidence'][0]['release_digest'],release)
        memory.retire(lesson['id'],reason='Superseded after this report started.')
        self.assertIn(lesson['id'],[row['id'] for row in self.open(self.owner).get(next_run['id'])['memory_snapshot']])

    @scenario('context.context_budget_preserves_critical_constraints')
    def test_small_context_budgets_never_silently_drop_mandatory_policy(self):
        documents={'policy':{'source':'company/strategy/policy.md','sha256':'synthetic-policy','text':'Never publish customer records.'},
                   'reference':{'source':'company/brand/long-example.md','sha256':'synthetic-example','text':'Long examples. '*200}}
        value=projection(documents,token_budget=100,critical=['policy'])
        self.assertEqual([row['name'] for row in value['documents']],['policy'])
        self.assertEqual(value['omitted'],['reference'])
        with self.assertRaisesRegex(ValueError,'mandatory'):projection(documents,token_budget=1,critical=['policy'])
        with self.assertRaisesRegex(ValueError,'missing'):projection(documents,critical=['absent'])

    @scenario('context.restart_restores_pending_work','context.owner_voice_and_machine_reference')
    def test_owner_sees_pending_report_after_restart_without_internal_syntax(self):
        release,_=create_release(self.runtime,specification('host'),reviewer_runtime=self.review_runtime)
        pending=self.runtime.run(release,{'title':'Next month','sales':[7,14]},request_key='waiting')
        restored=self.open(self.owner)
        text=owner_context(restored)['text']
        human,machine=text.rsplit('\nMachine reference: ',1)
        self.assertIn('waiting for its assigned executor',human)
        self.assertNotIn(pending['id'],human)
        self.assertNotIn('awaiting_provider',human)
        self.assertNotIn('--',human)
        self.assertIn(pending['id'],machine)
        self.assertEqual(text.count('Machine reference:'),1)
        claimed=restored.claim(pending['id'])
        self.assertIn('sales-summary',str(claimed['assignment']))

    @scenario('context.memory_citations_and_versions')
    def test_runtime_never_infers_a_strategy_or_lesson_from_repetition(self):
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        for number in range(3):
            run=self.runtime.run(release,{'title':'Routine report','sales':[number]},request_key='routine-'+str(number))
            self.runtime.evaluate_run(run['id'])
            self.review_runtime.review(run['id'],decision='accept')
        self.assertEqual(WorkflowMemory(self.runtime).active('sales-report',scopes=('owner','strategy','workflow')),[])

    @scenario('context.typed_profile_and_owner_boundaries')
    def test_owner_facts_are_typed_in_one_document_and_notes_are_preserved(self):
        from company.home import CompanyProfile
        profile=CompanyProfile(self.root,self.owner)
        self.assertEqual(profile.read()['state'],'needs_owner_input')
        path=self.root/'company/profile.md'
        path.write_text(path.read_text()+'\n## Owner notes\n\nKeep this original note.\n')
        value=profile.update({'name':'Synthetic example company','audience':'Local service customers','owner':'Accountable founder',
            'responsibilities':['Prepare accurate draft reports'],'boundaries':['Do not publish customer data','Do not infer revenue impact']},
            source='Explicit synthetic owner intake',runtime=self.runtime)
        self.assertEqual(value['state'],'provided')
        self.assertEqual(value['fields']['boundaries'],['Do not publish customer data','Do not infer revenue impact'])
        self.assertIn('Keep this original note.',path.read_text())
        with self.assertRaises(PermissionError):CompanyProfile(self.root,self.reviewer).update({'name':'Forged identity'},source='Not the owner',runtime=self.review_runtime)
        self.assertFalse((self.root/'company/profile.json').exists())
