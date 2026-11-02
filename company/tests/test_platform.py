"""Exercise real OS identity, locks, private authority and runtime aliases."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from company import platform
from company.runtime.bootstrap import scaffold
from company.security import CompanyAuthority


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()

    def test_private_authority_uses_real_os_identity_and_rejects_broad_access(self):
        home=self.root/'Company with spaces';scaffold(home,keep_stale=True)
        authority=CompanyAuthority(home);owner=authority.local_owner()
        self.assertEqual(owner.subject,'os:'+str(platform.user_id()))
        self.assertTrue(platform.is_private(authority.root))
        if platform.WINDOWS:
            subprocess.run(['icacls',str(authority.key_path),'/grant','*S-1-1-0:R'],check=True,capture_output=True)
        else:authority.key_path.chmod(0o644)
        with self.assertRaises(PermissionError):authority.local_owner()
        platform.protect_private(authority.key_path)
        self.assertEqual(authority.local_owner().subject,owner.subject)

    def test_private_acl_roundtrip_checks_real_native_permissions(self):
        folder=self.root/'Private folder';folder.mkdir();platform.protect_private(folder)
        diagnostic=subprocess.check_output(['icacls',str(folder)],text=True,errors='replace') if platform.WINDOWS else str(folder.stat().st_mode)
        self.assertTrue(platform.is_private(folder),diagnostic)

    def test_real_process_lock_excludes_another_process_and_releases(self):
        lock=self.root/'one.lock'
        code='from company.platform import locked_file; import sys\ntry:\n with locked_file(sys.argv[1],blocking=False):pass\nexcept BlockingIOError:sys.exit(7)'
        with platform.locked_file(lock):
            result=subprocess.run([sys.executable,'-B','-c',code,str(lock)],capture_output=True)
            self.assertEqual(result.returncode,7,result.stderr)
        self.assertEqual(subprocess.run([sys.executable,'-B','-c',code,str(lock)],capture_output=True).returncode,0)

    def test_directory_alias_needs_no_developer_mode_and_resolves_canonically(self):
        target=self.root/'Canonical company';target.mkdir();(target/'record.txt').write_text('One record',encoding='utf-8')
        alias=self.root/'Runtime alias';platform.create_alias(alias,target)
        self.assertTrue(platform.is_link(alias));self.assertEqual(alias.resolve(),target.resolve())
        (alias/'record.txt').write_text('Updated same record',encoding='utf-8')
        self.assertEqual((target/'record.txt').read_text(),'Updated same record')

    def test_installed_unicode_home_and_direct_entrypoint_survive_an_update(self):
        home=self.root/'Example café company';scaffold(home,keep_stale=True)
        entry=home/'.spielos/runtime/company/__main__.py'
        result=subprocess.run([sys.executable,'-X','utf8','-B',str(entry),'status','--home',str(home),'--json'],
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('company_id',json.loads(result.stdout))
        authority=CompanyAuthority(home);token=authority.issue(authority.local_owner(),subject='Test viewer',roles=['viewer'])
        authority.authorize(authority.authenticate(token),'read')
        with self.assertRaises(PermissionError):authority.authorize(authority.authenticate(token),'run')
        scaffold(home,force=True,keep_stale=True)
        self.assertEqual((home/'.agents/company').resolve(),(home/'.spielos/runtime/company').resolve())

    def test_report_paths_accept_native_separators_without_accepting_traversal_or_streams(self):
        from company.reporting import _document,permitted_file
        home=self.root/'Company';scaffold(home,keep_stale=True)
        self.assertEqual(_document(home,'company\\profile.md')['path'],'company/profile.md')
        for unsafe in ('company\\..\\.spielos\\security\\authority.key','company/profile.md:secret'):
            with self.assertRaises(PermissionError):permitted_file(home,unsafe)
