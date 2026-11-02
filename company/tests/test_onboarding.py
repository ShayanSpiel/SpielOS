"""First-use choices and exact-project verification; no real service calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from company.runtime.bootstrap import scaffold
from company import onboarding
from company.platform import is_private


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/'example-company';scaffold(self.home,keep_stale=True)

    def test_connection_question_is_pending_until_an_explicit_choice(self):
        self.assertTrue(onboarding.status(self.home)['ask_langfuse'])
        result=onboarding.choose(self.home,'local')
        self.assertFalse(result['ask_langfuse']);self.assertFalse(result['langfuse_configured'])
        self.assertFalse(onboarding.status(self.home)['dashboard_tour_shown'])

    def test_failed_or_wrong_project_readback_enables_nothing(self):
        with patch('company.observability.langfuse.LangfuseClient.request',return_value={'data':[{'id':'another-project'}]}):
            with self.assertRaises(ValueError):self.connect()
        self.assertFalse((self.home/'.spielos/telemetry.json').exists())
        self.assertFalse((self.home/'.spielos/security/langfuse.json').exists())

    def connect(self):
        return onboarding.connect_langfuse(self.home,base_url='https://langfuse.invalid',project_id='synthetic-project',
            public_key='synthetic-public-key',secret_key='synthetic-secret-key',approved_evidence_policy='reviewed_evidence')

    def test_successful_connection_is_exact_private_and_never_echoes_keys(self):
        with patch('company.observability.langfuse.LangfuseClient.request',return_value={'data':[{'id':'synthetic-project'}]}) as request:
            result=self.connect()
        request.assert_called_once_with('GET','/api/public/projects')
        self.assertTrue(result['langfuse_configured']);self.assertTrue(result['connection_verified_at'])
        self.assertNotIn('synthetic-secret-key',json.dumps(result))
        policy=json.loads((self.home/'.spielos/telemetry.json').read_text())
        self.assertNotIn('synthetic-secret-key',json.dumps(policy));self.assertTrue(policy['require_verified_release'])
        self.assertTrue(is_private(self.home/policy['credential_ref']))

    def test_tour_cannot_be_completed_with_an_invented_dashboard(self):
        with self.assertRaises(ValueError):onboarding.tour_shown(self.home,'http://127.0.0.1:1/invented')
        self.assertFalse(onboarding.status(self.home)['dashboard_tour_shown'])

    def test_context_requests_a_first_chat_tour_without_inventing_connection(self):
        from company.mcp import CompanySession
        from company.observability.receipts import context_payload
        session=CompanySession();value=session.select(str(self.home))
        text,_,_=context_payload(session.inspect(value['company_id']),home=self.home)
        self.assertIn('connect Langfuse now or continue locally',text)
        self.assertIn('After this first meaningful chat',text)
        onboarding.choose(self.home,'local')
        text,_,_=context_payload(session.inspect(value['company_id']),home=self.home)
        self.assertNotIn('ask whether to connect Langfuse now',text)
