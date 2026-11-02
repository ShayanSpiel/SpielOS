"""Distribution and cross-company report regression checks; synthetic homes only."""
import json,unittest,tomllib,http.client
from pathlib import Path
from company.runtime.config import VERSION
from company.tests import test_report_workspace as reports

class PackageTests(unittest.TestCase):
    def test_versions_and_report_assets_ship_with_the_same_release(self):
        root=Path(__file__).resolve().parents[2]
        self.assertEqual(json.loads((root/'package.json').read_text())['version'],VERSION)
        self.assertEqual(json.loads((root/'company/init_templates/integrations/spielos/plugin.json').read_text())['version'],VERSION)
        package=tomllib.loads((root/'pyproject.toml').read_text())['tool']['setuptools']['package-data']['*']
        self.assertIn('*.js',package)
        for f in ['report_ui/report.js','report_ui/report.css','observability/pricing.json','observability/usage.py']:
            self.assertEqual((root/'company'/f).read_bytes(),(root/'company/init_templates/agents/company'/f).read_bytes())
    def test_report_media_suffix_range_and_company_cookie_isolation(self):
        fixture=reports.ReportTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        s=fixture.server();folder=fixture.home/'.spielos/artifacts/clip';folder.mkdir(parents=True);(folder/'test.mp4').write_bytes(b'0123456789')
        with fixture.request(s,'/.spielos/artifacts/clip/test.mp4',headers={'Range':'bytes=-3'}) as x:self.assertEqual(x.read(),b'789');self.assertEqual(x.headers['Content-Range'],'bytes 7-9/10')
        client=http.client.HTTPConnection('127.0.0.1',int(s['base_url'].rsplit(':',1)[1]));self.addCleanup(client.close)
        client.request('GET','/?token='+s['token']);response=client.getresponse();self.assertEqual(response.status,303)
        cookie=response.headers['Set-Cookie'];self.assertIn('spielos_report_',cookie);self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)

    def test_report_reuse_restarts_when_its_loaded_dependencies_change(self):
        from unittest.mock import patch
        from company.reporting import ensure_server
        fixture=reports.ReportTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        old=ensure_server(fixture.home,port=0)
        with patch('company.reporting.report_fingerprint',return_value='changed-dependency'):
            new=ensure_server(fixture.home,port=0)
        import os,signal
        self.addCleanup(lambda:os.kill(new['pid'],signal.SIGTERM));self.assertNotEqual(old['pid'],new['pid'])
