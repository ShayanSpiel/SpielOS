"""Bounded GODAE development records, not autonomous outcome pursuit."""
import json,uuid
from pathlib import Path
from .home import canonical
from .workflows.runs import stamp,digest

SCHEMA='''CREATE TABLE IF NOT EXISTS workflow_improvements (
 id TEXT PRIMARY KEY,brief_json TEXT NOT NULL,stage TEXT NOT NULL,
 observation_json TEXT,architecture_json TEXT,candidate_digest TEXT,
 decision_json TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_change_evidence (
 improvement_id TEXT PRIMARY KEY REFERENCES workflow_improvements(id),
 evidence_json TEXT NOT NULL,producer TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_improvement_reconciliation (
 improvement_id TEXT PRIMARY KEY REFERENCES workflow_improvements(id),
 record_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_change_revisions (
 id TEXT PRIMARY KEY,improvement_id TEXT NOT NULL,record_json TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS workflow_change_revision_no_update BEFORE UPDATE ON workflow_change_revisions
 BEGIN SELECT RAISE(ABORT,'change revision history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workflow_change_revision_no_delete BEFORE DELETE ON workflow_change_revisions
 BEGIN SELECT RAISE(ABORT,'change revision evidence is preserved'); END;
'''


class Improvements:
    def __init__(self,runtime):
        self.runtime=runtime
        if not runtime.readonly:
            with runtime.connect() as connection:connection.executescript(SCHEMA)

    def create(self,brief):
        actor=self.runtime._actor('build')
        required={'name','business_need','owner','baseline','target','constraints','intended_users','outcome_window','allowed_files'}
        if not isinstance(brief,dict) or set(brief)!=required:raise ValueError('Improvement needs the bounded business brief and exact allowed files')
        if any(not isinstance(brief[key],str) or not brief[key].strip() for key in required-{'constraints','intended_users','allowed_files'}):
            raise ValueError('Unknown baseline must be recorded explicitly as unknown')
        for key in ('constraints','intended_users','allowed_files'):
            if not isinstance(brief[key],list) or not brief[key] or any(not isinstance(value,str) or not value.strip() for value in brief[key]):
                raise ValueError('Improvement needs explicit '+key)
        for name in brief['allowed_files']:
            path=Path(name)
            if path.is_absolute() or '..' in path.parts or '*' in name or path.as_posix()!=name:raise ValueError('Improvement file boundaries must be exact relative paths')
        identity='improvement-'+uuid.uuid4().hex
        with self.runtime.connect() as connection:
            connection.execute('INSERT INTO workflow_improvements(id,brief_json,stage,created_at,updated_at) VALUES(?,?,?,?,?)',
                (identity,canonical(brief),'observe',stamp(),stamp()))
            self.runtime._audit(connection,'improvement_create',identity,brief,actor=actor)
        return self.get(identity)

    def get(self,identity):
        self.runtime._actor('read')
        with self.runtime.connect() as connection:
            row=connection.execute('SELECT * FROM workflow_improvements WHERE id=?',(identity,)).fetchone()
            tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            evidence=connection.execute('SELECT evidence_json FROM workflow_change_evidence WHERE improvement_id=?',(identity,)).fetchone() if 'workflow_change_evidence' in tables else None
            reconciliation=connection.execute('SELECT record_json FROM workflow_improvement_reconciliation WHERE improvement_id=?',(identity,)).fetchone() if 'workflow_improvement_reconciliation' in tables else None
            revisions=[json.loads(r[0]) for r in connection.execute('SELECT record_json FROM workflow_change_revisions WHERE improvement_id=? ORDER BY rowid DESC LIMIT 20',(identity,))] if 'workflow_change_revisions' in tables else []
        if row is None:raise KeyError('Unknown improvement')
        value=dict(row)
        for key in ('brief','observation','architecture','decision'):value[key]=json.loads(value.pop(key+'_json') or 'null')
        if evidence:value['change_evidence']=json.loads(evidence[0])
        if reconciliation:value['reconciliation']=json.loads(reconciliation[0])
        value['revisions']=revisions
        return value

    def observe(self,identity,observation):
        actor=self.runtime._actor('build');row=self.get(identity)
        if row['stage']!='observe':raise ValueError('Observation is already agreed')
        if not isinstance(observation,dict) or not all(observation.get(key) for key in ('process','examples','failures','criterion_ids','evidence_sources')):
            raise ValueError('Observation needs real process evidence, examples, failures and stable criteria')
        if len(observation['criterion_ids'])!=len(set(observation['criterion_ids'])):raise ValueError('Criterion identities must be distinct')
        with self.runtime.connect() as connection:
            changed=connection.execute("UPDATE workflow_improvements SET observation_json=?,stage='decide',updated_at=? WHERE id=? AND stage='observe'",
                (canonical(observation),stamp(),identity)).rowcount
            if changed!=1:raise RuntimeError('Improvement changed during observation')
            self.runtime._audit(connection,'improvement_observe',identity,observation,actor=actor)
        return self.get(identity)

    def agree_architecture(self,identity,architecture):
        actor=self.runtime._actor('configure');row=self.get(identity)
        if row['stage']!='decide':raise ValueError('Architecture needs the observed acceptance brief')
        if not isinstance(architecture,dict) or not all(architecture.get(key) for key in ('chosen_provider','alternatives','tradeoffs','execution_contract','evaluation_contract','cost_envelope','test_plan')) or 'permissions' not in architecture:
            raise ValueError('Agree both harnesses, provider tradeoffs, permissions, costs and tests together')
        architecture={**architecture,'agreed_by':actor}
        with self.runtime.connect() as connection:
            changed=connection.execute("UPDATE workflow_improvements SET architecture_json=?,stage='act',updated_at=? WHERE id=? AND stage='decide'",
                (canonical(architecture),stamp(),identity)).rowcount
            if changed!=1:raise RuntimeError('Improvement changed during architecture review')
            self.runtime._audit(connection,'improvement_architecture',identity,architecture,actor=actor)
        return self.get(identity)

    def attach_candidate(self,identity,release_digest,*,changed_files):
        actor=self.runtime._actor('build');row=self.get(identity)
        if row['stage']!='act':raise ValueError('Implement only after agreeing the bounded architecture')
        if not isinstance(changed_files,list) or not changed_files or set(changed_files)-set(row['brief']['allowed_files']):
            raise ValueError('Candidate exceeds the agreed exact file boundary')
        manifest=self.runtime.manifest(release_digest)
        criteria={criterion['id'] for criterion in manifest['evaluation']['criteria']}
        if criteria!=set(row['observation']['criterion_ids']):raise ValueError('Execution and evaluation must retain the agreed criterion identities')
        with self.runtime.connect() as connection:
            changed=connection.execute("UPDATE workflow_improvements SET candidate_digest=?,stage='evaluate',updated_at=? WHERE id=? AND stage='act'",
                (release_digest,stamp(),identity)).rowcount
            if changed!=1:raise RuntimeError('Improvement changed during implementation')
            self.runtime._audit(connection,'improvement_candidate',identity,{'candidate':release_digest,'changed_files':changed_files},actor=actor)
        return self.get(identity)

    def decide(self,identity,*,decision,reason,candidate_runs=None):
        actor=self.runtime._actor('review');row=self.get(identity)
        if row['stage']=='awaiting_change_review':
            return self.review_change(identity,decision=decision,reason=reason)
        if row['stage']!='evaluate' or decision not in {'accept','revise','reject'} or not isinstance(reason,str) or not reason.strip():
            raise ValueError('Release review needs an explicit accept, revise or reject decision and reason')
        if decision=='accept':
            self.runtime.release(row['candidate_digest'],candidate_runs=candidate_runs)
            # The release and development decision are committed together.
            if self.get(identity)['stage']=='accepted':return self.get(identity)
        record={'decision':decision,'reason':reason,'reviewer':actor,'candidate_digest':row['candidate_digest'],'at':stamp()}
        with self.runtime.connect() as connection:
            changed=connection.execute('UPDATE workflow_improvements SET stage=?,decision_json=?,updated_at=? WHERE id=? AND stage=\'evaluate\'',
                ('act' if decision=='revise' else 'accepted' if decision=='accept' else 'rejected',canonical(record),stamp(),identity)).rowcount
            if changed!=1:raise RuntimeError('Improvement changed during release review')
            self.runtime._audit(connection,'improvement_decision',identity,record,actor=actor)
        return self.get(identity)

    def attach_change(self,identity,*,root,changed_files,evidence_files):
        """System changes have real file/test evidence, not a fake business workflow."""
        actor=self.runtime._actor('build');row=self.get(identity)
        if row['stage']!='act':raise ValueError('Change evidence needs the agreed implementation stage')
        if not changed_files or set(changed_files)-set(row['brief']['allowed_files']):
            raise ValueError('Change exceeds the agreed exact file boundary')
        if not isinstance(evidence_files,list) or not evidence_files:raise ValueError('Actual acceptance evidence files are required')
        from .operations import measured_files
        artifacts={}
        for name in evidence_files:
            path=Path(name).expanduser().resolve()
            artifacts[str(path)]=measured_files(path.parent,[path.name])[path.name]
        record={'root':str(Path(root).resolve()),'files':measured_files(root,changed_files),
                'acceptance_evidence':artifacts,'producer':actor,'status':'awaiting_independent_review'}
        from .observability.sessions import reviewed
        if reviewed(self.runtime):
            reports=[]
            for name in evidence_files:
                try:value=json.loads(Path(name).read_text())
                except (ValueError,UnicodeError):continue
                if value.get('standard')=='spielos-evaluation/2' and value.get('subject')=='system_improvement':reports.append(value)
            if not reports or any(not report.get('checks') or any(not all(check.get(key) for key in ('question','expected','actual','evidence')) or check.get('passed') is not True for check in report['checks']) for report in reports):
                raise ValueError('System acceptance needs actual behavioral questions, expected/observed results and passing evidence; file hashes alone are provenance')
            session_id=getattr(self.runtime,'activity_session_id',None)
            if not session_id:raise ValueError('Attach system evidence from its recorded activity session')
            record['evaluation_session_id']=session_id
            record['behavioral_reports']=reports
        with self.runtime.connect() as connection:
            connection.execute('INSERT OR REPLACE INTO workflow_change_evidence VALUES(?,?,?,?)',(identity,canonical(record),actor,stamp()))
            changed=connection.execute("UPDATE workflow_improvements SET stage='awaiting_change_review',updated_at=? WHERE id=? AND stage='act'",(stamp(),identity)).rowcount
            if changed!=1:raise RuntimeError('Improvement changed during evidence attachment')
            self.runtime._audit(connection,'improvement_change_evidence',identity,record,actor=actor)
        return self.get(identity)

    def review_change(self,identity,*,decision,reason):
        actor=self.runtime._actor('review');row=self.get(identity)
        if row['stage']!='awaiting_change_review' or decision not in {'accept','revise','reject'} or not reason:
            raise ValueError('Change review needs actual evidence and an explicit decision')
        with self.runtime.connect() as connection:stored=connection.execute('SELECT * FROM workflow_change_evidence WHERE improvement_id=?',(identity,)).fetchone()
        record=json.loads(stored['evidence_json'])
        if actor==stored['producer']:raise PermissionError('An independent reviewer must accept the system change')
        from .operations import measured_files
        if decision=='accept':
            if record.get('evaluation_session_id'):
                from .operations import require_activity_telemetry
                require_activity_telemetry(self.runtime,record['evaluation_session_id'])
            if measured_files(record['root'],list(record['files']))!=record['files']:raise ValueError('Changed files differ from the reviewed evidence')
            for name,expected in record['acceptance_evidence'].items():
                path=Path(name)
                if measured_files(path.parent,[path.name])[path.name]!=expected:raise ValueError('Acceptance evidence changed')
        review={'decision':decision,'reason':reason,'reviewer':actor,'at':stamp(),'evidence':record}
        with self.runtime.connect() as connection:
            connection.execute('UPDATE workflow_improvements SET stage=?,decision_json=?,updated_at=? WHERE id=?',
                ('accepted' if decision=='accept' else 'act' if decision=='revise' else 'rejected',canonical(review),stamp(),identity))
            self.runtime._audit(connection,'improvement_change_review',identity,review,actor=actor)
        return self.get(identity)

    def reconcile(self,identity,*,evidence_files,reason):
        """Preserve unresolved historical implementation claims without upgrading acceptance."""
        actor=self.runtime._actor('configure');row=self.get(identity)
        if row['stage'] in {'accepted','rejected'} or not reason:raise ValueError('Reconcile an unresolved record with its explicit reason')
        from .operations import measured_files
        artifacts={}
        for name in evidence_files:
            path=Path(name).resolve();artifacts[str(path)]=measured_files(path.parent,[path.name])[path.name]
        record={'reason':reason,'evidence_files':artifacts,'acceptance':'not_granted','actor':actor}
        with self.runtime.connect() as connection:
            connection.execute('INSERT OR REPLACE INTO workflow_improvement_reconciliation VALUES(?,?,?)',(identity,canonical(record),stamp()))
            self.runtime._audit(connection,'improvement_reconcile',identity,record,actor=actor)
        return {**self.get(identity),'reconciliation':record}

    def revise(self,identity,*,reason):
        """Withdraw pending evidence for another bounded draft; never self-accept."""
        actor=self.runtime._actor('build');row=self.get(identity)
        if row['stage'] not in {'awaiting_change_review','evaluate'} or not isinstance(reason,str) or not reason.strip():
            raise ValueError('Only pending unaccepted evidence can be revised, with an explicit reason')
        record={'reason':reason,'previous_stage':row['stage'],'previous_candidate':row['candidate_digest'],
                'previous_evidence':row.get('change_evidence'),'actor':actor,'at':stamp(),
                'acceptance':'withdrawn; fresh evidence and independent review required'}
        with self.runtime.connect() as connection:
            changed=connection.execute("UPDATE workflow_improvements SET stage='act',updated_at=? WHERE id=? AND stage=?",(stamp(),identity,row['stage'])).rowcount
            if changed!=1:raise RuntimeError('Improvement changed while recording its revision')
            connection.execute('INSERT INTO workflow_change_revisions VALUES(?,?,?,?)',(digest(record),identity,canonical(record),stamp()))
            self.runtime._audit(connection,'improvement_revise',identity,record,actor=actor)
        return self.get(identity)
