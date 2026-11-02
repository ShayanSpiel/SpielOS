"""Owners explicitly create/select homes; public entry points use the same core."""
from pathlib import Path
import json,os,shlex,shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from company.runtime.bootstrap import scaffold
from .test_home import scenario

SOURCE=Path(__file__).resolve().parents[3]


class InstallationJourneys(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve();self.bin=self.root/'bin';self.bin.mkdir()
        pipx=self.bin/'pipx';pipx.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "pipx test"; exit 0; fi\nprintf "%s\\n" "$*" >> "$INSTALL_LOG"\nexit 0\n');pipx.chmod(0o755)
        wrapper=self.bin/'spielos';wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -B -m company.cli "$@"\n');wrapper.chmod(0o755)
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1',
            'PYTHONPATH':str(SOURCE),'SPIELOS_TEMPLATE_DIR':str(SOURCE/'company/init_templates'),
            'SPIELOS_SOURCE':str(SOURCE),'SPIELOS_DIR':'','INSTALL_LOG':str(self.root/'install.log')}
        self.env.pop('SPIELOS_PRINCIPAL_TOKEN',None);self.env.pop('SPIELOS_HOME',None)

    def install(self,cwd,*args):
        result=subprocess.run(['/bin/sh',str(SOURCE/'install.sh'),*args],cwd=cwd,env=self.env,
                              stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);return result

    @scenario('home.explicit_installer_and_public_entrypoints')
    def test_piped_install_does_not_initialize_or_update_the_working_folder(self):
        empty=self.root/'empty';empty.mkdir();result=self.install(empty)
        self.assertEqual(list(empty.iterdir()),[])
        self.assertIn('No company home was created or changed automatically',result.stdout)
        self.assertIn('install --force', (self.root/'install.log').read_text())
        help_result=subprocess.run(['/bin/sh',str(SOURCE/'install.sh'),'--help'],cwd=empty,
            env=self.env,capture_output=True,text=True,timeout=5)
        self.assertEqual(help_result.returncode,0)
        self.assertIn('preview-only',help_result.stdout)

    @scenario('home.explicit_installer_and_public_entrypoints','home.update_preserves_owner_content')
    def test_explicit_home_creation_update_and_package_preview_use_real_core_without_auto_import(self):
        working=self.root/'working';working.mkdir();home=self.root/'selected-home'
        self.install(working,'--init','--dir',str(home))
        self.assertTrue((home/'.agents/company').is_symlink())
        voice=home/'company/brand/voice.md';voice.write_text('Owner voice stays here.\n')
        package=self.root/'package'
        export=subprocess.run([sys.executable,'-B','-m','company','export','sales-report','--home',str(home),
            '--out',str(package),'--package-id','installer-example','--version','fixture-v1','--json'],
            cwd=working,env=self.env,capture_output=True,text=True,timeout=15)
        self.assertEqual(export.returncode,0,export.stderr)
        preview=self.install(working,'--dir',str(home),'--package',str(package))
        self.assertIn('Package preview only',preview.stdout)
        self.assertEqual(voice.read_text(),'Owner voice stays here.\n')
        self.assertFalse((home/'.spielos/imports').exists())
        self.assertFalse((home/'.spielos/state/company.sqlite').exists())

    @scenario('home.explicit_installer_and_public_entrypoints','runtime.no_goal_or_daemon_needed')
    def test_npm_bridge_uses_the_vendored_home_without_a_global_python_package(self):
        home=self.root/'npm-home'
        with patch.dict(os.environ,{'SPIELOS_TEMPLATE_DIR':str(SOURCE/'company/init_templates')}):scaffold(home,keep_stale=True)
        env={**self.env,'PYTHONPATH':'','SPIELOS_PYTHON':sys.executable}
        result=subprocess.run(['node',str(SOURCE/'bin/spielos.js'),'status','--json'],cwd=home,
            env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['activepieces'],'inactive')
        self.assertEqual(len(value['workflows']),1)
        self.assertFalse((home/'.spielos/state/company.sqlite').exists())
        self.assertFalse((home/'.spielos/state/workflows.sqlite').exists())

        # An explicit selected company controls runtime dispatch even when
        # invoked from a different initialized company with older code.
        other=self.root/'other-home'
        with patch.dict(os.environ,{'SPIELOS_TEMPLATE_DIR':str(SOURCE/'company/init_templates')}):scaffold(other,keep_stale=True)
        (home/'.agents/company/__main__.py').write_text("print('{\"wrong_home\": true}')\n")
        for argument in (['--home',str(other)],['--home='+str(other)]):
            selected=subprocess.run([sys.executable,'-B','-m','company.cli','status',*argument,'--json'],cwd=home,
                env=self.env,capture_output=True,text=True,timeout=15)
            self.assertEqual(selected.returncode,0,selected.stderr)
            result=json.loads(selected.stdout)
            self.assertEqual(result['company_id'],json.loads((other/'.spielos/layout.json').read_text())['company_id'])
            self.assertNotIn('wrong_home',result)
