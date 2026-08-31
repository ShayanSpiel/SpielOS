"""Generated worker artifacts must load through both host and roster contracts."""

from __future__ import annotations

import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from company.agents import _load_installed_agents
from company.runtime.agent_compile import _render_codex, _render_roster


class AgentCompileTests(unittest.TestCase):
    def test_generated_codex_toml_parses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _render_codex(
                root, "lead-worker", "outbound", "social-lead-research",
                "research", ["qualification"], ["lead_dossier"],
                ["research"], False)
            payload = tomllib.loads(Path(path).read_text())
            self.assertEqual("lead-worker", payload["name"])
            self.assertIn("persisted company work-order", payload["developer_instructions"])

    def test_generated_roster_round_trips_declared_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _render_roster(
                root, "lead-worker", "outbound", "social-lead-research",
                ["qualification"], ["web"], ["lead_dossier"], False)
            installed = Path(path).parent
            with patch.dict("os.environ", {"SPIELOS_AGENTS_INSTALLED_ROOT": str(installed)}):
                agent = _load_installed_agents()["lead-worker"]
            self.assertEqual(("qualification",), agent.skill_ids)
            self.assertEqual(("lead_dossier",), agent.produces)
            self.assertIn("use_connection:web", agent.permissions)
            raw = json.loads(Path(path).read_text())
            self.assertNotIn("skills", raw)
            self.assertNotIn("evidence_kinds", raw)


if __name__ == "__main__":
    unittest.main()
