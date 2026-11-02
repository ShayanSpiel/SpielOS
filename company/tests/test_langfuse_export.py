"""No-network transport, privacy, response-loss and readback acceptance."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from company.observability.langfuse import LangfuseClient, ExportError, observation, identities
from company.workflows.runs import WorkflowRuntime, LocalAdapter
from company.tests.test_bounded_workflow_runs import manifest, samples, accepted_release, identity


class MemoryLangfuse(LangfuseClient):
    def __init__(self, *, lost=False, visible=True, project="synthetic-project"):
        super().__init__(base_url="https://langfuse.invalid", project_id="synthetic-project",
                         public_key="synthetic-public", secret_key="synthetic-secret")
        self.observations, self.scores, self.posts = [], [], []
        self.lost, self.visible, self.project = lost, visible, project

    def request(self, method, path, payload=None):
        if path == "/api/public/projects":
            return {"data": [{"id": self.project}]}
        if path.startswith("/api/public/v2/observations"):
            return {"data": self.observations if self.visible else []}
        if path.startswith("/api/public/v3/scores"):
            return {"data": self.scores if self.visible else []}
        if path == "/api/public/otel/v1/traces":
            self.posts.append((path,deepcopy(payload)))
            span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
            attrs = {row["key"]: next(iter(row["value"].values())) for row in span["attributes"]}
            self.observations.append({"id": span["spanId"], "traceId": span["traceId"],
                "metadata": {key.removeprefix("langfuse.observation.metadata."): value
                    for key,value in attrs.items() if key.startswith("langfuse.observation.metadata.")}})
            if self.lost:
                self.lost = False
                raise ExportError("response lost", ambiguous=True)
            return {}
        if path == "/api/public/scores":
            self.posts.append((path,deepcopy(payload)))
            returned = deepcopy(payload)
            returned["subject"] = {"kind":"observation", "traceId":returned.pop("traceId"), "id":returned.pop("observationId")}
            self.scores = [row for row in self.scores if row["id"] != payload["id"]] + [returned]
            return payload
        raise AssertionError((method,path))


class LangfuseExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runtime = WorkflowRuntime(Path(self.directory.name)/"db.sqlite", adapters={"local": LocalAdapter(identity)})
        self.release = accepted_release(self.runtime)
        with self.runtime.connect() as connection:
            connection.execute("UPDATE workflow_export_outbox SET status='verified'")
        self.run = self.runtime.run(self.release,{"text":"one"},request_key="synthetic")

    def events(self):
        with self.runtime.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM workflow_export_outbox WHERE run_id=? ORDER BY rowid",(self.run["id"],))]

    def test_transport_acceptance_is_not_remote_verification(self):
        client = MemoryLangfuse()
        self.assertEqual(self.runtime.export_pending(client)[0]["status"],"awaiting_readback")
        self.assertEqual(self.runtime.export_pending(client)[0]["status"],"verified")
        self.assertEqual(len(client.posts),2)

    def test_lost_response_is_reconciled_without_second_span(self):
        client = MemoryLangfuse(lost=True)
        self.runtime.export_pending(client)
        result = self.runtime.export_pending(client)
        self.assertEqual(result[0]["status"],"verified")
        self.assertEqual(len(client.posts),2)

    def test_visibility_lag_never_reingests_spans(self):
        client = MemoryLangfuse(visible=False)
        for _ in range(3):
            self.runtime.export_pending(client)
        self.assertEqual(len(client.posts),2)
        self.assertEqual(self.events()[0]["status"],"awaiting_readback")
        client.visible=True
        self.assertEqual(self.runtime.export_pending(client)[0]["status"],"verified")

    def test_wrong_project_blocks_every_write(self):
        client = MemoryLangfuse(project="different-project")
        result = self.runtime.export_pending(client)
        self.assertEqual(result[0]["status"],"pending")
        self.assertEqual(client.posts,[])

    def test_failed_outputs_export_failed_criteria_with_versions(self):
        run=self.runtime.run(self.release,{"text":"bad"},request_key="negative")
        self.runtime.evaluate_run(run["id"],case_id="negative")
        client=MemoryLangfuse()
        for _ in range(4):
            self.runtime.export_pending(client)
        self.assertTrue(all(row["status"]=="verified" for row in self.events()))
        self.assertTrue(any(row["value"]=="fail" for row in client.scores))
        for row in client.scores:
            self.assertEqual(row["metadata"]["release_digest"],self.release)
            self.assertEqual(row["metadata"]["rubric_version"],"1")
            self.assertEqual(row["metadata"]["evaluator_version"],"reference-v1")

    def test_private_inputs_rationales_and_credentials_do_not_leave(self):
        self.runtime.evaluate_run(self.run["id"],case_id="reference")
        with self.runtime.connect() as connection:
            row=connection.execute("SELECT * FROM workflow_export_outbox ORDER BY rowid DESC LIMIT 1").fetchone()
        event=json.loads(row["payload_json"])
        event["evaluation"]["criteria"]["correct"]["reason"]="PRIVATE-REASON"
        event["inputs"]={"password":"PRIVATE-INPUT"}
        event["review"]={"reviewer":"PRIVATE-REVIEWER"}
        client=MemoryLangfuse()
        client.export(event,allow_ingest=True)
        client.begin_batch()
        client.export(event,allow_ingest=False)
        serialized=json.dumps(client.posts)
        for value in ("PRIVATE-REASON","PRIVATE-INPUT","PRIVATE-REVIEWER","synthetic-secret","synthetic-public"):
            self.assertNotIn(value,serialized)
        self.assertIn("digests_only",serialized)
        self.assertIn("unknown",serialized)

    def test_trace_tree_uses_original_root_event(self):
        self.runtime.evaluate_run(self.run["id"],case_id="reference")
        events=[json.loads(row["payload_json"]) for row in self.events()]
        root=observation(events[0])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        child=observation(events[1])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertNotIn("parentSpanId",root)
        self.assertEqual(child["parentSpanId"],root["spanId"])
        self.assertEqual(child["traceId"],root["traceId"])

    def test_retry_budget_survives_restart(self):
        client=MemoryLangfuse(visible=False)
        self.runtime.export_pending(client,max_attempts=1)
        restarted=WorkflowRuntime(self.runtime.path)
        self.assertEqual(restarted.export_pending(client,max_attempts=1),[])
        self.assertEqual(len(client.posts),2)

    def test_corrupted_remote_identity_cannot_be_verified(self):
        client=MemoryLangfuse()
        self.runtime.export_pending(client)
        client.observations[0]["metadata"]["release_digest"]="wrong"
        result=self.runtime.export_pending(client)
        self.assertEqual(result[0]["status"],"awaiting_readback")
        self.assertIn("mismatch",result[0]["error"])

    def test_plain_http_and_credential_urls_rejected(self):
        for url in ("http://example.invalid","https://user:secret@example.invalid","https://example.invalid?token=secret"):
            with self.assertRaises(ValueError):
                LangfuseClient(base_url=url,project_id="synthetic",public_key="public",secret_key="secret")
