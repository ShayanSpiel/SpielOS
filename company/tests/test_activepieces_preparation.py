"""Offline package preparation must not connect, overwrite or activate."""
from importlib.util import spec_from_file_location,module_from_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]/'init_templates/integrations/activepieces'

class ActivepiecesPreparationTests(unittest.TestCase):
    def setUp(self):
        spec=spec_from_file_location('activepieces_prepare',ROOT/'configure.py')
        self.module=module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_preparation_is_offline_and_preserves_supplied_endpoint(self):
        with tempfile.TemporaryDirectory() as directory, patch('socket.create_connection',side_effect=AssertionError('must stay offline')):
            output=Path(directory)/'package'
            self.module.prepare('https://selected-instance.invalid/prefix/mcp',output)
            config=json.loads((output/'mcp.json').read_text())
            self.assertEqual(config['mcpServers']['activepieces']['url'],'https://selected-instance.invalid/prefix/mcp')
            self.assertTrue((output/'skills/activepieces-workflows/SKILL.md').is_file())
            self.assertTrue((output/'plugin.json').is_file())
            with self.assertRaisesRegex(ValueError,'new directory'):
                self.module.prepare('https://selected-instance.invalid/mcp',output)

    def test_unsafe_and_placeholder_endpoints_are_rejected(self):
        for url in ['http://instance.invalid/mcp','https://user:secret@instance.invalid/mcp',
                    'https://instance.invalid/mcp?token=secret','https://instance.invalid/dashboard',
                    'https://YOUR-ACTIVEPIECES-INSTANCE/mcp']:
            with tempfile.TemporaryDirectory() as directory, self.subTest(url=url), self.assertRaises(ValueError):
                self.module.prepare(url,Path(directory)/'package')

    def test_distribution_stays_unconfigured(self):
        self.assertFalse((ROOT/'mcp.json').exists())
        self.assertTrue((ROOT/'mcp.json.example').is_file())


    def test_prepared_package_is_shipped_with_exact_template_bytes(self):
        source=ROOT.parents[2]
        for path in ROOT.rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            relative=path.relative_to(ROOT)
            for target in (source/'integration_templates/activepieces',source/'init_templates/agents/company/integration_templates/activepieces'):
                self.assertEqual(path.read_bytes(),(target/relative).read_bytes())
