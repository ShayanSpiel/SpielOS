"""Goal-free workflow contract and failure-path acceptance."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from company.workflows.runs import WorkflowRuntime, LocalAdapter, digest


def manifest(provider="local"):
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    spec = {"id": "synthetic-report", "version": "1", "purpose": "Format a synthetic report",
        "owner": "synthetic-reviewer", "input_schema": schema, "output_schema": schema,
        "dependencies": {}, "context_versions": {},
        "execution": {"provider": provider, "timeout_seconds": 30, "retry_budget": 0, "effect_permissions": [], "binding": "synthetic-v1"},
        "evaluation": {"version": "1", "criteria": [{"id": "correct", "source": "synthetic-reference-v1",
            "anchors": "pass: exact reference; fail: different output", "severity": "block", "evaluator": "reference"}],
            "cases": [{"id": "reference", "split": "representative", "input": {"text": "one"}, "reference": {"text": "one"}, "expected": "pass"},
                      {"id": "held", "split": "held_out", "input": {"text": "two"}, "reference": {"text": "two"}, "expected": "pass"},
                      {"id": "negative", "split": "negative", "input": {"text": "bad"}, "reference": {"text": "good"}, "expected": "fail"}]}}
    spec['evaluation'].update(standard='spielos-evaluation/2', subject='workflow', objective='Preserve the requested report text exactly; reject the known incorrect output')
    spec['evaluation']['criteria'][0].update(question='Does the delivered report equal the pinned expected content?', dimension='output', anchors={'pass':'Delivered content equals the expected report','fail':'Delivered content differs from the expected report'})
    for case in spec['evaluation']['cases']:
        case['intent']='Check exact report content on '+case['split']+' input'
        if case['expected']=='fail':case['failure_criteria']=['correct']
    return spec



def identity(inputs):
    return inputs


def samples():
    return {"reference": {"output": {"text": "one"}}, "held": {"output": {"text": "two"}},
            "negative": {"output": {"text": "bad"}}}


def attach_development(runtime,release):
    """Synthetic fixtures exercise the same development gate as installed homes."""
    if not runtime.authority:return
    from company.improvements import Improvements
    development=Improvements(runtime);spec=runtime.manifest(release)
    with runtime.connect() as connection:
        if connection.execute('SELECT id FROM workflow_improvements WHERE candidate_digest=?',(release,)).fetchone():return
    files=['workflows/'+spec['id']+'/workflow.json']
    item=development.create({'name':'Qualify synthetic '+spec['id'],'business_need':'Exercise actual bounded acceptance',
        'owner':'Synthetic fixture owner','baseline':'unknown','target':'Cases match their expected quality outcomes',
        'constraints':['Synthetic draft data only'],'intended_users':['Test user'],'outcome_window':'This test invocation','allowed_files':files})
    development.observe(item['id'],{'process':'Run the actual fixture implementation','examples':['Pinned cases'],'failures':['Pinned negative case'],
        'criterion_ids':[c['id'] for c in spec['evaluation']['criteria']],'evidence_sources':['Synthetic test specification']})
    development.agree_architecture(item['id'],{'chosen_provider':spec['execution']['provider'],'alternatives':['Other execution provider'],
        'tradeoffs':'Bounded deterministic fixture','execution_contract':'Pinned implementation','evaluation_contract':'Actual case executions',
        'cost_envelope':'Local synthetic fixture','permissions':[],'test_plan':['Representative','Held out','Negative']})
    development.attach_candidate(item['id'],release,changed_files=files)


def prepare_fixture_telemetry(runtime):
    """Explicit synthetic project; never a production qualification shortcut."""
    if not runtime.authority:return
    import json
    path=runtime.home/'.spielos/telemetry.json'
    if not path.is_file():
        path.write_text(json.dumps({'enabled':True,'provider':'langfuse','base_url':'https://langfuse.invalid','project_id':'synthetic-project','payload_policy':'reviewed_evidence','require_verified_release':True}))


def verify_fixture_telemetry(runtime):
    if not runtime.authority:return
    from company.tests.test_langfuse_export import MemoryLangfuse
    client=MemoryLangfuse()
    for _ in range(4):runtime.export_pending(client,limit=100)


def accepted_release(runtime, specification=None, reviewer="synthetic-reviewer", reviewer_runtime=None):
    prepare_fixture_telemetry(runtime)
    specification=specification or manifest()
    release=runtime.candidate(specification)
    attach_development(runtime,release)
    runs={}
    for case in specification['evaluation']['cases']:
        run=runtime.run(release,case['input'],request_key=release+':'+case['id'],candidate_case=case['id'])
        if specification['execution']['provider']=='host':
            if runtime.authority:run=runtime.claim(run['id'])
            runtime.deliver(run['id'],case['input'],token=run['token'])
        runtime.evaluate_run(run['id'],case_id=case['id'])
        runs[case['id']]=run['id']
    verify_fixture_telemetry(runtime)
    return (reviewer_runtime or runtime).release(release,candidate_runs=runs,reviewer=None if runtime.authority else reviewer)


class BoundedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "bounded.sqlite"
        self.calls = []
        self.adapters = {"local": LocalAdapter(identity)}
        self.runtime = WorkflowRuntime(self.path, adapters=self.adapters)
        self.release = accepted_release(self.runtime)

    def test_local_workflow_completes_and_evaluates_without_goal_tables(self):
        run = self.runtime.run(self.release, {"text": "one"}, request_key="one")
        self.assertEqual(run["status"], "awaiting_evaluation")
        checked = self.runtime.evaluate_run(run["id"], case_id="reference")
        self.assertEqual(checked["status"], "awaiting_review")
        result = self.runtime.review(run["id"], reviewer="synthetic-reviewer", decision="accept")
        self.assertEqual(result["status"], "completed")
        with self.runtime.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'core_%'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT status FROM workflow_export_outbox ORDER BY rowid DESC LIMIT 1").fetchone()[0], "pending")

    def test_host_agent_delivery_survives_restart(self):
        release = accepted_release(self.runtime,{**manifest("host"), "version": "host-1"})
        run = self.runtime.run(release, {"text": "one"}, request_key="host")
        restarted = WorkflowRuntime(self.path, adapters=self.adapters)
        restored = restarted.reconcile(run["id"])
        self.assertEqual(restored["status"], "awaiting_provider")
        self.assertEqual(restored['token'],run['token'])
        restarted.deliver(run["id"], {"text": "one"}, token=restored["token"])
        with self.assertRaises(RuntimeError):
            restarted.deliver(run["id"], {"text": "one"}, token=run["token"])
        checked = restarted.evaluate_run(run["id"], case_id="reference")
        self.assertEqual(checked["evaluation"]["state"], "pass")

    def test_update_preserves_pending_invocation_and_ships_new_runtime(self):
        from company.runtime.bootstrap import scaffold
        home = Path(self.temp.name) / "home"
        scaffold(home)
        database = home / ".spielos" / "state" / "workflows.sqlite"
        from company.security import CompanyAuthority
        from company.agents.loader import AgentCatalog
        authority=CompanyAuthority(home);owner=authority.local_owner()
        AgentCatalog(home,owner).create_agent({'id':'reporter','description':'Report supplied text','permissions':['write_artifacts']})
        token=authority.issue(owner,subject='independent-reviewer',roles=['reviewer'])
        runtime = WorkflowRuntime(database,home=home,principal=owner)
        reviewer_runtime=WorkflowRuntime(database,home=home,principal=authority.authenticate(token))
        spec=manifest('host');spec['execution']['binding']='agent:reporter'
        release = accepted_release(runtime,spec,reviewer_runtime=reviewer_runtime)
        pending = runtime.run(release, {"text": "one"}, request_key="pending-update")
        scaffold(home, force=True)
        restored = WorkflowRuntime(database,home=home,principal=owner,readonly=True).get(pending["id"])
        self.assertEqual(restored["status"], "awaiting_provider")
        self.assertEqual(restored["token"], pending["token"])
        source = Path(__file__).resolve().parents[1] / "workflows" / "runs.py"
        self.assertEqual(source.read_bytes(), (home / ".agents/company/workflows/runs.py").read_bytes())

    def test_duplicate_request_does_not_invoke_provider_again(self):
        first = self.runtime.run(self.release, {"text": "one"}, request_key="same")
        second = self.runtime.run(self.release, {"text": "one"}, request_key="same")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.adapters["local"].dispatch_count, 4)
        with self.assertRaises(ValueError):
            self.runtime.run(self.release, {"text": "two"}, request_key="same")

    def test_release_is_immutable_and_pinned(self):
        changed = manifest()
        changed["purpose"] = "Changed"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.runtime.candidate(changed)
        with self.runtime.connect() as connection:
            import sqlite3
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM workflow_releases")

    def test_missing_evaluator_blocks_release(self):
        changed = manifest()
        changed["evaluation"]["criteria"][0]["evaluator"] = "missing"
        with self.assertRaisesRegex(ValueError, "evaluator"):
            self.runtime.candidate(changed)

    def test_empty_and_duplicate_cases_block_release(self):
        for cases in ([], [manifest()["evaluation"]["cases"][0]] * 2):
            changed = manifest()
            changed["evaluation"]["cases"] = cases
            with self.assertRaises(ValueError):
                self.runtime.candidate(changed)

    def test_incomplete_coverage_blocks_release(self):
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.runtime.release(self.release, candidate_runs={"reference":"invented"}, reviewer="synthetic-reviewer")

    def test_poor_output_fails_and_cannot_be_accepted(self):
        run = self.runtime.run(self.release, {"text": "bad"}, request_key="bad")
        failed = self.runtime.evaluate_run(run["id"], case_id="negative")
        self.assertEqual(failed["status"], "failed")
        with self.assertRaises(ValueError):
            self.runtime.review(run["id"], reviewer="synthetic-reviewer", decision="accept")

    def test_case_must_match_actual_inputs(self):
        run = self.runtime.run(self.release, {"text": "one"}, request_key="case-mismatch")
        with self.assertRaises(ValueError):
            self.runtime.evaluate_run(run["id"], case_id="held")

    def test_unknown_usage_is_not_zero_cost(self):
        run = self.runtime.run(self.release, {"text": "one"}, request_key="usage")
        self.runtime.evaluate_run(run["id"], case_id="reference")
        self.runtime.review(run["id"], reviewer="synthetic-reviewer", decision="accept")
        with self.runtime.connect() as connection:
            import json
            payload = json.loads(connection.execute("SELECT payload_json FROM workflow_export_outbox ORDER BY rowid DESC LIMIT 1").fetchone()[0])
        self.assertEqual(payload["usage"], {"status": "unknown"})

    def test_quality_pass_does_not_approve_external_action(self):
        run = self.runtime.run(self.release, {"text": "one"}, request_key="action")
        self.runtime.evaluate_run(run["id"], case_id="reference")
        self.runtime.review(run["id"], reviewer="synthetic-reviewer", decision="accept")
        with self.runtime.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM workflow_action_reviews").fetchone()[0], 0)
        action = {"action": "publish", "destination": "synthetic.invalid", "content_digest": digest(run["output"]), "scope": "one artifact"}
        self.assertEqual(self.runtime.approve_action(run["id"], action, reviewer="synthetic-reviewer", decision="approve"), digest(action))
        with self.assertRaises(ValueError):
            self.runtime.approve_action(run["id"], {**action, "content_digest": "wrong"}, reviewer="synthetic-reviewer", decision="approve")

    def test_unknown_local_completion_is_not_reexecuted_after_crash(self):
        class Crashed:
            def start(self, **kwargs):
                raise RuntimeError("response lost after possible work")
            def inspect(self, **kwargs):
                return {"status": "unknown"}
        crashed=Crashed()
        crashed.revision=self.adapters["local"].revision
        self.runtime.adapters["local"] = crashed
        run = self.runtime.run(self.release, {"text": "one"}, request_key="crash")
        self.assertEqual(run["status"], "awaiting_reconciliation")
        self.assertEqual(self.runtime.reconcile(run["id"])["status"], "awaiting_reconciliation")
        self.assertEqual(self.calls, [])


class BoundedWorkflowCommandTests(unittest.TestCase):
    def test_host_command_flow_and_readonly_show(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        from company.__main__ import main
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import os
            from unittest.mock import patch
            from company.runtime.bootstrap import scaffold
            from company.security import CompanyAuthority
            from company.agents.loader import AgentCatalog
            scaffold(root,keep_stale=True)
            authority=CompanyAuthority(root);owner=authority.local_owner()
            AgentCatalog(root,owner).create_agent({'id':'reporter','description':'Report supplied text','permissions':['write_artifacts']})
            reviewer_token=authority.issue(owner,subject='independent-reviewer',roles=['reviewer'])
            db = root / '.spielos/state/workflows.sqlite'
            def write(name, value):
                path = root / name
                path.write_text(json.dumps(value))
                return str(path)
            def command(*args):
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["--db", str(db), "workflow", *args,"--home",str(root),"--json"]), 0)
                return json.loads(output.getvalue())
            fixture_runtime=WorkflowRuntime(db,home=root,principal=owner)
            prepare_fixture_telemetry(fixture_runtime)
            spec=manifest('host');spec['execution']['binding']='agent:reporter'
            release = command("candidate", "--manifest", write("manifest.json",spec))["release_digest"]
            attach_development(WorkflowRuntime(db,home=root,principal=owner),release)
            runs={}
            for case in manifest('host')['evaluation']['cases']:
                candidate=command('run','--release',release,'--inputs',write('candidate-input.json',case['input']),
                    '--request-key','candidate:'+case['id'],'--candidate-case',case['id'])
                candidate=command('claim',candidate['id'])
                command('deliver',candidate['id'],'--output',write('candidate-output.json',case['input']),'--token',candidate['token'])
                command('evaluate',candidate['id'],'--case',case['id'])
                runs[case['id']]=candidate['id']
            with patch.dict(os.environ,{'SPIELOS_PRINCIPAL_TOKEN':reviewer_token}):
                verify_fixture_telemetry(fixture_runtime)
                command('release','--release',release,'--runs',write('candidate-runs.json',runs))
            run = command("run", "--release", release, "--inputs", write("input.json", {"text": "one"}), "--request-key", "cli")
            before = db.read_bytes()
            self.assertEqual(command("show", run["id"])["status"], "awaiting_provider")
            self.assertEqual(before, db.read_bytes())
            run=command('claim',run['id'])
            command("deliver", run["id"], "--output", write("output.json", {"text": "one"}), "--token", run["token"])
            command("evaluate", run["id"], "--case", "reference")
            with patch.dict(os.environ,{'SPIELOS_PRINCIPAL_TOKEN':reviewer_token}):
                self.assertEqual(command("review", run["id"], "--decision", "accept")["status"], "completed")
