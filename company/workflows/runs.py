"""Bounded workflow releases and invocations, independent of legacy Goals.

Trusted local principals only. This module is not a multi-user authorization
service. Provider implementations own their transport and effect idempotency.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import inspect
import multiprocessing
import threading
import subprocess
from ..platform import user_id
import sys
import os
import re
import time
from typing import Protocol
import uuid


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def validate(schema, value, path="value"):
    """Deliberately small, fail-closed JSON schema vocabulary.

    Unsupported keywords are rejected rather than silently ignored. Full JSON
    Schema interoperability is a separate integration, not claimed here.
    """
    allowed = {"type", "properties", "required", "additionalProperties", "items", "enum"}
    if not isinstance(schema, dict) or set(schema) - allowed:
        raise ValueError(f"unsupported schema at {path}")
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "boolean": bool, "null": type(None)}
    if kind not in types:
        raise ValueError(f"schema needs a supported type at {path}")
    if not isinstance(value, types[kind]) or (kind in {"integer", "number"} and isinstance(value, bool)):
        raise ValueError(f"{path} must be {kind}")
    canonical(value)
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not an allowed value")
    if kind == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, dict) or not isinstance(schema.get("required", []), list):
            raise ValueError(f"invalid object schema at {path}")
        if set(schema.get("required", [])) - set(value):
            raise ValueError(f"missing required fields at {path}")
        if schema.get("additionalProperties", False) is not True and set(value) - set(properties):
            raise ValueError(f"unexpected fields at {path}")
        for key, item in value.items():
            if key in properties:
                validate(properties[key], item, f"{path}.{key}")
    if kind == "array":
        for index, item in enumerate(value):
            validate(schema.get("items", {}), item, f"{path}[{index}]")


class Adapter(Protocol):
    """Return completed/output or pending/handle. Never infer remote success."""
    def start(self, *, request_id: str, manifest: dict, inputs: dict) -> dict: ...
    def inspect(self, *, request_id: str, handle: str) -> dict: ...


class HostAdapter:
    """A durable assignment for the selected host; no implicit agent invocation."""
    def start(self, *, request_id, manifest, inputs):
        return {"status": "pending", "handle": request_id}

    def inspect(self, *, request_id, handle):
        return {"status": "pending", "handle": handle}


def _local_child(execute,inputs,send):
    try:
        send.send({"status":"completed","output":execute(inputs),"usage":{"status":"unknown"}})
    except Exception as exc:
        send.send({"status":"failed","error":type(exc).__name__+": "+str(exc)})
    finally:send.close()


class LocalAdapter:
    """Run trusted pure local code in a child process with a hard deadline."""
    def __init__(self, execute):
        if '<locals>' in execute.__qualname__ or execute.__name__=='<lambda>':
            raise ValueError('Local execution needs an importable trusted function for portable process isolation')
        self.execute = execute
        self.dispatch_count = 0
        source = inspect.getsource(execute)
        self.revision = digest({"source": source, "module": execute.__module__,
                                "name": execute.__qualname__})

    def start(self, *, request_id, manifest, inputs):
        self.dispatch_count += 1
        context=multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        process = context.Process(target=_local_child,args=(self.execute,deepcopy({'inputs':inputs,'context':{'documents':manifest.get('resolved_context',{}),'brand':manifest.get('resolved_brand'),'memory':manifest.get('invocation_memory',[])}} if manifest['execution'].get('context_transport')=='envelope_v1' else inputs),send),daemon=True)
        process.start(); send.close()
        try:
            if receive.poll(manifest["execution"]["timeout_seconds"]):
                try: return receive.recv()
                except EOFError: return {"status": "unknown", "error": "local process exited before returning its result"}
            return {"status": "failed", "error": "local execution exceeded its deadline"}
        finally:
            if process.is_alive(): process.terminate()
            process.join(); receive.close()

    def inspect(self, *, request_id, handle):
        return {"status": "unknown", "handle": handle}

    def cancel(self, *, request_id, handle):
        return {"status": "cancelled", "handle": handle}


class LocalFileAdapter:
    """Execute an explicitly selected, digest-pinned owner script on invocation.

    Construction/import reads bytes only. The local filesystem owner must trust
    code before running it; this is process isolation, not an untrusted-code VM.
    Scripts consume one JSON input on stdin and return one JSON output on stdout.
    """
    def __init__(self,home,manifest):
        from ..home import CompanyHome
        CompanyHome(home).require_ready()
        content=CompanyHome(home).content
        identity=manifest.get('id','')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',identity):raise ValueError('Local workflow identity is not portable')
        root=content/'workflows'/identity
        relative=Path(manifest['execution']['binding'])
        path=root/relative
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative.parts[0]!='execution':
            raise ValueError('Local binding must name this workflow execution script')
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or path.suffix!='.py':
            raise ValueError('Local binding must be a contained Python script')
        self.path=path.resolve();self.root=root.resolve()
        self.revision=hashlib.sha256(self.path.read_bytes()).hexdigest()

    def start(self,*,request_id,manifest,inputs):
        if hashlib.sha256(self.path.read_bytes()).hexdigest()!=self.revision:
            return {'status':'failed','error':'Execution code changed after dispatch validation'}
        environment={key:os.environ[key] for key in ('PATH','LANG','SYSTEMROOT') if key in os.environ}
        try:
            payload=({'inputs':inputs,'context':{'documents':manifest.get('resolved_context',{}),'brand':manifest.get('resolved_brand'),'memory':manifest.get('invocation_memory',[])}} if manifest['execution'].get('context_transport')=='envelope_v1' else inputs)
            result=subprocess.run([sys.executable,'-I','-B',str(self.path)],input=canonical(payload),
                cwd=self.root,env=environment,capture_output=True,text=True,
                timeout=manifest['execution']['timeout_seconds'])
        except subprocess.TimeoutExpired:return {'status':'failed','error':'Local execution exceeded its deadline'}
        if result.returncode:return {'status':'failed','error':'Local script failed; inspect the bounded execution log'}
        if len(result.stdout)>1024*1024:return {'status':'failed','error':'Local output exceeds one megabyte'}
        try:output=json.loads(result.stdout)
        except ValueError:return {'status':'failed','error':'Local script did not return a JSON output'}
        return {'status':'completed','output':output,'usage':{'status':'unknown'}}

    def inspect(self,*,request_id,handle):return {'status':'unknown','handle':handle}
    def cancel(self,*,request_id,handle):return {'status':'cancelled','handle':handle}


class SequentialAdapter:
    """Small sequential composition over durable child invocations, not a DAG."""
    def __init__(self,runtime):
        self.runtime=runtime
        self.revision=digest(inspect.getsource(type(self)))

    def validate(self,manifest):
        execution=manifest['execution'];steps=execution.get('steps')
        if not isinstance(steps,list) or not 1<=len(steps)<=20:raise ValueError('Composition needs one to twenty ordered steps')
        for index,step in enumerate(steps):
            if not isinstance(step,dict) or set(step)!={'release','inputs'}:raise ValueError('Each step needs a pinned release and explicit input mapping')
            child=self.runtime.manifest(step['release'])
            if child['execution']['provider']=='sequential':raise ValueError('Nested compositions are outside this bounded sequence contract')
            with self.runtime.connect() as connection:
                if not connection.execute('SELECT digest FROM workflow_release_acceptance WHERE digest=?',(step['release'],)).fetchone():
                    raise ValueError('Every child workflow must already be released')
            self._validate_mapping(step['inputs'],index)
        self._validate_mapping(execution.get('output'),len(steps))

    @staticmethod
    def _validate_mapping(mapping,available):
        if not isinstance(mapping,dict) or not mapping:raise ValueError('Sequence mappings must explicitly name fields')
        for reference in mapping.values():
            if not isinstance(reference,dict):raise ValueError('Sequence references must be objects')
            if set(reference)=={'input'}:
                if not isinstance(reference['input'],str) or not reference['input'].startswith('/'):raise ValueError('Input references use JSON pointers')
            elif set(reference)=={'step','path'}:
                if not isinstance(reference['step'],int) or isinstance(reference['step'],bool) or not 0<=reference['step']<available or not isinstance(reference['path'],str) or not reference['path'].startswith('/'):
                    raise ValueError('A sequence can reference only completed earlier steps')
            else:raise ValueError('Unsupported sequence mapping')

    def _advance(self,request_id,manifest,inputs):
        from ..evals.contracts import field
        outputs=[]
        def mapped(mapping):
            return {name:field(inputs,ref['input']) if 'input' in ref else field(outputs[ref['step']],ref['path']) for name,ref in mapping.items()}
        for index,step in enumerate(manifest['execution']['steps']):
            child_manifest=self.runtime.manifest(step['release'])
            if (child_manifest['execution']['provider']=='local' and self.runtime.home
                    and getattr(self.runtime.adapters.get('local'),'revision',None)!=child_manifest['execution'].get('implementation_digest')):
                # Resolve the exact script without executing submitted imports.
                self.runtime.adapters['local']=LocalFileAdapter(self.runtime.home,child_manifest)
            child=self.runtime.run(step['release'],mapped(step['inputs']),request_key=request_id+':step:'+str(index),parent_run_id=request_id)
            if child['status']=='awaiting_evaluation':child=self.runtime.evaluate_run(child['id'])
            if child['status'] in {'failed','cancelled'}:return {'status':'failed','handle':child['id'],'error':'A named child workflow did not complete its contract'}
            if child['status']!='completed':return {'status':'pending','handle':child['id']}
            outputs.append(child['output'])
        return {'status':'completed','output':mapped(manifest['execution']['output']),'usage':{'status':'unknown'}}

    def start(self,*,request_id,manifest,inputs):return self._advance(request_id,manifest,inputs)
    def inspect(self,*,request_id,handle):
        run=self.runtime.get(request_id)
        return self._advance(request_id,self.runtime.manifest(run['release_digest']),run['inputs'])


SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_judge_calibrations (
 id TEXT PRIMARY KEY,record_json TEXT NOT NULL,reviewer TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS workflow_calibration_no_update BEFORE UPDATE ON workflow_judge_calibrations
 BEGIN SELECT RAISE(ABORT,'judge calibration is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_calibration_no_delete BEFORE DELETE ON workflow_judge_calibrations
 BEGIN SELECT RAISE(ABORT,'judge calibration evidence is preserved'); END;
CREATE TABLE IF NOT EXISTS workflow_company (singleton INTEGER PRIMARY KEY CHECK(singleton=1),company_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_effects (
 id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES workflow_invocations(id),
 action_digest TEXT NOT NULL,action_json TEXT NOT NULL,adapter TEXT NOT NULL,
 status TEXT NOT NULL,token TEXT NOT NULL,provider_handle TEXT,error TEXT,
 actor TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
 UNIQUE(run_id,action_digest));
CREATE TABLE IF NOT EXISTS workflow_schema_versions (
 version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_releases (
 digest TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, version TEXT NOT NULL,
 manifest_json TEXT NOT NULL, review_json TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(workflow_id,version));
CREATE TABLE IF NOT EXISTS workflow_release_acceptance (
 digest TEXT PRIMARY KEY REFERENCES workflow_releases(digest),
 review_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_outcome_observations (
 id TEXT PRIMARY KEY,release_digest TEXT NOT NULL REFERENCES workflow_releases(digest),
 measurement_json TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS workflow_outcome_no_update BEFORE UPDATE ON workflow_outcome_observations
 BEGIN SELECT RAISE(ABORT,'outcome observations are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_outcome_no_delete BEFORE DELETE ON workflow_outcome_observations
 BEGIN SELECT RAISE(ABORT,'outcome history is preserved'); END;
CREATE TABLE IF NOT EXISTS workflow_usage_events (
 id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES workflow_invocations(id),
 event_key TEXT NOT NULL,stage TEXT NOT NULL,attempt INTEGER NOT NULL,
 usage_json TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,
 UNIQUE(run_id,event_key));
CREATE INDEX IF NOT EXISTS workflow_usage_run ON workflow_usage_events(run_id);
CREATE TRIGGER IF NOT EXISTS workflow_usage_no_update BEFORE UPDATE ON workflow_usage_events
 BEGIN SELECT RAISE(ABORT,'usage evidence is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_usage_no_delete BEFORE DELETE ON workflow_usage_events
 BEGIN SELECT RAISE(ABORT,'usage evidence is immutable'); END;
CREATE TABLE IF NOT EXISTS workflow_memories (
 id TEXT PRIMARY KEY,scope TEXT NOT NULL,workflow_id TEXT,claim TEXT NOT NULL,
 evidence_json TEXT NOT NULL,source TEXT,actor TEXT NOT NULL,created_at TEXT NOT NULL,
 status TEXT NOT NULL,retired_at TEXT,retirement_reason TEXT);
CREATE TRIGGER IF NOT EXISTS workflow_memory_no_rewrite BEFORE UPDATE OF scope,workflow_id,claim,evidence_json,source,actor,created_at ON workflow_memories
 BEGIN SELECT RAISE(ABORT,'memory claims and evidence are immutable; retire a superseded claim'); END;
CREATE TRIGGER IF NOT EXISTS workflow_memory_no_delete BEFORE DELETE ON workflow_memories
 BEGIN SELECT RAISE(ABORT,'memory history is preserved'); END;
CREATE INDEX IF NOT EXISTS workflow_memory_lookup ON workflow_memories(scope,workflow_id,status,created_at);
CREATE TABLE IF NOT EXISTS workflow_actor_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL,
 subject TEXT NOT NULL, payload_digest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS workflow_audit_no_update BEFORE UPDATE ON workflow_actor_audit
 BEGIN SELECT RAISE(ABORT,'actor audit is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_audit_no_delete BEFORE DELETE ON workflow_actor_audit
 BEGIN SELECT RAISE(ABORT,'actor audit is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_acceptance_no_update BEFORE UPDATE ON workflow_release_acceptance
 BEGIN SELECT RAISE(ABORT,'release acceptance is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_acceptance_no_delete BEFORE DELETE ON workflow_release_acceptance
 BEGIN SELECT RAISE(ABORT,'release acceptance is immutable'); END;
CREATE TABLE IF NOT EXISTS workflow_invocations (
 id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 release_digest TEXT NOT NULL REFERENCES workflow_releases(digest),
 inputs_json TEXT NOT NULL, status TEXT NOT NULL, provider_handle TEXT,
 output_json TEXT, evaluation_json TEXT, review_json TEXT,
 generation INTEGER NOT NULL DEFAULT 0, token TEXT,
 error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_action_reviews (
 run_id TEXT NOT NULL REFERENCES workflow_invocations(id), action_digest TEXT NOT NULL,
 actor TEXT NOT NULL, decision TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(run_id,action_digest));
CREATE TABLE IF NOT EXISTS workflow_export_outbox (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES workflow_invocations(id),
 payload_json TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 last_error TEXT, remote_reference TEXT);
CREATE TRIGGER IF NOT EXISTS workflow_export_payload_no_rewrite BEFORE UPDATE OF id,run_id,payload_json ON workflow_export_outbox
 BEGIN SELECT RAISE(ABORT,'telemetry evidence payloads are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_release_no_update BEFORE UPDATE ON workflow_releases
 BEGIN SELECT RAISE(ABORT,'workflow releases are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_release_no_delete BEFORE DELETE ON workflow_releases
 BEGIN SELECT RAISE(ABORT,'workflow releases are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_review_no_update BEFORE UPDATE ON workflow_action_reviews
 BEGIN SELECT RAISE(ABORT,'action decisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_review_no_delete BEFORE DELETE ON workflow_action_reviews
 BEGIN SELECT RAISE(ABORT,'action decisions are immutable'); END;
"""


from ..observability.experiments import SCHEMA as EXPERIMENT_SCHEMA
SCHEMA += EXPERIMENT_SCHEMA
from ..observability.sessions import SCHEMA as ACTIVITY_SCHEMA
SCHEMA += ACTIVITY_SCHEMA


class WorkflowRuntime:
    def __init__(self, path, *, adapters=None, readonly=False, home=None, principal=None, effect_adapters=None):
        from ..runtime.boundary import require_runtime_destination
        self.path = Path(path)
        self.readonly = readonly
        self.home = Path(home).resolve() if home is not None else None
        if self.home is None:
            for parent in self.path.resolve().parents:
                if (parent/'.spielos/layout.json').is_file():
                    self.home=parent
                    break
        self.authority = None
        self.principal = principal
        if self.home is not None:
            from ..security import CompanyAuthority
            self.authority = CompanyAuthority(self.home)
            if not self.path.resolve().is_relative_to(self.home / ".spielos/state"):
                raise PermissionError("Workflow state must belong to the selected company")
            self.authority.authorize(principal, "read")
        require_runtime_destination(self.path)
        if not readonly:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.adapters = {"host": HostAdapter(), **(adapters or {})}
        self.effect_adapters=effect_adapters or {}
        self.adapters['sequential']=SequentialAdapter(self)
        if readonly:
            if self.authority:
                with self.connect() as connection:self._verify_company(connection,initialize=False)
            return
        with self.connect() as connection:
            versions = connection.execute("SELECT name FROM sqlite_master WHERE name='workflow_schema_versions'").fetchone()
            if versions and connection.execute("SELECT COALESCE(MAX(version),0) FROM workflow_schema_versions").fetchone()[0] > 2:
                raise ValueError("workflow database requires a newer runtime")
            connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
            self._verify_company(connection,initialize=True)
            columns={row[1] for row in connection.execute("PRAGMA table_info(workflow_invocations)")}
            for name,definition in {"kind":"TEXT NOT NULL DEFAULT 'production'", "case_id":"TEXT",
                    "deadline_at":"REAL", "lease_until":"REAL", "usage_json":"TEXT",
                    "actor":"TEXT", "claimed_by":"TEXT", "memory_snapshot_json":"TEXT", "parent_run_id":"TEXT", "root_run_id":"TEXT", "experiment_id":"TEXT", "session_id":"TEXT", "cancel_requested":"INTEGER NOT NULL DEFAULT 0"}.items():
                if name not in columns: connection.execute(f"ALTER TABLE workflow_invocations ADD COLUMN {name} {definition}")
            connection.execute('CREATE INDEX IF NOT EXISTS workflow_pending ON workflow_invocations(kind,status,created_at)')
            # Pre-provenance releases remain readable, but need new actual
            # candidate evidence before they can dispatch production work.
            connection.execute("INSERT OR IGNORE INTO workflow_schema_versions VALUES(2,?)", (stamp(),))
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("database integrity check failed")
        from ..observability.automatic import enabled
        if self.home and enabled(self):
            import os
            host_id=os.environ.get('CODEX_THREAD_ID') or os.environ.get('CODEX_SESSION_ID')
            if host_id:
                from ..observability.sessions import Sessions
                roles=set(getattr(principal,'roles',()))
                role='evaluator' if roles=={'reviewer'} else 'builder' if roles=={'builder'} else 'director'
                boundary=Path.cwd()/'.spielos-boundary.json'
                if role=='director' and boundary.is_file() and json.loads(boundary.read_text()).get('role')=='source':
                    role='system_improvement'
                if roles & {'owner','operator','builder','reviewer'}:
                    self.activity_session_id=Sessions(self).start(host='codex',host_session=host_id,role=role,brief=True)['id']

    def _verify_company(self,connection,*,initialize):
        if not self.authority:return
        exists=connection.execute("SELECT name FROM sqlite_master WHERE name='workflow_company'").fetchone()
        row=connection.execute('SELECT company_id FROM workflow_company WHERE singleton=1').fetchone() if exists else None
        if row and row[0]!=self.authority.company_id:raise PermissionError('Database belongs to another company')
        if row is None:
            if not initialize:raise PermissionError('Database company identity has not been established')
            connection.execute('INSERT INTO workflow_company VALUES(1,?)',(self.authority.company_id,))

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(
            f"file:{self.path}?mode=ro" if self.readonly else str(self.path),
            timeout=30, uri=self.readonly)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def validate_manifest(self, manifest):
        required = {"id", "version", "purpose", "owner", "execution", "evaluation",
                    "input_schema", "output_schema", "dependencies", "context_versions"}
        if not isinstance(manifest, dict) or required - set(manifest):
            raise ValueError("release needs identity, owner, both harnesses, schemas and pinned context")
        for key in ("id", "version", "purpose", "owner"):
            if not isinstance(manifest[key], str) or not manifest[key].strip():
                raise ValueError(f"release needs {key}")
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',manifest['id']):raise ValueError('Workflow identity must be portable')
        execution = manifest["execution"]
        if not isinstance(execution, dict) or execution.get("provider") not in self.adapters:
            raise ValueError("execution provider is unavailable")
        if execution.get("effect_permissions") != []:
            raise ValueError("this pilot supports draft/pure work only; external-effect adapters are not installed")
        if not isinstance(execution.get("binding"), str) or not execution["binding"].strip():
            raise ValueError("execution harness needs a versioned binding")
        if not isinstance(execution.get("timeout_seconds"), int) or execution["timeout_seconds"] <= 0:
            raise ValueError("execution needs a positive timeout")
        # Automatic dispatch retries are deliberately absent. Reconciliation
        # examines the same request identity; it never starts another effect.
        if execution.get("retry_budget") != 0:
            raise ValueError("this release supports reconciliation, not automatic dispatch retries")
        for key in ("dependencies", "context_versions"):
            if not isinstance(manifest[key], dict) or any(not isinstance(v, str) or not v for v in manifest[key].values()):
                raise ValueError(f"{key} must pin explicit revisions")
        if execution['provider']=='sequential':self.adapters['sequential'].validate(manifest)
        evaluation = manifest["evaluation"]
        if not isinstance(evaluation, dict) or not evaluation.get("version"):
            raise ValueError("evaluation harness needs a version")
        from ..evals.standard import validate_standard
        validate_standard(evaluation)
        criteria = evaluation.get("criteria", [])
        cases = evaluation.get("cases", [])
        if (not isinstance(criteria, list) or not criteria or not isinstance(cases, list) or not cases
                or any(not isinstance(row, dict) for row in criteria + cases)):
            raise ValueError("release needs nonempty criteria and cases")
        for rows, label in ((criteria, "criterion"), (cases, "case")):
            ids = [row.get("id") for row in rows]
            if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
                raise ValueError(f"{label} identities must be nonempty and unique")
        from ..evals.contracts import validate_criterion
        for criterion in criteria: validate_criterion(criterion)
        if not any(row['severity']=='block' for row in criteria):
            raise ValueError("Evaluation requires a nonempty blocking population")
        if not {"representative", "held_out", "negative"}.issubset({case.get("split") for case in cases}):
            raise ValueError("release needs representative, held-out and negative cases")
        for case in cases:
            if ((case.get("split") in {"representative", "held_out"} and case.get("expected") != "pass")
                    or (case.get("split") == "negative" and case.get("expected") != "fail")):
                raise ValueError("reference and held-out cases must pass; negative cases must fail")
            validate(manifest["input_schema"], case.get("input"), "case.input")
            validate(manifest["output_schema"], case.get("reference"), "case.reference")
            if case.get("expected") not in {"pass", "fail"}:
                raise ValueError("case needs an expected quality outcome")
        policy=evaluation.get('review_policy','each_run')
        if policy not in {'each_run','release_only'}:raise ValueError('Unknown output-review policy')
        if policy=='release_only' and (any(row['evaluator'] not in {'check','reference'} for row in criteria) or execution['effect_permissions']):
            raise ValueError('Release-only review is limited to deterministic draft work')
        canonical(manifest)

    def _actor(self, action, supplied=None):
        if self.authority:
            actor = self.authority.authorize(self.principal, action)
            if supplied is not None and supplied != actor:
                raise PermissionError("Reviewer identity must match the authenticated principal")
            return actor
        # Direct Python harnesses are trusted local processes, not a team API.
        import os
        return supplied or f"os:{user_id()}"

    def _audit(self, connection, action, subject, payload, *, actor=None):
        connection.execute("INSERT INTO workflow_actor_audit(actor,action,subject,payload_digest,created_at) VALUES(?,?,?,?,?)",
            (actor or self._actor("read"), action, subject, digest(payload), stamp()))
        import os
        session_id=getattr(self,'activity_session_id',None) or os.environ.get('SPIELOS_SESSION_ID')
        if session_id:
            from ..observability.sessions import reviewed,sanitize,session_label
            session=connection.execute('SELECT * FROM activity_sessions WHERE id=?',(session_id,)).fetchone()
            if not session:raise ValueError('Operation references an unknown activity session')
            audit_id=connection.execute('SELECT last_insert_rowid()').fetchone()[0]
            identity=digest({'session':session_id,'audit':audit_id})
            now=stamp();record={'kind':'decision','payload':sanitize({'operation':action,'subject':subject,'evidence':payload})}
            first=connection.execute('SELECT id FROM activity_events WHERE session_id=? ORDER BY rowid LIMIT 1',(session_id,)).fetchone()
            event={'id':identity,'run_id':session_id,'session_id':session_id,'root_event_id':first[0] if first else identity,
                   'host_session_id':session_label(self,session),
                   'trace_run_id':session_id,'release_digest':'activity-v2','status':action,'at':now,'started_at':now,
                   'name':'SpielOS '+session['role']+' / '+action,'input_digest':digest(record),'output_digest':None,
                   'context_export':'reviewed_evidence' if reviewed(self) else 'digests_only'}
            if reviewed(self):event['evidence']={'input':{'operation':action,'subject':subject},'output':record['payload']}
            connection.execute('INSERT INTO activity_events VALUES(?,?,?,?,?,?,?)',
                (identity,session_id,'audit:'+str(audit_id),'decision',canonical(record),actor or self._actor('read'),now))
            connection.execute("INSERT INTO activity_exports(id,payload_json,status) VALUES(?,?,'pending')",(identity,canonical(event)))

    def evaluate(self, manifest, output, *, case_id=None, inputs=None, verdicts=None, evaluator=None, producer=None):
        from ..evals.contracts import evaluate
        from ..evals import contracts
        expected=manifest['evaluation'].get('implementation_digest')
        if expected and expected!=hashlib.sha256(Path(contracts.__file__).read_bytes()).hexdigest():
            raise ValueError('Evaluation implementation changed; qualify a new workflow release')
        case=next((row for row in manifest['evaluation']['cases'] if row['id']==case_id),None)
        report = evaluate(manifest,output,inputs=inputs if inputs is not None else case['input'] if case else {},
                          case_id=case_id,verdicts=verdicts,evaluator=evaluator,producer=producer)
        for criterion in manifest['evaluation']['criteria']:
            row = report['criteria'][criterion['id']]
            row['question'] = criterion.get('question')
            row['dimension'] = criterion.get('dimension')
            row['anchors'] = criterion['anchors']
            row['evidence'] = (verdicts or {}).get(criterion['id'], {}).get('evidence', row['reason'])
        report['subject']=manifest['evaluation'].get('subject','historical')
        report['standard']=manifest['evaluation'].get('standard','historical')
        if all(c.get('dimension') in {'behavior','safety','operational'} for c in manifest['evaluation']['criteria']):
            report['quality_domain']='behavior_and_operations'
        return report

    def candidate(self, manifest):
        actor=self._actor("build")
        if self.home:
            from ..home import CompanyHome
            CompanyHome(self.home).require_ready()
        manifest=deepcopy(manifest)
        for derived in ('resolved_context','resolved_agent','resolved_brand','invocation_memory'):
            manifest.pop(derived,None)
        if self.authority:
            for criterion in manifest.get('evaluation',{}).get('criteria',[]):
                if criterion.get('evaluator')!='model':continue
                judge=criterion.get('judge',{})
                with self.connect() as connection:record=connection.execute('SELECT record_json FROM workflow_judge_calibrations WHERE id=?',(judge.get('calibration_id'),)).fetchone()
                if not record:raise ValueError('A model judge needs an independently authenticated calibration record')
                calibration=json.loads(record[0])
                if any(judge.get(key)!=calibration['judge'][key] for key in ('model','prompt_digest','version')):raise ValueError('Judge differs from its reviewed calibration')
                judge['calibration']=calibration['ratings'];judge['maximum_disagreement']=calibration['policy']['maximum_disagreement']
        self.validate_manifest(manifest)
        from ..evals import contracts
        manifest['evaluation']['implementation_digest']=hashlib.sha256(Path(contracts.__file__).read_bytes()).hexdigest()
        provider=manifest['execution']['provider']
        adapter=self.adapters[provider]
        if hasattr(adapter,'revision'):
            supplied=manifest['execution'].get('implementation_digest')
            if supplied and supplied!=adapter.revision:raise ValueError('Execution code revision differs from the candidate')
            manifest['execution']['implementation_digest']=adapter.revision
        elif provider!='host':
            raise ValueError('Provider needs a pinned implementation revision')
        revisions={**manifest['dependencies'],**manifest['context_versions']}
        if provider=='host' and self.home is not None:
            from ..agents.loader import AgentCatalog
            binding=manifest['execution']['binding']
            if not binding.startswith('agent:'):raise ValueError('Host workflow must bind a reusable agent declaration')
            declaration,agent_revisions=AgentCatalog(self.home,self.principal).resolve(binding.removeprefix('agent:'))
            if set(revisions)&set(agent_revisions) and any(revisions.get(key,value) not in (value,'sha256:'+value) for key,value in agent_revisions.items()):
                raise ValueError('Agent dependencies conflict with pinned context')
            revisions.update(agent_revisions)
            manifest['resolved_agent']=declaration
        if manifest['execution'].get('brand_context') is not None and not manifest.get('brand_release'):
            raise ValueError('Brand context needs an approved pinned brand release')
        if manifest.get('brand_release'):
            if not self.home:raise ValueError('Brand must resolve within the selected company')
            from ..branding import BrandRegistry
            brand=BrandRegistry(self.home,self.principal).resolve(manifest['brand_release'])
            manifest['resolved_brand']={key:brand[key] for key in ('company_id','version','files','reviewer')}
            manifest['resolved_brand']['digest']=manifest['brand_release']
            manifest['resolved_brand']['source']='company/brand/releases/'+manifest['brand_release']+'.json'
        if revisions:
            if self.home is None:raise ValueError('Pinned context must resolve in an explicitly selected company home')
            from ..context.workflow import snapshot
            manifest['resolved_context']=snapshot(self.home,revisions)
        else:manifest['resolved_context']={}
        if manifest.get('brand_release'):
            import base64
            selected=manifest['execution'].get('brand_context')
            text_types={'.md','.css','.json','.html','.svg','.js','.mjs','.jsx','.ts','.tsx'}
            if selected is not None:
                if not isinstance(selected,list) or not selected or any(not isinstance(name,str) for name in selected) or len(set(selected))!=len(selected):
                    raise ValueError('Brand context must name a distinct nonempty pinned text subset')
                if any(name not in brand['files'] or Path(name).suffix not in text_types for name in selected):
                    raise ValueError('Brand context references an absent or non-text pinned file')
                selected=set(selected)
            elif brand.get('contract'):
                roles=brand['contract']['roles']
                selected=set(name for role in ('voice','tokens','components','templates') for name in roles[role])
            else:selected={name for name in brand['files'] if not name.startswith('examples/')}
            manifest['resolved_brand']['context_files']=sorted(selected)
            for name,encoded in brand['content'].items():
                if name not in selected or Path(name).suffix not in text_types:continue
                raw=base64.b64decode(encoded,validate=True)
                manifest['resolved_context']['brand/'+name]={'sha256':hashlib.sha256(raw).hexdigest(),'text':raw.decode('utf-8'),
                    'source':manifest['resolved_brand']['source']+'#'+name}
        if provider=='host' and any(name.startswith(('profile.md','strategy/','brand/','departments/')) for name in manifest['resolved_context']) and 'read_company' not in manifest.get('resolved_agent',{}).get('permissions',[]):
            raise PermissionError('The declared agent cannot receive company context outside its permitted scope')
        from ..context.workflow import projection
        projection(manifest['resolved_context'],token_budget=manifest['execution'].get('context_budget',6000),
                   critical=manifest['execution'].get('critical_context',[]))
        release_digest=digest(manifest)
        with self.connect() as connection:
            existing=connection.execute('SELECT digest FROM workflow_releases WHERE workflow_id=? AND version=?',
                (manifest['id'],manifest['version'])).fetchone()
            if existing:
                if existing[0]!=release_digest:raise ValueError('Candidate versions are immutable; use a new version')
                return release_digest
            connection.execute('INSERT INTO workflow_releases VALUES(?,?,?,?,?,?)',
                (release_digest,manifest['id'],manifest['version'],canonical(manifest),
                 canonical({'decision':'candidate','builder':actor}),stamp()))
            self._audit(connection,'candidate',release_digest,manifest,actor=actor)
        from ..observability.automatic import enabled
        if enabled(self):
            from ..observability.evaluators import register_manifest
            register_manifest(self,manifest,release_digest)
        return release_digest

    def release(self, release_digest, *, candidate_runs, reviewer=None):
        actor=self._actor('review',reviewer)
        manifest=self.manifest(release_digest)
        cases=manifest['evaluation']['cases']
        if not isinstance(candidate_runs,dict) or set(candidate_runs)!={case['id'] for case in cases}:
            raise ValueError('Release requires exact coverage by actual evaluated candidate runs')
        if len(set(candidate_runs.values()))!=len(candidate_runs):raise ValueError('Each acceptance case requires its own execution')
        reports=[]
        with self.connect() as connection:
            for case in cases:
                row=connection.execute('SELECT * FROM workflow_invocations WHERE id=?',(candidate_runs[case['id']],)).fetchone()
                if row is None or row['kind']!='candidate' or row['release_digest']!=release_digest or row['case_id']!=case['id']:
                    raise ValueError('Acceptance evidence must originate from this exact candidate and case')
                report=json.loads(row['evaluation_json'] or 'null')
                from ..evals.standard import matched
                if (not report or not matched(case, report)
                        or report['artifact_digest']!=digest(json.loads(row['output_json']))):
                    raise ValueError('Candidate execution did not meet the expected acceptance outcome')
                if self.authority and (row['actor']==actor or report.get('self_judged')):
                    raise PermissionError('Release needs independent review of the actual candidate evidence')
                reports.append({'run_id':row['id'],'case_id':case['id'],'evaluation':report})
            review={'reviewer':actor,'reports':reports,'decision':'accept','at':stamp(),
                    'independent':all(connection.execute('SELECT actor FROM workflow_invocations WHERE id=?',(rid,)).fetchone()[0]!=actor for rid in candidate_runs.values())}
            existing=connection.execute('SELECT digest FROM workflow_release_acceptance WHERE digest=?',(release_digest,)).fetchone()
            if existing:return release_digest
            improvement=None
            if self.authority:
                table=connection.execute("SELECT name FROM sqlite_master WHERE name='workflow_improvements'").fetchone()
                improvement=connection.execute("SELECT id FROM workflow_improvements WHERE candidate_digest=? AND stage='evaluate'",(release_digest,)).fetchone() if table else None
                if not improvement:raise ValueError('Workflow release requires an attached candidate in a bounded Improvement')
                from ..operations import require_release_telemetry
                require_release_telemetry(self,candidate_runs.values())
            connection.execute('INSERT INTO workflow_release_acceptance VALUES(?,?,?)',(release_digest,canonical(review),stamp()))
            if improvement:
                connection.execute("UPDATE workflow_improvements SET stage='accepted',decision_json=?,updated_at=? WHERE id=? AND stage='evaluate'",(canonical({'decision':'accept','reviewer':actor,'reason':'Independent acceptance of actual pinned candidate cases','candidate_digest':release_digest,'at':stamp()}),stamp(),improvement[0]))
            self._audit(connection,'release',release_digest,review,actor=actor)
        return release_digest

    def manifest(self, release_digest):
        self._actor("read")
        with self.connect() as connection:
            row = connection.execute("SELECT manifest_json FROM workflow_releases WHERE digest=?", (release_digest,)).fetchone()
        if row is None:
            raise KeyError("unknown workflow release")
        return json.loads(row[0])

    def get(self, run_id):
        self._actor("read")
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM workflow_invocations WHERE id=?", (run_id,)).fetchone()
            exports = connection.execute("SELECT status,attempts,last_error,remote_reference FROM workflow_export_outbox WHERE run_id=? ORDER BY rowid", (run_id,)).fetchall()
        if row is None:
            raise KeyError("unknown workflow run")
        result = dict(row)
        result["telemetry"] = {"events": [dict(item) for item in exports],
            "verified": bool(exports) and all(item["status"] == "verified" for item in exports)}
        result['qualification_state'] = ('awaiting_telemetry' if result['status']=='completed' and not result['telemetry']['verified'] else 'verified' if result['status']=='completed' else 'awaiting_quality')
        for key in ("inputs", "output", "evaluation", "review", "usage", "memory_snapshot"):
            result[key] = json.loads(result.pop(key + "_json") or "null")
        if self.home is not None:
            manifest=self.manifest(result['release_digest'])
            if manifest['execution']['provider']=='host':
                from ..context.workflow import projection
                result['assignment']={'agent':manifest['resolved_agent'],
                    'workflow':{'id':manifest['id'],'version':manifest['version'],'release_digest':result['release_digest']},
                    'output_schema':manifest['output_schema'],
                    'evaluation':{'standard':manifest['evaluation'].get('standard','historical'),
                        'version':manifest['evaluation']['version'],
                        'criteria':[{key:value for key,value in criterion.items() if key!='judge'} for criterion in manifest['evaluation']['criteria']]},
                    'instruction':manifest['execution'].get('instruction',manifest['purpose']),
                    'inputs':result['inputs'],'memory':result['memory_snapshot'],'brand':manifest.get('resolved_brand'),'context':projection(manifest['resolved_context'],
                        token_budget=manifest['execution'].get('context_budget',6000),
                        critical=manifest['execution'].get('critical_context',[])),
                    'external_effects':'draft only; publication requires a separate exact-action approval'}
        return result

    def run(self, release_digest, inputs, *, request_key, candidate_case=None, parent_run_id=None, experiment_id=None):
        actor=self._actor("run" if candidate_case is None else "build")
        if self.home:
            from ..home import CompanyHome
            CompanyHome(self.home).require_ready()
        manifest = self.manifest(release_digest)
        if candidate_case is None and manifest['evaluation'].get('standard')!='spielos-evaluation/2':
            raise ValueError('Historical workflow needs requalification under the current evaluation standard before new production work')
        validate(manifest["input_schema"], inputs, "input")
        if not isinstance(request_key, str) or not request_key.strip():
            raise ValueError("request identity is required")
        case=next((row for row in manifest['evaluation']['cases'] if row['id']==candidate_case),None)
        if candidate_case and (case is None or case['input']!=inputs):raise ValueError('Candidate inputs must match the pinned case')
        provider=manifest['execution']['provider']
        adapter=self.adapters.get(provider)
        if adapter is None:raise ValueError('Execution provider is unavailable')
        if manifest['execution'].get('implementation_digest') and getattr(adapter,'revision',None)!=manifest['execution']['implementation_digest']:
            raise ValueError('Execution implementation changed since candidate validation')
        parent=self.get(parent_run_id) if parent_run_id else None
        experiment_id=experiment_id or (parent['experiment_id'] if parent else None)
        if experiment_id:
            with self.connect() as connection:
                experiment=connection.execute('SELECT release_digest FROM workflow_experiments WHERE id=?',(experiment_id,)).fetchone()
            if not experiment or not parent and (experiment[0]!=release_digest or candidate_case is None):raise ValueError('Experiment must execute its exact pinned candidate cases')
        kind=('candidate' if candidate_case else 'candidate_component' if parent and parent['kind'] in {'candidate','candidate_component'} else 'component' if parent else 'production')
        root_run_id=(parent['root_run_id'] or parent['id']) if parent else None
        from ..context.workflow import WorkflowMemory
        learning=WorkflowMemory(self).active(manifest['id'],scopes=manifest.get('memory_scopes',['owner','strategy','workflow']),prompt=manifest['purpose']+' '+manifest['id'])
        if learning and provider=='local' and manifest['execution'].get('requires_memory') and manifest['execution'].get('context_transport')!='envelope_v1':
            raise ValueError('This workflow requires memory delivery through envelope_v1')
        deadline=time.time()+manifest['execution']['timeout_seconds']
        run_id = "invocation-" + uuid.uuid4().hex
        token = uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if candidate_case is None and not connection.execute('SELECT digest FROM workflow_release_acceptance WHERE digest=?',(release_digest,)).fetchone():
                raise ValueError('Production dispatch requires actual accepted candidate evidence')
            existing = connection.execute("SELECT id,release_digest,inputs_json,case_id,parent_run_id,experiment_id FROM workflow_invocations WHERE request_key=?", (request_key,)).fetchone()
            if existing:
                if existing[1] != release_digest or existing[2] != canonical(inputs) or existing[3]!=candidate_case or existing[4]!=parent_run_id or existing[5]!=experiment_id:
                    raise ValueError("request identity was already used with different content")
                run_id = existing[0]
            else:
                connection.execute("""INSERT INTO workflow_invocations
                    (id,request_key,release_digest,inputs_json,status,generation,token,created_at,updated_at,kind,case_id,deadline_at,lease_until,actor,memory_snapshot_json,parent_run_id,root_run_id,experiment_id)
                    VALUES(?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?)""", (run_id, request_key, release_digest, canonical(inputs), "dispatching", token, stamp(), stamp(),
                    kind,candidate_case,deadline,deadline,actor,canonical(learning),parent_run_id,root_run_id,experiment_id))
                import os
                session_id = getattr(self, 'activity_session_id', None) or os.environ.get('SPIELOS_SESSION_ID')
                if session_id:
                    if not connection.execute('SELECT id FROM activity_sessions WHERE id=?', (session_id,)).fetchone():
                        raise ValueError('Select a recorded SpielOS session before linking a workflow run')
                    connection.execute('UPDATE workflow_invocations SET session_id=? WHERE id=?', (session_id,run_id))
                self._audit(connection,'run',run_id,{'release':release_digest,'input_digest':digest(inputs)},actor=actor)
                self._queue_export(connection,run_id)
        if existing:
            return self.get(run_id)
        # Invocation identity is committed before any provider work.
        try:
            result = self._start_bounded(adapter,run_id,{**manifest,'invocation_memory':learning},inputs)
        except Exception as exc:
            result = {"status": "unknown", "error": str(exc)}
        return self._apply(run_id, token, result)

    @staticmethod
    def _start_bounded(adapter,run_id,manifest,inputs):
        if isinstance(adapter,(LocalAdapter,LocalFileAdapter)):
            return adapter.start(request_id=run_id,manifest=deepcopy(manifest),inputs=deepcopy(inputs))
        returned=[];event=threading.Event()
        def invoke():
            try:returned.append(adapter.start(request_id=run_id,manifest=deepcopy(manifest),inputs=deepcopy(inputs)))
            except Exception as exc:returned.append({'status':'unknown','error':str(exc)})
            finally:event.set()
        threading.Thread(target=invoke,daemon=True).start()
        if not event.wait(manifest['execution']['timeout_seconds']):
            return {'status':'unknown','error':'provider dispatch deadline exceeded; reconcile the same request'}
        return returned[0]

    def _apply(self, run_id, token, result):
        run = self.get(run_id)
        manifest = self.manifest(run["release_digest"])
        if not isinstance(result, dict):
            raise ValueError("provider result must be an object")
        provider_status = result.get("status")
        status = {"completed": "awaiting_evaluation", "pending": "awaiting_provider",
                  "failed": "failed", "cancelled": "cancelled", "unknown": "awaiting_reconciliation"}.get(provider_status)
        if status is None:
            raise ValueError("invalid provider result state")
        output = result.get("output")
        if status == "awaiting_evaluation":
            try:
                validate(manifest["output_schema"], output, "output")
            except ValueError as exc:
                status, output = "failed", None
                result = {**result, "error": str(exc)}
        if status == "awaiting_provider" and not result.get("handle"):
            raise ValueError("asynchronous providers require a durable handle")
        with self.connect() as connection:
            changed = connection.execute("""UPDATE workflow_invocations SET status=?,provider_handle=?,
                output_json=?,error=?,updated_at=?,usage_json=? WHERE id=? AND token=? AND status='dispatching'""",
                (status, result.get("handle") or run['provider_handle'], canonical(output) if output is not None else None,
                 result.get("error"), stamp(), canonical(self._usage(result.get("usage"))), run_id, token)).rowcount
            if changed != 1:
                raise RuntimeError("stale execution result")
            self._store_usage(connection,run_id,'provider:'+token,'provider',run['generation'],
                              self._usage(result.get('usage')),actor=run['actor'] or self._actor('run'))
            self._queue_export(connection, run_id)
        from ..observability.automatic import workflow_output
        return workflow_output(self,run_id)

    def reconcile(self, run_id):
        self._actor("run")
        run = self.get(run_id)
        if run["status"] not in {"dispatching", "awaiting_provider", "awaiting_reconciliation"}:
            return run
        manifest = self.manifest(run["release_digest"])
        now=time.time()
        if run['status']=='dispatching' and run['lease_until'] and run['lease_until']>now:
            return run
        if manifest['execution']['provider']=='host' and run['status']=='awaiting_provider' and run['deadline_at']>now:
            return run
        if manifest['execution']['provider']=='host' and run['deadline_at']<=now:
            with self.connect() as connection:
                connection.execute("UPDATE workflow_invocations SET status='failed',error='host assignment deadline exceeded',token=?,updated_at=? WHERE id=? AND token=?",
                    (uuid.uuid4().hex,stamp(),run_id,run['token']))
                self._queue_export(connection,run_id)
            return self.get(run_id)
        token = uuid.uuid4().hex
        with self.connect() as connection:
            changed = connection.execute("""UPDATE workflow_invocations SET status='dispatching',
                generation=generation+1,token=?,updated_at=?,lease_until=? WHERE id=? AND token=?""",
                (token, stamp(),time.time()+manifest["execution"]["timeout_seconds"], run_id, run["token"])).rowcount
            if changed != 1:
                raise RuntimeError("another reconciliation owns this run")
        try:
            result = self.adapters[manifest["execution"]["provider"]].inspect(
                request_id=run_id, handle=run["provider_handle"] or run_id)
        except Exception as exc:
            result = {"status": "unknown", "handle": run["provider_handle"], "error": str(exc)}
        return self._apply(run_id, token, result)

    def claim(self,run_id):
        actor=self._actor('run');run=self.get(run_id)
        manifest=self.manifest(run['release_digest'])
        if manifest['execution']['provider']!='host':raise ValueError('Only host work can be claimed')
        if run['deadline_at']<=time.time():raise RuntimeError('Host assignment deadline expired')
        # A workflow may explicitly restrict execution to a named principal.
        if manifest['execution'].get('assigned_principal',actor)!=actor:raise PermissionError('This host assignment names another executor')
        token=uuid.uuid4().hex
        with self.connect() as connection:
            changed=connection.execute("UPDATE workflow_invocations SET claimed_by=?,actor=?,token=?,generation=generation+1,updated_at=? WHERE id=? AND status='awaiting_provider' AND claimed_by IS NULL",
                (actor,actor,token,stamp(),run_id)).rowcount
            if changed!=1:raise RuntimeError('Host assignment is already claimed or closed')
            self._audit(connection,'claim',run_id,{'generation':run['generation']+1},actor=actor)
        return self.get(run_id)

    def deliver(self, run_id, output, *, token):
        actor=self._actor("run")
        run = self.get(run_id)
        manifest = self.manifest(run["release_digest"])
        if manifest["execution"]["provider"] != "host":
            raise ValueError("manual delivery is restricted to host assignments")
        validate(manifest["output_schema"], output, "output")
        if run['deadline_at'] is not None and run['deadline_at']<=time.time():
            raise RuntimeError('Host delivery deadline expired')
        if self.authority and run['claimed_by']!=actor:raise PermissionError('Claim the host assignment with its authenticated executor before delivering')
        with self.connect() as connection:
            changed = connection.execute("""UPDATE workflow_invocations SET status='awaiting_evaluation',
                output_json=?,updated_at=? WHERE id=? AND token=? AND status='awaiting_provider'""",
                (canonical(output), stamp(), run_id, token)).rowcount
            if changed != 1:
                raise RuntimeError("stale or duplicate host delivery")
            self._audit(connection,'deliver',run_id,{'output_digest':digest(output)},actor=actor)
            self._queue_export(connection, run_id)
        from ..observability.automatic import workflow_output
        return workflow_output(self,run_id)

    def evaluate_run(self, run_id, *, case_id=None, verdicts=None, evaluator=None):
        actor=self._actor("evaluate",evaluator)
        run = self.get(run_id)
        from ..observability.automatic import enabled
        if enabled(self) and run.get('evaluation') and verdicts is None and case_id in (None,run.get('case_id')):
            return run
        if run['status']!='awaiting_evaluation':
            if run['status'] not in {'awaiting_review','failed'} or run['output'] is None or not run['evaluation']:
                raise ValueError('Run has no delivered output awaiting evaluation or an attributable review revision')
            self._actor('review')
            if self.authority and actor==run['actor']:raise PermissionError('An independent reviewer must revise a completed evaluation')
        manifest = self.manifest(run["release_digest"])
        case = next((row for row in manifest["evaluation"]["cases"] if row["id"] == case_id), None)
        case_id=case_id or run['case_id']
        case = next((row for row in manifest['evaluation']['cases'] if row['id']==case_id),None)
        if case_id and (case is None or case['input']!=run['inputs']):
            raise ValueError('Evaluation case must match the actual run inputs')
        report = self.evaluate(manifest,run['output'],inputs=run['inputs'],case_id=case_id,
            verdicts=verdicts,evaluator=actor,producer=run['actor'])
        status = "awaiting_review" if report["state"] == "pass" else "failed" if report["state"] == "fail" else "awaiting_evaluation"
        policy_review=None
        if status=='awaiting_review' and run['kind'] in {'production','component','candidate_component'} and manifest['evaluation'].get('review_policy')=='release_only':
            with self.connect() as connection:
                accepted=connection.execute('SELECT review_json FROM workflow_release_acceptance WHERE digest=?',(run['release_digest'],)).fetchone()
            if not accepted:raise ValueError('Release-only acceptance needs an approved immutable release')
            policy_review={'decision':'accept','policy':'deterministic checks under independent release review',
                           'release_reviewer':json.loads(accepted[0])['reviewer'],'at':stamp()}
            status='completed'
        with self.connect() as connection:
            changed = connection.execute("""UPDATE workflow_invocations SET status=?,evaluation_json=?,updated_at=?,review_json=?
                WHERE id=? AND status=? AND token=?""",
                (status, canonical(report), stamp(),canonical(policy_review) if policy_review else None, run_id,run['status'], run["token"])).rowcount
            if changed != 1:
                raise RuntimeError("run changed during evaluation")
            self._audit(connection,'evaluate',run_id,report,actor=actor)
            self._queue_export(connection, run_id)
        return self.get(run_id)

    def review(self, run_id, *, reviewer=None, decision):
        reviewer=self._actor("review",reviewer)
        if not reviewer or decision not in {"accept", "reject"}:
            raise ValueError("named reviewer and accept/reject decision required")
        run = self.get(run_id)
        if run["status"] != "awaiting_review" or run["evaluation"]["state"] != "pass":
            raise ValueError("only a quality-passing run can be reviewed")
        if self.authority and (reviewer==run['actor'] or run['evaluation'].get('self_judged')):
            raise PermissionError('An independent authenticated reviewer must accept this output')
        review = {"reviewer": reviewer, "decision": decision, "at": stamp()}
        with self.connect() as connection:
            changed = connection.execute("""UPDATE workflow_invocations SET status=?,review_json=?,updated_at=?
                WHERE id=? AND status='awaiting_review'""",
                ("completed" if decision == "accept" else "failed", canonical(review), stamp(), run_id)).rowcount
            if changed != 1:
                raise RuntimeError("run already reviewed")
            self._audit(connection,'review',run_id,review,actor=reviewer)
            self._queue_export(connection, run_id)
        return self.get(run_id)

    def _store_usage(self,connection,run_id,event_key,stage,attempt,usage,*,actor):
        existing=connection.execute('SELECT usage_json,stage,attempt FROM workflow_usage_events WHERE run_id=? AND event_key=?',(run_id,event_key)).fetchone()
        if existing:
            if tuple(existing)!=(canonical(usage),stage,attempt):raise ValueError('Usage identity already refers to different evidence')
            return
        connection.execute('INSERT INTO workflow_usage_events VALUES(?,?,?,?,?,?,?,?)',
            (uuid.uuid4().hex,run_id,event_key,stage,attempt,canonical(usage),actor,stamp()))

    def record_usage(self,run_id,*,event_key,stage,attempt=1,usage):
        actor=self._actor('evaluate' if stage=='evaluation' else 'run')
        self.get(run_id)
        if stage not in {'provider','evaluation','media','external_service'} or not isinstance(event_key,str) or not event_key or not isinstance(attempt,int) or attempt<1:
            raise ValueError('Usage needs an explicit work stage, attempt and stable event identity')
        usage=self._usage(usage)
        with self.connect() as connection:
            self._store_usage(connection,run_id,event_key,stage,attempt,usage,actor=actor)
            self._audit(connection,'usage',run_id,{'key':event_key,'stage':stage,'usage':usage},actor=actor)
            self._queue_export(connection,run_id)

    @staticmethod
    def _usage(value):
        import math
        if value is None:return {'status':'unknown'}
        if not isinstance(value,dict) or value.get('status') not in {'actual','estimated','unknown'}:
            raise ValueError('Usage requires actual, estimated or unknown provenance')
        if value['status']=='unknown':return {'status':'unknown'}
        if not value.get('source'):raise ValueError('Measured and estimated usage require their source')
        for key in ('input_tokens','output_tokens','cost'):
            if key in value and (not isinstance(value[key],(int,float)) or isinstance(value[key],bool) or not math.isfinite(value[key]) or value[key]<0):
                raise ValueError('Usage values must be finite and nonnegative')
        if 'cost' in value and not value.get('currency'):raise ValueError('Costs require their currency')
        return {key:value[key] for key in ('status','source','input_tokens','output_tokens','cost','currency') if key in value}

    def cancel(self,run_id):
        actor=self._actor('run');run=self.get(run_id)
        if run['status'] in {'completed','failed','cancelled'}:return run
        manifest=self.manifest(run['release_digest']);provider=manifest['execution']['provider']
        token=uuid.uuid4().hex
        with self.connect() as connection:
            changed=connection.execute("UPDATE workflow_invocations SET status='dispatching',cancel_requested=1,generation=generation+1,token=?,updated_at=? WHERE id=? AND token=?",
                (token,stamp(),run_id,run['token'])).rowcount
            if changed!=1:raise RuntimeError('Run changed during cancellation')
            self._audit(connection,'cancel',run_id,{'generation':run['generation']+1},actor=actor)
        adapter=self.adapters[provider]
        try:
            result=({'status':'cancelled'} if provider=='host' else adapter.cancel(request_id=run_id,handle=run['provider_handle'] or run_id)
                    if hasattr(adapter,'cancel') else {'status':'unknown','error':'Provider cancellation is unconfirmed'})
        except Exception:result={'status':'unknown','error':'Provider cancellation is unconfirmed'}
        return self._apply(run_id,token,result)

    def _queue_export(self, connection, run_id):
        row = connection.execute("SELECT * FROM workflow_invocations WHERE id=?", (run_id,)).fetchone()
        manifest_row = connection.execute("SELECT manifest_json FROM workflow_releases WHERE digest=?", (row["release_digest"],)).fetchone()
        evaluation = json.loads(row["evaluation_json"] or "null")
        usage_rows=[dict(item) for item in connection.execute('SELECT event_key,stage,attempt,usage_json FROM workflow_usage_events WHERE run_id=? ORDER BY rowid',(run_id,))]
        event_id = digest({"run": run_id, "status": row["status"],
                           "evaluation": evaluation, "review": row["review_json"],"usage_entries":usage_rows})
        first = connection.execute("SELECT id FROM workflow_export_outbox WHERE run_id=? ORDER BY rowid LIMIT 1", (row['root_run_id'] or run_id,)).fetchone()
        root=connection.execute('SELECT case_id,experiment_id FROM workflow_invocations WHERE id=?',(row['root_run_id'] or run_id,)).fetchone()
        payload = {"experiment_id":root['experiment_id'],'experiment_case':root['case_id'],"id": event_id, "root_event_id": first[0] if first else event_id,
                   "run_id": run_id, "trace_run_id":row['root_run_id'] or run_id,"parent_run_id":row['parent_run_id'],"status": row["status"],
                   "input_digest": digest(json.loads(row["inputs_json"])),
                   "output_digest": digest(json.loads(row["output_json"])) if row["output_json"] else None,
                   "release_digest": row["release_digest"], "at": row["updated_at"],"started_at":row['created_at'],
                   "usage_entries":[{key:value for key,value in item.items() if key!='usage_json'} | {'usage':json.loads(item['usage_json'])} for item in usage_rows],
                   "workflow_version": json.loads(manifest_row[0])["version"],
                   "evaluation": evaluation, "usage": json.loads(row["usage_json"] or '{"status":"unknown"}'),
                   "context_export": "digests_only"}
        declaration=json.loads(manifest_row[0])
        payload.update({'trace_name':('Experiment · ' if root['experiment_id'] else 'Workflow · ')+declaration['purpose'],
            'name':({'awaiting_review':'Evaluate output · ','awaiting_evaluation':'Awaiting evaluation evidence · ','completed':'Accepted output · ','failed':'Quality or execution failure · ','awaiting_provider':'Assigned to executor · ','dispatching':'Start execution · '}.get(row['status'],'Workflow state · '))+declaration['purpose'],
            'category':'experiment' if root['experiment_id'] else 'workflow_review' if row['status']=='completed' else 'workflow_output' if evaluation else 'workflow_execution',
            'company_id':self.authority.company_id if self.authority else 'synthetic','workflow_id':declaration['id'],
            'agent_id':declaration.get('resolved_agent',{}).get('id'),'agent_name':declaration.get('resolved_agent',{}).get('description')})
        from ..observability.sessions import reviewed, sanitize, session_label
        if row['session_id']:
            payload['session_id'] = row['session_id']
            session=connection.execute('SELECT * FROM activity_sessions WHERE id=?',(row['session_id'],)).fetchone()
            payload['host_session_id']=session_label(self,session)
        if reviewed(self):
            manifest = json.loads(manifest_row[0])
            payload['name'] = manifest['id']+' / '+row['status']
            payload['context_export'] = 'reviewed_evidence'
            payload['evidence'] = sanitize({'input': json.loads(row['inputs_json']),
                'output': json.loads(row['output_json'] or 'null'),
                'context': {'documents': manifest.get('resolved_context', {}), 'agent': manifest.get('resolved_agent'),
                            'memory': json.loads(row['memory_snapshot_json'] or 'null')},
                'evaluation_contract': manifest['evaluation']})
            payload['evaluation'] = sanitize(evaluation)
        if root['experiment_id']:connection.execute('UPDATE workflow_experiments SET remote_verified=0 WHERE id=?',(root['experiment_id'],))
        connection.execute("""INSERT OR IGNORE INTO workflow_export_outbox
            (id,run_id,payload_json,status) VALUES(?,?,?,'pending')""", (event_id,run_id,canonical(payload)))

    def export_pending(self, client, *, limit=10, max_attempts=20):
        self._actor('configure')
        return self._export_pending(client,limit=limit,max_attempts=max_attempts)

    def _export_pending(self, client, *, limit=10, max_attempts=20):
        if self.home and (self.home/'.spielos/telemetry.json').is_file():
            config=json.loads((self.home/'.spielos/telemetry.json').read_text())
            if config.get('enabled') is not True or client.project_id!=config.get('project_id') or client.base_url!=config.get('base_url'):
                raise PermissionError('Export destination differs from the approved company configuration')
        """One explicit wake; remote confirmation is separate from delivery.

        Unknown OTLP delivery never triggers a second span export. Subsequent
        wakes read back the fixed identity and retry idempotent score writes.
        """
        from ..observability.langfuse import ExportError
        if not 1 <= limit <= 100 or not 1 <= max_attempts <= 100:
            raise ValueError("export limit and attempt budget must be between 1 and 100")
        with self.connect() as connection:
            rows = connection.execute("""SELECT id FROM workflow_export_outbox
                WHERE status!='verified' AND attempts<? ORDER BY rowid LIMIT ?""", (max_attempts,limit)).fetchall()
        if hasattr(client, "begin_batch"):
            client.begin_batch()
        from ..observability.experiments import sync_resources,enrich_event
        sync_resources(self,client,max_attempts=max_attempts)
        results = []
        for selected in rows:
            with self.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT * FROM workflow_export_outbox WHERE id=?", (selected[0],)).fetchone()
                if row["status"] == "verified" or row["attempts"] >= max_attempts:
                    continue
                event=enrich_event(self,client,json.loads(row['payload_json']))
                if event is None:
                    results.append({'event_id':row['id'],'status':'awaiting_experiment_setup','reference':None,'error':None})
                    continue
                allow_ingest = row["status"] == "pending"
                connection.execute("UPDATE workflow_export_outbox SET status='sending',attempts=attempts+1 WHERE id=?", (row["id"],))
            try:
                reference = client.export(event, allow_ingest=allow_ingest)
                status, error = ("verified" if reference else "awaiting_readback"), None
            except ExportError as exc:
                reference = None
                status = "awaiting_readback" if exc.ambiguous or not allow_ingest else "pending"
                error = str(exc)  # sanitized by the transport, never response data
            except Exception:
                reference, status, error = None, "awaiting_readback", "export failed; inspect the connection"
            if status!='verified' and row['attempts']+1>=max_attempts:
                status='exhausted'
                error=error or 'Remote verification budget exhausted; inspect the connection before another explicit attempt'
            with self.connect() as connection:
                connection.execute("""UPDATE workflow_export_outbox SET status=?,last_error=?,remote_reference=?
                    WHERE id=? AND status!='verified'""", (status,error,reference,row["id"]))
                current = connection.execute("SELECT status,remote_reference FROM workflow_export_outbox WHERE id=?", (row["id"],)).fetchone()
            results.append({"event_id": row["id"], "status": current[0], "reference": current[1], "error": error})
        from ..observability.experiments import confirm_experiments
        confirm_experiments(self,client)
        return results

    def wake(self,*,run_id=None,client=None):
        """One host-triggered wake; no scheduler, polling loop or hidden home setup."""
        self._actor('read')
        result={'run':self.reconcile(run_id) if run_id else None,'telemetry':{'state':'disabled','events':[]}}
        if client is not None:
            result['telemetry']={'state':'explicit','events':self.export_pending(client,limit=5,max_attempts=3)}
            return result
        if self.home is None:return result
        config_path=self.home/'.spielos/telemetry.json'
        if not config_path.is_file():return result
        if config_path.is_symlink():raise PermissionError('Telemetry configuration must be local to the company')
        config=json.loads(config_path.read_text())
        if config.get('enabled') is not True:return result
        if config.get('provider')!='langfuse' or config.get('payload_policy') not in {'digests_only','reviewed_evidence'}:
            raise ValueError('Telemetry configuration needs an explicit provider and approved payload policy')
        from ..observability.langfuse import LangfuseClient
        try:
            transport=LangfuseClient.from_configuration(self.home,config)
            if transport.project_id!=config.get('project_id') or transport.base_url!=config.get('base_url'):
                raise PermissionError('Telemetry connection differs from the company-approved project')
            if config.get('automatic',{}).get('enabled'):
                from ..observability.automatic import drain
                result['telemetry']=drain(self,client=transport)
                return result
            result['telemetry']={'state':'enabled','events':self._export_pending(transport,limit=5,max_attempts=3)}
            if config.get('payload_policy') == 'reviewed_evidence':
                from ..observability.sessions import Sessions
                result['telemetry']['activity'] = Sessions(self).export(transport,limit=10,max_attempts=20)
        except PermissionError:raise
        except Exception:
            result['telemetry']={'state':'unavailable','events':[],
                'issue':'Langfuse verification is incomplete; work remains locally journaled and observability is pending'}
        return result

    def approve_action(self, run_id, action, *, reviewer=None, decision):
        reviewer=self._actor("approve",reviewer)
        run = self.get(run_id)
        if run["status"] != "completed":
            raise ValueError("action approval requires an accepted output")
        if not reviewer or decision not in {"approve", "reject"}:
            raise ValueError("explicit named action decision required")
        if not isinstance(action, dict) or set(action) != {"action", "destination", "content_digest", "scope"}:
            raise ValueError("approval must bind exact action, destination, content digest and scope")
        if action["content_digest"] != digest(run["output"]) or any(not isinstance(v, str) or not v.strip() for v in action.values()):
            raise ValueError("approval must bind the accepted artifact")
        action_digest = digest(action)
        with self.connect() as connection:
            connection.execute("INSERT INTO workflow_action_reviews VALUES(?,?,?,?,?)",
                (run_id, action_digest, reviewer, decision, stamp()))
            self._audit(connection,'approve_action',run_id,{'action_digest':action_digest,'decision':decision},actor=reviewer)
        return action_digest


    def execute_action(self,run_id,action,*,adapter):
        actor=self._actor('run');run=self.get(run_id)
        if run['status']!='completed' or not isinstance(action,dict) or set(action)!={'action','destination','content_digest','scope'} or action['content_digest']!=digest(run['output']):
            raise ValueError('Dispatch requires the exact accepted output and action scope')
        if adapter not in self.effect_adapters:raise ValueError('No effect adapter is installed for this explicit action')
        provider=self.effect_adapters[adapter]
        timeout=getattr(provider,'timeout_seconds',30)
        if not isinstance(timeout,(int,float)) or not 0<timeout<=600:raise ValueError('Effect provider timeout must be bounded')
        action_digest=digest(action);identity='effect-'+uuid.uuid4().hex;token=uuid.uuid4().hex
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            review=connection.execute('SELECT decision FROM workflow_action_reviews WHERE run_id=? AND action_digest=?',(run_id,action_digest)).fetchone()
            if not review or review[0]!='approve':raise PermissionError('This exact action, destination, content and scope have not been approved')
            existing=connection.execute('SELECT * FROM workflow_effects WHERE run_id=? AND action_digest=?',(run_id,action_digest)).fetchone()
            if existing:
                if existing['adapter']!=adapter:raise ValueError('Approved action is already assigned to another provider')
                return dict(existing)
            connection.execute('INSERT INTO workflow_effects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,run_id,action_digest,canonical(action),adapter,'dispatching',token,None,None,actor,stamp(),stamp()))
            self._audit(connection,'effect_dispatch',identity,{'action_digest':action_digest},actor=actor)
        returned=[];finished=threading.Event()
        def dispatch():
            try:returned.append(provider.start(request_id=identity,action=deepcopy(action),output=deepcopy(run['output'])))
            except Exception:returned.append({'status':'unknown','error':'Effect response is unavailable; reconcile the same action'})
            finally:finished.set()
        threading.Thread(target=dispatch,daemon=True).start()
        result=returned[0] if finished.wait(timeout) else {'status':'unknown','error':'Effect deadline exceeded; reconcile the same action'}
        return self._apply_effect(identity,token,result)

    def _apply_effect(self,identity,token,result):
        if not isinstance(result,dict) or result.get('status') not in {'completed','pending','failed','unknown','cancelled'}:
            result={'status':'unknown','error':'Effect adapter returned an invalid response'}
        status={'completed':'completed','pending':'awaiting_provider','failed':'failed','unknown':'awaiting_reconciliation','cancelled':'cancelled'}[result['status']]
        with self.connect() as connection:
            changed=connection.execute("UPDATE workflow_effects SET status=?,provider_handle=COALESCE(?,provider_handle),error=?,updated_at=? WHERE id=? AND token=? AND status='dispatching'",
                (status,result.get('handle'),result.get('error'),stamp(),identity,token)).rowcount
            if changed!=1:raise RuntimeError('Stale effect result')
            row=connection.execute('SELECT * FROM workflow_effects WHERE id=?',(identity,)).fetchone()
        return dict(row)

    def reconcile_action(self,identity):
        self._actor('run')
        with self.connect() as connection:row=connection.execute('SELECT * FROM workflow_effects WHERE id=?',(identity,)).fetchone()
        if row is None:raise KeyError('Unknown action execution')
        if row['status'] in {'completed','failed','cancelled'}:return dict(row)
        adapter=self.effect_adapters.get(row['adapter'])
        if adapter is None:raise ValueError('Effect provider is unavailable; no replay was attempted')
        if row['status']=='dispatching' and datetime.fromisoformat(row['updated_at']).timestamp()+getattr(adapter,'timeout_seconds',30)>time.time():
            return dict(row)
        token=uuid.uuid4().hex
        with self.connect() as connection:
            changed=connection.execute("UPDATE workflow_effects SET status='dispatching',token=?,updated_at=? WHERE id=? AND token=?",(token,stamp(),identity,row['token'])).rowcount
            if changed!=1:raise RuntimeError('Another reconciliation owns this action')
        try:result=adapter.inspect(request_id=identity,handle=row['provider_handle'] or identity)
        except Exception:result={'status':'unknown','error':'Effect result remains unconfirmed'}
        return self._apply_effect(identity,token,result)

    def snapshot(self,destination):
        self._actor('configure')
        from ..runtime.boundary import require_runtime_destination
        target=Path(destination).expanduser().resolve();require_runtime_destination(target)
        if target==self.path.resolve():raise ValueError('Snapshot must use a separate, explicitly selected path')
        target.parent.mkdir(parents=True,exist_ok=True)
        descriptor=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
        copied=sqlite3.connect(target)
        try:
            with self.connect() as connection:connection.backup(copied)
            if copied.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Snapshot integrity check failed')
        finally:copied.close()
        return {'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                'policy':'history and pending identities preserved; effects are never replayed by restoration'}
