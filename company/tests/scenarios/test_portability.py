"""A second company adopts definitions without executing import-time code or inheriting approvals."""
from pathlib import Path
import hashlib,json,tempfile
from company.home import CompanyHome
from company.security import CompanyAuthority
from company.portability import PortablePackages,package_inventory
from company.commands.workflows import read_package
from company.workflows.runs import WorkflowRuntime,LocalFileAdapter
from company.runtime.bootstrap import scaffold
from .test_home import scenario
from .test_runtime import WorkspaceJourney


class PortabilityJourneys(WorkspaceJourney):
    def transfer(self):
        source=self.root/'producer';scaffold(source,keep_stale=True)
        authority=CompanyAuthority(source)
        exporter=PortablePackages(source,authority.local_owner())
        bundle=self.root/'bundle'
        exported=exporter.export_workflow('sales-report',bundle,package_id='reporting-starter')
        # The adopter is genuinely independent and starts without the shipped
        # workflow example, so this tests installation rather than file reuse.
        adopter=self.root/'adopter';CompanyHome(adopter).initialize_content()
        authority=CompanyAuthority(adopter);authority.bootstrap()
        # Existing initialized draft starter files can be reused without a new
        # package claiming ownership; use a distinct package workflow identity.
        manifest=json.loads((bundle/'content/workflows/sales-report/workflow.json').read_text())
        manifest['id']='adopted-report'
        old=bundle/'content/workflows/sales-report';old.rename(old.with_name('adopted-report'))
        path=bundle/'content/workflows/adopted-report/workflow.json';path.write_text(json.dumps(manifest,indent=2)+'\n')
        declaration=exported['manifest'];declaration['workflows']=['adopted-report']
        declaration['files']={name.replace('workflows/sales-report/','workflows/adopted-report/'):
            hashlib.sha256((bundle/'content'/name.replace('workflows/sales-report/','workflows/adopted-report/')).read_bytes()).hexdigest()
            for name in declaration['files']}
        (bundle/'package.json').write_text(json.dumps(declaration,indent=2)+'\n')
        return bundle,adopter,authority,PortablePackages(adopter,authority.local_owner())

    @scenario('portability.no_submitted_code_executes_on_import','portability.ownership_receipt_and_collision_preview','portability.clean_adopter_reproduces_example')
    def test_adopter_previews_installs_and_then_explicitly_runs_the_example(self):
        bundle,home,authority,packages=self.transfer()
        marker=self.root/'import-was-executed'
        # A top-level payload in a script would run if an importer inspected it
        # through importlib. It must remain inert until explicit execution.
        script=bundle/'content/workflows/adopted-report/execution/report.py'
        original=script.read_text()
        script.write_text("from pathlib import Path\nPath("+repr(str(marker))+").write_text('executed')\n"+original.replace('"""Generic draft example: aggregate the explicit sales rows without external effects."""\n',''))
        manifest=json.loads((bundle/'package.json').read_text());name='workflows/adopted-report/execution/report.py'
        manifest['files'][name]=hashlib.sha256(script.read_bytes()).hexdigest();(bundle/'package.json').write_text(json.dumps(manifest))
        preview=packages.preview(bundle)
        self.assertFalse(marker.exists())
        self.assertFalse((home/'company/workflows/adopted-report').exists())
        receipt=packages.install(preview['plan'],expected_digest=preview['digest'])
        self.assertFalse(marker.exists())
        self.assertIn(name,receipt['owned_files'])
        self.assertEqual(receipt['production_releases_created'],0)
        spec=read_package(home,home/'company/workflows/adopted-report/workflow.json')
        runtime=WorkflowRuntime(home/'.spielos/state/workflows.sqlite',home=home,principal=authority.local_owner(),adapters={'local':LocalFileAdapter(home,spec)})
        release=runtime.candidate(spec);case=next(row for row in spec['evaluation']['cases'] if row['id']=='example')
        run=runtime.run(release,case['input'],request_key='adopter-example',candidate_case='example')
        self.assertTrue(marker.exists())
        self.assertEqual(run['output'],case['reference'])
        self.assertEqual(runtime.evaluate_run(run['id'])['evaluation']['state'],'pass')
        with self.assertRaises(ValueError):runtime.run(release,case['input'],request_key='unapproved-production')

    @scenario('portability.contained_paths_and_symlinks','security.secret_references_not_exported')
    def test_escape_paths_links_and_connection_secrets_are_refused(self):
        bundle,home,authority,packages=self.transfer()
        path=bundle/'package.json';manifest=json.loads(path.read_text())
        original=dict(manifest['files'])
        for name in ('../outside.py','/tmp/outside.py','skills/../../outside.py','brand/.env'):
            manifest['files']={name:'a'*64};path.write_text(json.dumps(manifest))
            with self.subTest(name=name):
                with self.assertRaises(ValueError):packages.preview(bundle)
        manifest['files']=dict(original)
        connection=bundle/'content/connections/reporting.json';connection.parent.mkdir(parents=True,exist_ok=True)
        connection.write_text(json.dumps({'id':'reporting','provider':'synthetic','credential_ref':'REPORTING_TOKEN','secret_key':'synthetic-forbidden-value'}))
        manifest['files']['connections/reporting.json']=hashlib.sha256(connection.read_bytes()).hexdigest()
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'never credentials'):packages.preview(bundle)
        connection.unlink()
        manifest['files']=original;path.write_text(json.dumps(manifest))
        source=bundle/'content/workflows/adopted-report/execution/report.py';source.unlink();source.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):packages.preview(bundle)

    @scenario('portability.ownership_receipt_and_collision_preview')
    def test_owner_edits_after_preview_block_install_without_overwriting(self):
        bundle,home,authority,packages=self.transfer()
        preview=packages.preview(bundle)
        target=home/'company/workflows/adopted-report/brief.md';target.parent.mkdir(parents=True)
        target.write_text('Owner started a different brief.')
        with self.assertRaises(FileExistsError):packages.install(preview['plan'],expected_digest=preview['digest'])
        self.assertEqual(target.read_text(),'Owner started a different brief.')

    @scenario('portability.atomic_install_and_recovery')
    def test_interrupted_transfer_is_closed_to_execution_until_exact_recovery(self):
        bundle,home,authority,packages=self.transfer();preview=packages.preview(bundle)
        def crash(index):raise RuntimeError('Synthetic interruption after one installed file')
        with self.assertRaises(RuntimeError):packages.install(preview['plan'],expected_digest=preview['digest'],after_operation=crash)
        with self.assertRaisesRegex(ValueError,'recovery'):CompanyHome(home).require_ready()
        receipt=packages.install(preview['plan'],expected_digest=preview['digest'])
        CompanyHome(home).require_ready()
        for name,expected in receipt['owned_files'].items():self.assertEqual(hashlib.sha256((home/'company'/name).read_bytes()).hexdigest(),expected)
        self.assertEqual(packages.install(preview['plan'],expected_digest=preview['digest']),receipt)
        self.assertEqual(receipt['external_effects'],0)

    @scenario('portability.legacy_history_readonly')
    def test_legacy_history_remains_readable_without_resuming_its_intent(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from company.__main__ import main,legacy_history
        from company.state import Database
        from company.workflows.runs import stamp
        database=self.root/'.spielos/state/company.sqlite';legacy=Database(database)
        with legacy.connect() as connection:
            connection.execute('INSERT INTO core_goals VALUES(?,?,?,?,?,?,?,?,?)',
                ('legacy-objective','Earlier customer objective','customers','ge','10',None,'active',stamp(),stamp()))
        before=hashlib.sha256(database.read_bytes()).hexdigest()
        history=legacy_history(self.root,kind='goals')
        self.assertEqual(history['records'][0]['name'],'Earlier customer objective')
        self.assertIn('never resumed',history['policy'])
        with redirect_stdout(StringIO()):
            self.assertEqual(main(['history','--home',str(self.root),'--json']),0)
        self.assertEqual(before,hashlib.sha256(database.read_bytes()).hexdigest())
        with self.runtime.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM workflow_invocations WHERE id='legacy-objective'").fetchone()[0],0)
