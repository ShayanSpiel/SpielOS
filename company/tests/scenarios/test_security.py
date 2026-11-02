"""Real authentication and company/role boundaries; no mocked identity proof."""
from pathlib import Path
from dataclasses import replace
import json,tempfile,unittest
from company.home import CompanyHome
from company.security import CompanyAuthority
from .test_home import scenario

class CompanySecurityJourneys(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        CompanyHome(self.root).initialize_content()
        self.authority=CompanyAuthority(self.root);self.authority.bootstrap()
        self.owner=self.authority.local_owner()

    @scenario('security.authenticated_company_principals')
    def test_owner_provisions_a_bounded_reviewer_without_storing_plaintext(self):
        token=self.authority.issue(self.owner,subject='reviewer-a',roles=['reviewer'])
        reviewer=self.authority.authenticate(token)
        self.assertEqual(self.authority.authorize(reviewer,'review'),'reviewer-a')
        self.assertNotIn(token,self.authority.policy_path.read_text())
        with self.assertRaises(PermissionError):self.authority.authenticate('wrong-credential')
        self.authority.revoke(self.owner,'reviewer-a')
        with self.assertRaises(PermissionError):self.authority.authorize(reviewer,'review')
        with self.assertRaises(PermissionError):self.authority.authenticate(token)

    @scenario('security.cross_company_and_role_denial')
    def test_reader_cannot_run_or_approve_and_principal_cannot_cross_company(self):
        token=self.authority.issue(self.owner,subject='reader',roles=['viewer'])
        reader=self.authority.authenticate(token)
        self.authority.authorize(reader,'read')
        for action in ('approve','run','configure'):
            with self.assertRaises(PermissionError):self.authority.authorize(reader,action)
        with self.assertRaises(PermissionError):self.authority.authorize(replace(reader,roles=('owner',)),'configure')
        other=self.root/'other';CompanyHome(other).initialize_content()
        second=CompanyAuthority(other);second.bootstrap()
        with self.assertRaises(PermissionError):second.authorize(self.owner,'read')

    @scenario('security.authenticated_company_principals')
    def test_expired_or_unprotected_authentication_is_refused(self):
        token=self.authority.issue(self.owner,subject='expired',roles=['viewer'])
        policy=json.loads(self.authority.policy_path.read_text())
        policy['bearer_principals']['expired']['expires_at']=1
        self.authority.policy_path.write_text(json.dumps(policy))
        with self.assertRaises(PermissionError):self.authority.authenticate(token)
        self.authority.key_path.chmod(0o644)
        with self.assertRaises(PermissionError):self.authority.local_owner()


from .test_runtime import WorkspaceJourney


class GovernedActionJourneys(WorkspaceJourney):
    @scenario('security.exact_action_content_destination_scope','security.restoration_preserves_history_and_no_effect_replay')
    def test_exact_approval_dispatches_once_and_restored_unknown_effect_is_not_replayed(self):
        import shutil
        from company.workflows.runs import WorkflowRuntime,digest
        from .test_runtime import create_release
        class Effect:
            timeout_seconds=1
            def __init__(self):self.starts=[];self.inspections=[]
            def start(self,**kwargs):self.starts.append(kwargs);raise OSError('Synthetic lost response after possible publication')
            def inspect(self,**kwargs):self.inspections.append(kwargs);return {'status':'unknown','handle':kwargs['handle']}
        provider=Effect();self.runtime.effect_adapters['synthetic']=provider
        release,_=create_release(self.runtime,reviewer_runtime=self.review_runtime)
        run=self.runtime.run(release,{'title':'Accepted draft','sales':[4,8]},request_key='draft-for-publication')
        self.runtime.evaluate_run(run['id']);self.review_runtime.review(run['id'],decision='accept')
        action={'action':'publish','destination':'https://synthetic.invalid/reports/weekly',
                'content_digest':digest(run['output']),'scope':'One reviewed weekly report'}
        with self.assertRaises(PermissionError):self.runtime.execute_action(run['id'],action,adapter='synthetic')
        self.runtime.approve_action(run['id'],action,decision='approve')
        for key,value in [('destination','https://another.invalid/'),('scope','All reports'),('action','send_email'),('content_digest',digest({'changed':'output'}))]:
            with self.subTest(key=key):
                with self.assertRaises((PermissionError,ValueError)):
                    self.runtime.execute_action(run['id'],{**action,key:value},adapter='synthetic')
        first=self.runtime.execute_action(run['id'],action,adapter='synthetic')
        self.assertEqual(first['status'],'awaiting_reconciliation')
        duplicate=self.runtime.execute_action(run['id'],action,adapter='synthetic')
        self.assertEqual(first['id'],duplicate['id']);self.assertEqual(len(provider.starts),1)
        snapshot=self.runtime.snapshot(self.root/'.spielos/state/explicit-recovery.sqlite')
        restored=WorkflowRuntime(snapshot['path'],home=self.root,principal=self.owner,
            adapters={'local':self.adapter},effect_adapters={'synthetic':provider})
        self.assertEqual(restored.get(run['id'])['status'],'completed')
        self.assertEqual(restored.reconcile_action(first['id'])['status'],'awaiting_reconciliation')
        self.assertEqual(len(provider.starts),1);self.assertEqual(len(provider.inspections),1)
        # Reopening a copied database under another company's credentials is denied.
        other=self.root/'other-company';CompanyHome(other).initialize_content()
        other_authority=CompanyAuthority(other);other_authority.bootstrap()
        destination=other/'.spielos/state/copied.sqlite';destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(snapshot['path'],destination)
        with self.assertRaises(PermissionError):WorkflowRuntime(destination,home=other,principal=other_authority.local_owner())
