"""Pinned, scoped company documents; content snapshots carry their own provenance."""
from pathlib import Path
import hashlib
from ..home import CompanyHome,canonical


def snapshot(home,revisions):
    company=CompanyHome(home)
    if not company.lean:raise ValueError('Workflow context needs a lean company home')
    result={}
    for name,expected in sorted(revisions.items()):
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise ValueError('Context paths must stay inside company content')
        if relative.parts[0] not in {'profile.md','evaluation-and-learning-contract.md','strategy','brand','skills','agents','connections','departments','workflows'}:
            raise ValueError('Context is outside company content')
        if relative.parts[0]=='connections':
            raise ValueError('Connection definitions must be resolved as non-secret provider requirements, not prompt context')
        path=company.content/relative
        if path.is_symlink() or not path.resolve().is_relative_to(company.content.resolve()) or not path.is_file():
            raise ValueError('Context must name an existing contained company file')
        content=path.read_bytes()
        if len(content)>1024*1024:raise ValueError('Context document exceeds the bounded snapshot size')
        actual=hashlib.sha256(content).hexdigest()
        if expected not in (actual,'sha256:'+actual):raise ValueError('Context revision does not match actual company content: '+name)
        result[name]={'sha256':actual,'text':content.decode('utf-8'),'source':'company/'+name}
    return result


def projection(documents,*,token_budget=6000,critical=()):
    """A predictable budget: never silently trim the workflow's constraints."""
    if not isinstance(token_budget,int) or token_budget<1:raise ValueError('A positive context budget is required')
    if set(critical)-set(documents):raise ValueError('Critical context is missing')
    ordered=[*critical,*[name for name in sorted(documents) if name not in critical]]
    included=[];omitted=[];used=0
    for name in ordered:
        row=documents[name]
        block=f"{row['source']}\n{row['text']}"
        # Conservative character budget is explicit; no claim of exact model tokens.
        cost=(len(block)+2)//3
        if used+cost>token_budget:
            if name in critical:raise ValueError('Context budget cannot fit mandatory constraints')
            omitted.append(name);continue
        included.append({'name':name,**row});used+=cost
    return {'documents':included,'omitted':omitted,'budget_method':'ceil(characters/3)',
            'estimated_tokens':used,'digest':hashlib.sha256(canonical(included).encode()).hexdigest()}


class WorkflowMemory:
    """Explicit causal claims shared by bounded runs; the runtime invents none."""
    def __init__(self,runtime):self.runtime=runtime

    def add(self,*,scope,claim,workflow_id=None,evidence_runs=(),source=None,topics=(),category=None,critical=False):
        import uuid
        from ..workflows.runs import stamp,digest
        actor=self.runtime._actor('memory' if scope=='workflow' else 'configure')
        if scope not in {'owner','strategy','workflow'}:raise ValueError('Memory must have a classified scope')
        if not isinstance(claim,str) or not claim.strip() or len(claim)>2000:raise ValueError('Memory needs a bounded concrete claim')
        if scope=='workflow' and (not workflow_id or not evidence_runs):raise ValueError('Operational learning requires workflow-scoped run evidence')
        if scope!='workflow' and (workflow_id or not isinstance(source,str) or not source.strip()):
            raise ValueError('Owner preference and strategy need explicit owner direction')
        if not isinstance(evidence_runs,(list,tuple)) or len(evidence_runs)!=len(set(evidence_runs)):
            raise ValueError('Memory evidence must name distinct runs')
        metadata=None
        if topics or category or critical:
            self.runtime._actor('configure')
            metadata=self._classification(topics,category or {'owner':'preference','strategy':'direction','workflow':'lesson'}[scope],
                critical,source or 'Explicit evaluated workflow lesson')
        evidence=[]
        for identity in evidence_runs:
            run=self.runtime.get(identity);manifest=self.runtime.manifest(run['release_digest'])
            if not run['evaluation'] or not run['evaluation']['coverage_complete']:
                raise ValueError('Learning evidence must have a complete evaluation')
            if workflow_id and manifest['id']!=workflow_id:raise ValueError('Learning evidence belongs to another workflow')
            evidence.append({'run_id':identity,'release_digest':run['release_digest'],
                             'artifact_digest':run['evaluation']['artifact_digest'],
                             'evaluation_digest':digest(run['evaluation'])})
        row={'id':'memory-'+uuid.uuid4().hex,'scope':scope,'workflow_id':workflow_id,'claim':claim.strip(),
             'evidence':evidence,'source':source,'actor':actor,'created_at':stamp()}
        with self.runtime.connect() as connection:
            connection.execute('INSERT INTO workflow_memories(id,scope,workflow_id,claim,evidence_json,source,actor,created_at,status) VALUES(?,?,?,?,?,?,?,?,?)',
                (row['id'],scope,workflow_id,row['claim'],canonical(evidence),source,actor,row['created_at'],'active'))
            self.runtime._audit(connection,'memory_add',row['id'],row,actor=actor)
            if metadata is not None:
                connection.execute('CREATE TABLE IF NOT EXISTS workflow_memory_classifications (memory_id TEXT PRIMARY KEY,metadata_json TEXT NOT NULL)')
                connection.execute('INSERT INTO workflow_memory_classifications VALUES(?,?)',(row['id'],canonical(metadata)))
                self.runtime._audit(connection,'memory_classify',row['id'],metadata,actor=actor)
        if getattr(self.runtime,'activity_session_id',None):
            from ..observability.sessions import Sessions
            Sessions(self.runtime).record(self.runtime.activity_session_id,kind='decision',request_key='memory-write:'+row['id'],payload={'category':'memory_saved','memory_id':row['id'],'scope':scope,'claim':row['claim'],'workflow_id':workflow_id,'evidence':evidence})
        return row

    @staticmethod
    def _classification(topics,category,critical,reason):
        if category not in {'preference','direction','lesson','project_instruction','historical_authorization','historical_owner_record'} or not reason:
            raise ValueError('Memory classification needs an explicit category and reason')
        if not isinstance(topics,(list,tuple)) or any(not isinstance(t,str) or not t.strip() for t in topics) or not isinstance(critical,bool):
            raise ValueError('Memory topics and critical policy must be explicit')
        return {'category':category,'topics':list(topics),'critical':critical,'reason':reason}

    def classify(self,identity,*,topics=(),category='preference',critical=False,reason):
        actor=self.runtime._actor('configure')
        metadata=self._classification(topics,category,critical,reason)
        with self.runtime.connect() as connection:
            if not connection.execute('SELECT id FROM workflow_memories WHERE id=?',(identity,)).fetchone():raise KeyError('Unknown memory')
            connection.execute('CREATE TABLE IF NOT EXISTS workflow_memory_classifications (memory_id TEXT PRIMARY KEY,metadata_json TEXT NOT NULL)')
            connection.execute('INSERT OR REPLACE INTO workflow_memory_classifications VALUES(?,?)',(identity,canonical(metadata)))
            self.runtime._audit(connection,'memory_classify',identity,metadata,actor=actor)
        return metadata

    def retire(self,identity,*,reason):
        from ..workflows.runs import stamp
        actor=self.runtime._actor('memory')
        with self.runtime.connect() as connection:
            row=connection.execute('SELECT scope FROM workflow_memories WHERE id=?',(identity,)).fetchone()
        if row and row['scope']!='workflow':actor=self.runtime._actor('configure')
        if not isinstance(reason,str) or not reason.strip():raise ValueError('Retiring memory requires its reason')
        with self.runtime.connect() as connection:
            changed=connection.execute("UPDATE workflow_memories SET status='retired',retired_at=?,retirement_reason=? WHERE id=? AND status='active'",
                (stamp(),reason,identity)).rowcount
            if changed!=1:raise ValueError('Memory is missing or already retired')
            self.runtime._audit(connection,'memory_retire',identity,{'reason':reason},actor=actor)

    def summary(self,workflow_id=None,*,prompt=''):
        self.runtime._actor('read')
        with self.runtime.connect() as connection:
            counts={row[0]:row[1] for row in connection.execute("SELECT scope,COUNT(*) FROM workflow_memories WHERE status='active' GROUP BY scope")}
        return {'counts':{scope:counts.get(scope,0) for scope in ('owner','workflow','strategy')},
                'claims':self.active(workflow_id,scopes=('owner','strategy','workflow'),prompt=prompt),
                'selection':'Critical constraints and relevant claims per scope; historical authorizations are never execution permission'}

    def active(self,workflow_id,*,limit_per_scope=5,scopes=('owner','workflow'),prompt=''):
        import json,re
        self.runtime._actor('read')
        if not 1<=limit_per_scope<=20 or set(scopes)-{'owner','workflow','strategy'}:raise ValueError('Memory retrieval must be bounded and classified')
        result=[]
        with self.runtime.connect() as connection:
            tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            metadata={r[0]:json.loads(r[1]) for r in connection.execute('SELECT memory_id,metadata_json FROM workflow_memory_classifications')} if 'workflow_memory_classifications' in tables else {}
            origins={r[0]:json.loads(r[1]) for r in connection.execute('SELECT memory_id,origin_json FROM workflow_memory_origins')} if 'workflow_memory_origins' in tables else {}
            terms=set(re.findall(r'[\w-]{3,}',prompt.casefold()))-{'the','and','with','this','that','from','please','company','workflow'}
            # Each scope receives its own bounded population before combining;
            # a large preference list cannot consume the learning population.
            for scope in scopes:
                rows=connection.execute("SELECT * FROM workflow_memories WHERE status='active' AND scope=? AND (workflow_id=? OR workflow_id IS NULL) ORDER BY rowid DESC",
                    (scope,workflow_id)).fetchall()
                selected=[]
                for row in rows:
                    value=dict(row);value['evidence']=json.loads(value.pop('evidence_json'))
                    policy=metadata.get(value['id'],{'category':'historical_owner_record' if value['id'] in origins else {'owner':'preference','strategy':'direction','workflow':'lesson'}[scope],'topics':[],'critical':False})
                    value['classification']=policy
                    if value['id'] in origins:value['origin']=origins[value['id']]
                    value['authority']='context_only; never approval for external actions'
                    if policy['category'] in {'historical_authorization','historical_owner_record'}:continue
                    topics={t.casefold() for t in policy.get('topics',[])}
                    if topics and prompt and not topics & terms and not policy.get('critical'):continue
                    selected.append((bool(policy.get('critical')),len(terms & set(re.findall(r'[\w-]{3,}',value['claim'].casefold()))),value))
                selected.sort(key=lambda item:(item[0],item[1]),reverse=True)
                critical=[v for c,_,v in selected if c]
                result.extend(critical+[v for c,_,v in selected if not c][:max(0,limit_per_scope-len(critical))])
        return result


def owner_context(runtime,*,prompt='',workflow_id=None,token_budget=6000):
    """Plain progress sentences plus one Director-only machine reference."""
    import json
    runtime._actor('read')
    with runtime.connect() as connection:
        rows=connection.execute("SELECT i.id,i.status,r.manifest_json FROM workflow_invocations i JOIN workflow_releases r ON r.digest=i.release_digest WHERE i.kind='production' AND i.status NOT IN ('completed','failed','cancelled') ORDER BY i.created_at LIMIT 30").fetchall()
        counts={row[0]:row[1] for row in connection.execute("SELECT status,COUNT(*) FROM workflow_invocations WHERE kind='production' GROUP BY status")}
        candidates=[dict(row) for row in connection.execute("SELECT i.id,i.status,i.case_id,r.workflow_id,i.evaluation_json,r.manifest_json FROM workflow_invocations i JOIN workflow_releases r ON r.digest=i.release_digest WHERE i.kind='candidate' ORDER BY i.created_at DESC LIMIT 30")]
        has_improvements=connection.execute("SELECT name FROM sqlite_master WHERE name='workflow_improvements'").fetchone()
        improvements=[dict(row) for row in connection.execute("SELECT id,stage,brief_json FROM workflow_improvements WHERE stage NOT IN ('accepted','rejected') ORDER BY created_at LIMIT 100")] if has_improvements else []
    phrases={'awaiting_provider':'is waiting for its assigned executor',
             'dispatching':'is starting','awaiting_reconciliation':'needs its provider result checked',
             'awaiting_evaluation':'has an output ready for quality checks',
             'awaiting_review':'has passed quality checks and needs independent review'}
    lines=['Company work',f"{counts.get('completed',0)} accepted outputs; {counts.get('failed',0)} runs need revision."]
    memory=WorkflowMemory(runtime).summary(workflow_id,prompt=prompt)
    lines.append(str(memory['counts']['owner'])+' owner records, '+str(memory['counts']['workflow'])+' workflow lessons and '+str(memory['counts']['strategy'])+' strategic directions are preserved; only applicable reviewed context is supplied below.')
    references=[]
    for row in rows:
        manifest=json.loads(row['manifest_json']);name=manifest.get('name') or manifest['purpose'][:160]
        lines.append(name+' '+phrases.get(row['status'],'needs attention')+'.')
        references.append({'run_id':row['id'],'workflow_id':manifest['id'],'status':row['status']})
    if not rows:lines.append('There is no unfinished production work.')
    if not counts:lines.append('No production runs are registered; this does not establish that direct chat work was completed or evaluated.')
    for index,row in enumerate(improvements):
        brief=json.loads(row.pop('brief_json'));row['name']=brief['name']
        if index>=3:continue
        lines.append(row['name']+(' has implementation evidence awaiting independent review.' if row['stage']=='awaiting_change_review' else ' is an unfinished Improvement.'))
    if len(improvements)>3:lines.append(str(len(improvements)-3)+' additional Improvements are preserved; open /report for their history.')
    candidate_refs=[]
    for row in candidates:
        evaluation=json.loads(row.pop('evaluation_json') or 'null');manifest=json.loads(row.pop('manifest_json'))
        case=next((c for c in manifest['evaluation']['cases'] if c['id']==row['case_id']),{})
        expected_rejection=bool(evaluation and evaluation['state']=='fail' and case.get('expected')=='fail')
        row['expected_rejection']=expected_rejection;candidate_refs.append(row)
    if candidates:
        lines.append(str(sum(r['status']=='awaiting_review' for r in candidates))+' candidate outputs await independent review; '+str(sum(r['expected_rejection'] for r in candidates))+' negative cases were correctly rejected.')
    from ..operations import telemetry_status
    telemetry=telemetry_status(runtime)
    outstanding=sum(n for pop in (telemetry['events'],telemetry.get('activity_events',{})) for state,n in pop.items() if state!='verified')
    lines.append(('Langfuse export is enabled' if telemetry['state']=='enabled' else 'Langfuse export is disabled')+'; '+str(outstanding)+' events remain unverified.')
    if runtime.home:
        strategy=CompanyHome(runtime.home).content/'strategy'
        documents=sorted(p.name for p in strategy.glob('*.md'))
        if documents:lines.append('Canonical strategy documents are available separately from strategy memory: '+', '.join(documents)+'.')
        legacy_departments=CompanyHome(runtime.home).content/'departments'
        if any(legacy_departments.glob('*/department.py')):lines.append('Preserved Department declarations are historical capabilities; their ready flags do not qualify them as released workflows.')
    memory_docs={row['id']:{'source':row['scope']+' memory ('+row['classification']['category']+'; applies to '+(', '.join(row['classification'].get('topics',[])) or 'company-wide')+'; '+('historical lineage; ' if row.get('origin') else '')+'context only, never external permission)', 'sha256':hashlib.sha256(row['claim'].encode()).hexdigest(),'text':row['claim']} for row in memory['claims']}
    chosen=projection(memory_docs,token_budget=token_budget,critical=[r['id'] for r in memory['claims'] if r['classification'].get('critical')])
    if chosen['documents']:lines.append('Applicable memory\n'+'\n'.join(row['source']+': '+row['text'] for row in chosen['documents']))
    if chosen['omitted']:lines.append(str(len(chosen['omitted']))+' additional memory records were omitted by the context budget.')
    legacy=None
    if runtime.home and (runtime.home/'.spielos/legacy-review.json').is_file():
        legacy=json.loads((runtime.home/'.spielos/legacy-review.json').read_text())
        earlier=sum(row.get('status') in {'active','paused'} for row in legacy['inventory']['tables'].get('core_goals',[]))
        lines.append(str(earlier)+' earlier objectives are preserved for migration review. None was resumed.')
    lines.append('Machine reference: '+canonical({'pending':references,'counts':counts,'memory_counts':memory['counts'],'improvements':improvements[:5],'improvement_count':len(improvements),'candidates':candidate_refs,'telemetry':telemetry,'omitted_memory':chosen['omitted'],'legacy_review':'.spielos/legacy-review.json' if legacy else None}))
    return {'text':'\n'.join(lines),'pending':references,'counts':counts,'memory':memory,'improvements':improvements,'candidates':candidate_refs,'telemetry':telemetry,'memory_projection':chosen}
