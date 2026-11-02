"""Realistic migration journeys use actual directories and preserved bytes."""
from pathlib import Path
import json
import tempfile
import unittest
from company.home import CompanyHome,fingerprint


def scenario(*ids):
    def decorate(function):
        function.scenarios=ids
        return function
    return decorate


class LeanHomeJourneys(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        runtime=self.root/'.agents/company'
        runtime.mkdir(parents=True)
        (runtime/'__main__.py').write_text('# Synthetic runtime marker\n')
        for layer in ('departments','skills','connections','strategy','agents/installed','brand'):
            (runtime/layer).mkdir(parents=True,exist_ok=True)
        (runtime/'skills/core.py').write_text('# runtime core\n')
        (runtime/'skills/research').mkdir()
        (runtime/'skills/research/SKILL.md').write_text('Use the verified source; cite the evidence.\n')
        (runtime/'departments/research').mkdir()
        (runtime/'departments/research/department.py').write_text('# Synthetic owner declaration\n')
        (runtime/'strategy/direction.md').write_text('Prefer repeat customers; baseline is unknown.\n')
        (runtime/'brand/voice.md').write_text('Owner voice: short and direct.\n')
        (runtime/'agents/installed/reporter.json').write_text('{"id":"reporter"}\n')
        (runtime/'connections/reporting.json').write_text('{"secret_ref":"REPORTING_TOKEN"}\n')
        (self.root/'.spielos/state').mkdir(parents=True)
        (self.root/'.spielos/state/history.fixture').write_bytes(b'Historical evidence must not change')
        self.home=CompanyHome(self.root)

    @scenario('home.reviewed_hash_bound_migration','home.update_preserves_owner_content')
    def test_a_pre_receipt_shipped_placeholder_is_not_mistaken_for_owner_content(self):
        marker=self.root/'.agents/company/agents/installed/.gitkeep';marker.write_bytes(b'')
        plan=self.home.migration_plan()
        self.assertFalse(any(row['from']=='agents/installed/.gitkeep' for row in plan['moves']))
        marker.write_text('Actual owner content differs from the shipped empty placeholder.')
        changed=self.home.migration_plan()
        self.assertTrue(any(row['from']=='agents/installed/.gitkeep' for row in changed['moves']))

    @scenario('home.runtime_hidden_and_legacy_aliases','home.brand_is_owner_owned')
    def test_founder_sees_company_content_and_original_brand_voice(self):
        plan=self.home.migration_plan()
        self.home.apply_migration(plan,expected_digest=fingerprint(plan))
        self.assertTrue(self.home.lean)
        for layer in ('strategy','brand','workflows','agents','skills','connections','departments'):
            self.assertTrue((self.root/'company'/layer).is_dir())
        for layer in ('assets','design-system','templates','examples'):
            self.assertTrue((self.root/'company/brand'/layer).is_dir())
        self.assertEqual((self.root/'company/brand/voice.md').read_text(),'Owner voice: short and direct.\n')
        self.assertTrue((self.root/'.agents/company').is_symlink())
        self.assertTrue((self.root/'.spielos/runtime/company/skills/core.py').is_file())
        self.assertEqual((self.root/'.agents/company/skills/research/SKILL.md').read_bytes(),
                         (self.root/'company/skills/research/SKILL.md').read_bytes())
        self.assertFalse((self.root/'company/skills/core.py').exists())

    @scenario('home.reviewed_hash_bound_migration')
    def test_preview_is_read_only_and_migration_moves_without_copies(self):
        plan=self.home.migration_plan()
        self.assertFalse((self.root/'company').exists())
        self.assertFalse((self.root/'.spielos/migration.json').exists())
        with self.assertRaises(ValueError):self.home.apply_migration(plan,expected_digest='unreviewed')
        result=self.home.apply_migration(plan,expected_digest=fingerprint(plan))
        self.assertGreater(result['owner_files'],0)
        self.assertEqual((self.root/'.spielos/state/history.fixture').read_bytes(),b'Historical evidence must not change')
        self.assertTrue((self.root/'.spielos/runtime/company/brand/voice.md').is_symlink())
        (self.root/'company/brand/voice.md').write_text('Updated owner rule\n')
        self.home.initialize_content()
        self.assertEqual((self.root/'company/brand/voice.md').read_text(),'Updated owner rule\n')
        self.assertFalse(any('backup' in path.name for path in self.root.rglob('*')))

    @scenario('home.migration_collision_refused')
    def test_existing_company_strategy_is_never_overwritten(self):
        target=self.root/'company/strategy/direction.md'
        target.parent.mkdir(parents=True)
        target.write_text('A different owner document\n')
        with self.assertRaisesRegex(ValueError,'collision'):self.home.migration_plan()
        self.assertEqual(target.read_text(),'A different owner document\n')

    @scenario('home.migration_restart_recovery')
    def test_power_loss_after_first_move_resumes_the_exact_plan(self):
        plan=self.home.migration_plan()
        def crash(index):raise RuntimeError('synthetic interruption')
        with self.assertRaises(RuntimeError):
            self.home.apply_migration(plan,expected_digest=fingerprint(plan),after_operation=crash)
        self.assertFalse(self.home.lean)
        recovered=self.home.apply_migration(plan,expected_digest=fingerprint(plan))
        self.assertTrue(self.home.lean)
        self.assertEqual(recovered['moved'],len(plan['moves']))
        self.assertEqual(json.loads((self.root/'.spielos/migration.json').read_text())['status'],'complete')

    @scenario('home.reviewed_hash_bound_migration')
    def test_owner_edit_after_preview_invalidates_the_plan(self):
        plan=self.home.migration_plan()
        (self.root/'.agents/company/strategy/direction.md').write_text('Owner changed direction\n')
        with self.assertRaisesRegex(ValueError,'changed since'):
            self.home.apply_migration(plan,expected_digest=fingerprint(plan))
        self.assertFalse((self.root/'.spielos/runtime/company').exists())

    @scenario('home.source_boundary_refused')
    def test_source_checkout_cannot_receive_company_content(self):
        (self.root/'.spielos-boundary.json').write_text('{"role":"source"}')
        with self.assertRaisesRegex(ValueError,'source'):self.home.initialize_content()
        self.assertFalse((self.root/'company').exists())

class InstallationJourneys(unittest.TestCase):
    @scenario('home.fresh_visible_lean_structure','home.update_preserves_owner_content')
    def test_fresh_install_update_and_restart_from_another_directory(self):
        import os, subprocess, sys
        from company.runtime.bootstrap import scaffold
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'home'
            receipt=scaffold(root,keep_stale=True)
            self.assertEqual(receipt['layout'],'lean')
            home=CompanyHome(root)
            self.assertTrue((home.runtime/'runtime/paths.py').is_file())
            voice=home.content/'brand/voice.md'
            voice.write_text('Approved company voice, owned by founder.\n')
            strategy=home.content/'strategy/direction.md'
            strategy.write_text('Repeat customers before acquisition.\n')
            private=root/'.spielos/state/history.fixture'
            private.write_bytes(b'Original accepted evidence')
            scaffold(root,force=True,keep_stale=True)
            self.assertEqual(voice.read_text(),'Approved company voice, owned by founder.\n')
            self.assertEqual(strategy.read_text(),'Repeat customers before acquisition.\n')
            self.assertEqual(private.read_bytes(),b'Original accepted evidence')
            result=subprocess.run([sys.executable,'-B','-c',
                'from company.runtime.paths import find_project_root; print(find_project_root())'],
                cwd=directory,env={**os.environ,'PYTHONPATH':str(root/'.agents'),
                                  'SPIELOS_HOME':str(Path(directory)/'wrong-home')},
                text=True,capture_output=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),str(root.resolve()))
            self.assertFalse((home.content/'runtime').exists())

    @scenario('home.update_preserves_owner_content')
    def test_release_cannot_take_over_an_owner_filename(self):
        import os, shutil
        from unittest.mock import patch
        from company.runtime.bootstrap import scaffold,template_root
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'home'
            scaffold(root,keep_stale=True)
            owner=root/'.agents/company/owner_extension.py'
            owner.write_text('# The owner wrote this extension\n')
            template=base/'release'
            shutil.copytree(template_root(),template)
            (template/'agents/company/owner_extension.py').write_text('# Product collision\n')
            with patch.dict(os.environ,{'SPIELOS_TEMPLATE_DIR':str(template)}):
                with self.assertRaisesRegex(FileExistsError,'collides'):
                    scaffold(root,force=True,keep_stale=True)
            self.assertEqual(owner.read_text(),'# The owner wrote this extension\n')


class LegacyContextMigrationJourneys(unittest.TestCase):
    setUp=LeanHomeJourneys.setUp
    @scenario('home.legacy_state_and_memory_inventory')
    def test_owner_preferences_survive_without_broadening_task_lessons_or_old_approvals(self):
        from company.state import Database
        from company.workflows.runs import WorkflowRuntime,stamp
        from company.context.workflow import WorkflowMemory
        from company.security import CompanyAuthority
        database=Database(self.root/'.spielos/state/company.sqlite')
        with database.connect() as connection:
            connection.execute('INSERT INTO core_goals VALUES(?,?,?,?,?,?,?,?,?)',('earlier-goal','Earlier customer task','customers','ge','1',None,'active',stamp(),stamp()))
            for identity,scope,claim in [('preference','owner','preferences.writing_style="Concise"'),('task-lesson','workflow','Keep the original task-specific context'),('strategy','strategy','Earlier direction requiring review')]:
                connection.execute('''INSERT INTO core_memory
                    (id,scope,claim,goal_id,evidence_ids_json,created_at,status) VALUES(?,?,?,?,?,?,?)''',
                    (identity,scope,claim,None if scope=='owner' else 'earlier-goal','[]',stamp(),'active'))
        original=(self.root/'.spielos/state/company.sqlite').read_bytes()
        plan=self.home.migration_plan()
        self.assertEqual(len(plan['legacy_state']['tables']['core_memory']),3)
        self.home.apply_migration(plan,expected_digest=fingerprint(plan))
        authority=CompanyAuthority(self.root)
        runtime=WorkflowRuntime(self.root/'.spielos/state/workflows.sqlite',home=self.root,principal=authority.local_owner())
        memory=WorkflowMemory(runtime)
        self.assertEqual(memory.active('new-workflow',scopes=('owner','workflow','strategy')),[])
        self.assertEqual(memory.summary()['counts']['owner'],1)
        with runtime.connect() as connection:
            preserved=connection.execute("SELECT id,claim FROM workflow_memories WHERE scope='owner'").fetchone()
        self.assertIn('Concise',preserved['claim'])
        memory.classify(preserved['id'],category='preference',reason='Reviewed explicit synthetic owner writing preference')
        claims=memory.active('new-workflow',scopes=('owner','workflow','strategy'))
        self.assertEqual(len(claims),1);self.assertEqual(claims[0]['scope'],'owner')
        self.assertIn('Concise',claims[0]['claim'])
        review=json.loads((self.root/'.spielos/legacy-review.json').read_text())
        self.assertEqual(len(review['deferred_memory_claims']),2)
        self.assertEqual((self.root/'.spielos/state/company.sqlite').read_bytes(),original)
        self.home.apply_migration(plan,expected_digest=fingerprint(plan))
        self.assertEqual(len(WorkflowMemory(runtime).active('new-workflow')),1)
