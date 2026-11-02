"""Explicit, bounded Langfuse export with observation-first readback.

No daemon or implicit transmission. Uses OTLP/HTTP JSON (v4) and public scores.
Credentials are environment inputs or an explicitly supplied authorization header;
they never enter outbox records. HTTP errors never include provider response bodies.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import ssl
import subprocess,sys
import time
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@lru_cache(maxsize=1)
def trusted_context():
    """Python.org macOS installs may lack their optional certificate bundle."""
    context=ssl.create_default_context()
    if sys.platform=='darwin' and not context.get_ca_certs():
        roots=subprocess.run(['/usr/bin/security','find-certificate','-a','-p',
            '/System/Library/Keychains/SystemRootCertificates.keychain'],capture_output=True,text=True,timeout=5,check=True)
        context.load_verify_locations(cadata=roots.stdout)
    return context


class ExportError(RuntimeError):
    def __init__(self, message, *, ambiguous=False, status=None,retry_after=None):
        super().__init__(message)
        self.ambiguous = ambiguous
        self.status=status
        self.retry_after=retry_after



def _hash(value, length=64):
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def identities(event):
    trace = _hash("spielos:" + event.get("trace_run_id",event["run_id"]), 32)
    return trace, _hash("spielos-event:" + event["id"], 16)


def _attribute(key, value):
    if isinstance(value, bool):
        data = {"boolValue": value}
    elif isinstance(value, (int, float)):
        data = {"doubleValue": value}
    else:
        data = {"stringValue": str(value)}
    return {"key": key, "value": data}


def _nano(value):
    return str(int(datetime.fromisoformat(value).timestamp() * 1_000_000_000))


def observation(event):
    """Export only approved scalar status, versions and artifact digests."""
    trace_id, span_id = identities(event)
    evaluation = event.get("evaluation") or {}
    attributes = {
        "langfuse.trace.name": event.get('trace_name', event.get('name', "SpielOS bounded workflow")),
        "langfuse.environment": "spielos-local",
        "langfuse.release": event["release_digest"],
        "langfuse.version": str(event.get("workflow_version", "unknown")),
        "langfuse.observation.type": event.get('observation_type', "evaluator" if evaluation else "span"),
        "langfuse.trace.public": False,
        "langfuse.observation.metadata.event_digest": event["id"],
        "langfuse.observation.metadata.release_digest": event["release_digest"],
        "langfuse.observation.metadata.run_digest": _hash(event["run_id"]),
        "langfuse.observation.metadata.execution_status": event["status"],
        "langfuse.observation.metadata.usage_status": event.get("usage",{}).get("status","unknown"),
        "langfuse.observation.metadata.payload_policy": event.get('context_export', 'digests_only'),
        "langfuse.observation.metadata.category": event.get('category','workflow' if event.get('evaluation') else 'activity'),
    }
    if event.get('evaluation') and event.get('context_export')=='reviewed_evidence':
        from .sessions import sanitize
        attributes['langfuse.observation.metadata.evaluation']=json.dumps(sanitize(event['evaluation']),ensure_ascii=False)
    for key in ('company_id','workflow_id','agent_id','agent_name','runtime_model'):
        if event.get(key):attributes['langfuse.observation.metadata.'+key]=event[key]
    attributes["langfuse.observation.input"] = json.dumps({"digest": event.get("input_digest"), "policy": "digests_only"})
    attributes["langfuse.observation.output"] = json.dumps({"digest": event.get("output_digest"), "status": event["status"]})
    if event.get('session_id'):
        attributes['langfuse.session.id'] = event.get('host_session_id',event['session_id'])
    if event.get('context_export') == 'reviewed_evidence' and event.get('evidence'):
        from .sessions import sanitize
        evidence = sanitize(event['evidence'])
        attributes['langfuse.observation.input'] = json.dumps(evidence.get('input'), ensure_ascii=False)
        attributes['langfuse.observation.output'] = json.dumps(evidence.get('output'), ensure_ascii=False)
        for key in ('context', 'artifacts', 'feedback', 'evaluation_contract'):
            if key in evidence:
                attributes['langfuse.observation.metadata.'+key] = json.dumps(evidence[key], ensure_ascii=False)
    if evaluation:
        attributes.update({
            "langfuse.observation.metadata.artifact_digest": evaluation["artifact_digest"],
            "langfuse.observation.metadata.rubric_version": evaluation["rubric_version"],
            "langfuse.observation.metadata.evaluation_state": evaluation["state"],
            "langfuse.observation.metadata.case_digest": _hash(evaluation["case_id"] or "production"),
        })
    usage=event.get('usage') or {'status':'unknown'}
    for key in ('source','currency','input_tokens','cached_input_tokens','cache_write_input_tokens','reasoning_output_tokens','total_tokens','output_tokens','cost'):
        if key in usage:
            attributes['langfuse.observation.metadata.usage_'+key]=usage[key]
    if event.get('observation_type') == 'generation':
        if event.get('model'):
            attributes['gen_ai.request.model'] = event['model']
        if usage.get('status') == 'actual':
            if 'input_tokens' in usage:
                attributes['gen_ai.usage.input_tokens'] = usage['input_tokens']
            if 'cached_input_tokens' in usage:attributes['gen_ai.usage.cache_read.input_tokens']=usage['cached_input_tokens']
            if 'output_tokens' in usage:
                attributes['gen_ai.usage.output_tokens'] = usage['output_tokens']
    # Preserve cost provenance as metadata. Provider service charges and local
    # estimates are not mislabeled as measured model-generation billing.
    experiment=event.get('experiment')
    if experiment:
        attributes.update({'langfuse.experiment.id':experiment['id'],'langfuse.experiment.name':experiment['name'],
            'langfuse.experiment.dataset.id':experiment['dataset_id'],'langfuse.experiment.item.id':experiment['item_id'],
            'langfuse.experiment.item.expected_output':json.dumps(experiment['expected_output']),
            'langfuse.experiment.item.root_observation_id':_hash('spielos-event:'+event['root_event_id'],16)})
    # Each exported record is a completed immutable event in one logical run.
    # No replay updates a span. A run may have distinct evaluation/review events.
    when = _nano(event["at"])
    span = {"traceId": trace_id, "spanId": span_id,
            "name": event.get('name', "SpielOS " + event["status"]), "kind": 1,
            "startTimeUnixNano": _nano(event.get("started_at",event["at"])), "endTimeUnixNano": when,
            "attributes": [_attribute(key, value) for key, value in attributes.items()],
            "status": {"code": 2 if event["status"] == "failed" else 1}}
    root_event = event.get("root_event_id", event["id"])
    if root_event != event["id"]:
        span["parentSpanId"] = _hash("spielos-event:" + root_event, 16)
    return {"resourceSpans": [{"resource": {"attributes": [_attribute("service.name", "spielos")]},
            "scopeSpans": [{"scope": {"name": "spielos.workflow-export", "version": "1"}, "spans": [span]}]}]}


def scores(event):
    trace_id, span_id = identities(event)
    evaluation = event.get("evaluation") or {}
    rows = []
    for criterion, verdict in sorted(evaluation.get("criteria", {}).items()):
        state = verdict["state"]
        # Missing/error/not-applicable are categorical states, never zero scores.
        config=(event.get('score_configs') or {}).get(criterion)
        rows.append({**({'configId':config['id']} if config else {}),"id": _hash(event["id"] + ":" + criterion, 32),
            "traceId": trace_id, "observationId": span_id,
            "name": config["name"] if config else verdict.get('question') or criterion, "dataType": "CATEGORICAL", "value": state,
            "comment": (verdict.get('reason', '') if event.get('context_export') == 'reviewed_evidence' else "SpielOS criterion result; rationale retained locally"),
            "metadata": {"event_digest": event["id"], "release_digest": event["release_digest"],
                         "rubric_version": evaluation["rubric_version"],
                         "artifact_digest": evaluation["artifact_digest"],
                         "evaluator_version": verdict.get("evaluator_version","legacy-evaluator-unspecified"),
                         **({'evidence': verdict.get('evidence'), 'source': verdict.get('source'), 'dimension': verdict.get('dimension')} if event.get('context_export') == 'reviewed_evidence' else {})}})
        if verdict.get('score') is not None:
            rows.append({'id': _hash(event['id']+':'+criterion+':rating', 32), 'traceId': trace_id,
                         'observationId': span_id, 'name': criterion+'.rating', 'dataType': 'NUMERIC',
                         'value': verdict['score'], 'comment': rows[-1]['comment'], 'metadata': rows[-1]['metadata']})
    if event.get('rating'):
        rating = event['rating']
        rated_trace,rated_span=identities(event.get('rating_subject',event))
        rows.append({'id': _hash(event['id']+':owner-rating', 32), 'traceId': rated_trace,
                     'observationId': rated_span, 'name': rating['criterion'], 'dataType': 'NUMERIC',
                     'value': rating['value'], 'comment': rating['reason'],
                     'metadata': {'event_digest': event['id'], 'target': rating['target'], 'origin': 'attributed-review'}})
    return rows


class LangfuseClient:
    def __init__(self, *, base_url, project_id, public_key=None, secret_key=None,
                 authorization=None, timeout=20, context=None):
        url = urlsplit(base_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Langfuse needs an HTTPS base URL without embedded credentials")
        if url.path not in {"", "/"}:
            raise ValueError("Langfuse base URL must be an origin")
        if not project_id:
            raise ValueError("explicit Langfuse project identity required")
        if not authorization:
            if not public_key or not secret_key:
                raise ValueError("Langfuse project credentials are not configured")
            authorization = "Basic " + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        if not authorization.startswith("Basic "):
            raise ValueError("Langfuse requires project Basic authentication")
        self.base_url, self.project_id = base_url.rstrip("/"), project_id
        self.authorization, self.timeout = authorization, timeout
        self.opener = build_opener(_NoRedirect(), HTTPSHandler(context=context or trusted_context()))
        self._project_verified = False
        self._read_cache = {}

    def begin_batch(self):
        self._read_cache.clear()

    def read(self, path):
        if path not in self._read_cache:
            self._read_cache[path] = self.request("GET", path)
        return self._read_cache[path]


    @classmethod
    def from_configuration(cls,home,config):
        """Credentials remain in an explicitly selected private company file."""
        from pathlib import Path
        reference=config.get('credential_ref')
        if not reference:
            client=cls.from_environment();client._rate_path=Path(home).resolve()/'.spielos/telemetry-rate-limit.json';return client
        root=Path(home).resolve();relative=Path(reference);path=root/relative
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0]!='.spielos' or path.is_symlink() or not path.resolve().is_relative_to(root/'.spielos'):
            raise ValueError('Telemetry credential reference must be a private company file')
        from ..platform import is_private
        if not is_private(path):raise PermissionError('Telemetry credential file must be owner-private')
        credentials=json.loads(path.read_text())
        client=cls(base_url=config['base_url'],project_id=config['project_id'],authorization=credentials.get('authorization'),public_key=credentials.get('public_key'),secret_key=credentials.get('secret_key'))
        client._rate_path=root/'.spielos/telemetry-rate-limit.json'
        return client

    @classmethod
    def from_environment(cls):
        return cls(base_url=os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            project_id=os.environ.get("LANGFUSE_PROJECT_ID"), public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.environ.get("LANGFUSE_SECRET_KEY"))

    def request(self, method, path, payload=None):
        rate_path=getattr(self,'_rate_path',None)
        rate_group='definitions' if any(p in path for p in ('/v2/evaluators','/v2/evaluation-rules')) else 'delivery'
        if rate_path and rate_path.is_symlink():raise PermissionError('Telemetry rate-limit state cannot be a symbolic link')
        if rate_path and rate_path.is_file():
            limits=json.loads(rate_path.read_text());cooldown=limits.get(rate_group,limits.get('retry_at',0))-time.time()
            if cooldown>0:raise ExportError('Langfuse rate-limit cooldown; evidence remains queued',status=429,retry_after=cooldown)
        remaining=getattr(self,'deadline',float('inf'))-time.monotonic()
        if remaining<=0:raise ExportError('Telemetry wake reached its time budget',ambiguous=False)
        headers = {"Authorization": self.authorization, "Content-Type": "application/json",
                   "x-langfuse-ingestion-version": "4"}
        data = json.dumps(payload, allow_nan=False).encode() if payload is not None else None
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=min(self.timeout,remaining)) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except HTTPError as exc:
            if exc.code==429:
                try:delay=max(1,min(3600,float(exc.headers.get('Retry-After','60'))))
                except (ValueError,TypeError):delay=60
                if rate_path:
                    from ..home import write_json
                    limits=json.loads(rate_path.read_text()) if rate_path.is_file() else {}
                    limits.update({rate_group:time.time()+delay,'reason':'Langfuse HTTP 429; defer this API family until an eligible bounded wake'})
                    write_json(rate_path,limits)
                raise ExportError('Langfuse rate limited telemetry; evidence remains queued',status=429,retry_after=delay) from None
            raise ExportError(f"Langfuse request failed (HTTP {exc.code})",
                ambiguous=method == "POST" and (exc.code >= 500 or exc.code==408),status=exc.code) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ExportError("Langfuse request failed; result may be unknown",
                ambiguous=method == "POST") from None

    def verify_project(self):
        result = self.request("GET", "/api/public/projects")
        if {row["id"] for row in result.get("data", [])} != {self.project_id}:
            raise ExportError("Langfuse credentials do not match the explicitly selected project")
        self._project_verified = True

    def find_observation(self, event):
        trace_id, span_id = identities(event)
        query = urlencode({"traceId": trace_id, "fields": "core,basic,metadata", "limit": 100})
        cursor = None
        for _ in range(10):
            response = self.read("/api/public/v2/observations?" + query +
                                    ("&" + urlencode({"cursor": cursor}) if cursor else ""))
            for row in response.get("data", []):
                if row.get("id") == span_id and row.get("traceId") == trace_id:
                    metadata = row.get("metadata") or {}
                    # Mismatched immutable content is a hard failure, not success.
                    if metadata.get("event_digest") != event["id"] or metadata.get("release_digest") != event["release_digest"]:
                        raise ExportError("Langfuse observation identity/content mismatch")
                    return row
            cursor = response.get("meta", {}).get("cursor")
            if not cursor:
                return None
        raise ExportError("Langfuse observation pagination exceeded its budget")

    def score_matches(self, expected):
        query = urlencode({"traceId": expected["traceId"], "fields": "subject,details", "limit": 100})
        cursor = None
        for _ in range(10):
            result = self.read("/api/public/v3/scores?" + query +
                                  ("&" + urlencode({"cursor": cursor}) if cursor else ""))
            for row in result.get("data", []):
                if row.get("id") == expected["id"]:
                    subject = row.get("subject") or {}
                    if (subject.get("kind") != "observation"
                            or subject.get("traceId") != expected["traceId"]
                            or subject.get("id") != expected["observationId"]
                            or any(row.get(key) != expected[key] for key in ("name", "dataType", "value"))
                            or any(str((row.get("metadata") or {}).get(key)) != str(value)
                                   for key, value in expected["metadata"].items())):
                        raise ExportError("Langfuse score identity/content mismatch")
                    return True
            cursor = result.get("meta", {}).get("cursor")
            if not cursor:
                return False
        raise ExportError("Langfuse score pagination exceeded its budget")

    def export(self, event, *, allow_ingest):
        if not self._project_verified:
            self.verify_project()
        existing = self.find_observation(event)
        if not existing:
            if not allow_ingest:
                # OTLP re-ingestion is not idempotent. Ambiguous sends are read
                # back on later wakes, never blindly resent with the same ID.
                return None
            response = self.request("POST", "/api/public/otel/v1/traces", observation(event))
            if response.get("partialSuccess", {}).get("rejectedSpans", "0") not in {0, "0"}:
                raise ExportError("Langfuse rejected part of the trace batch", ambiguous=True)
            return None  # transport acceptance is not remote verification
        expected_scores = scores(event)
        wrote_scores = False
        for score in expected_scores:
            if not self.score_matches(score):
                self.request("POST", "/api/public/scores", score)
                wrote_scores = True
        if wrote_scores:
            return None  # wait for exact score readback before completion
        trace_id, span_id = identities(event)
        return self.base_url + "/project/" + self.project_id + "/traces/" + trace_id + "?observation=" + span_id
