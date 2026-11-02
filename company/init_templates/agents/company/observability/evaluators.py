"""Readable native Langfuse definitions for lifecycle and host-model reviews.

Langfuse runs deterministic validators. Semantic judgments come from the
selected Codex/other host and remain attributed to that actual runtime.
"""
import json
from urllib.parse import urlencode,quote

SOURCE = r'''function evaluate(ctx) {
  const parse = x => { if (typeof x !== "string") return x || {}; try { return JSON.parse(x); } catch { return {}; } };
  const out = parse(ctx.observation.output);
  const meta = parse(ctx.observation.metadata);
  const report = parse(meta.evaluation);
  const verdicts = out.verdicts || out.governance || report.criteria || {};
  const scores = Object.entries(verdicts).map(([name, v]) => ({
    name: name,
    dataType: "CATEGORICAL",
    value: v.state || "missing",
    comment: v.reason || "No attributable judgment was supplied.",
    metadata: { evaluator: "SpielOS native evidence validator", model: out.model || meta.runtime_model || "not exposed", evidence: v.evidence || null }
  }));
  for (const [name, v] of Object.entries(verdicts)) {
    if (typeof v.score === "number" && Number.isFinite(v.score) && v.score >= 0 && v.score <= 1)
      scores.push({name: name + " · Rating", dataType: "NUMERIC", value: v.score, comment: v.reason || "Host-model rubric rating", metadata: {model: out.model || meta.runtime_model || "not exposed", independence: "Same-host diagnostic; independent acceptance is separate"}});
  }
  if (!scores.length) scores.push({name: "Evaluation evidence available", dataType: "CATEGORICAL", value: "missing", comment: "The selected observation has no complete criterion verdicts; this is not a quality pass."});
  return {scores};
}'''

SCHEMA='''CREATE TABLE IF NOT EXISTS native_evaluation_definitions(
 key TEXT PRIMARY KEY,definition_json TEXT NOT NULL,evaluator_id TEXT,rule_id TEXT,status TEXT NOT NULL,last_error TEXT);
CREATE TABLE IF NOT EXISTS workflow_evaluation_definitions(
 release_digest TEXT PRIMARY KEY,definition_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_evaluation_definitions(
 agent_id TEXT PRIMARY KEY,definition_json TEXT NOT NULL);
'''


def prepare(runtime):
    with runtime.connect() as c:c.executescript(SCHEMA)


def register_manifest(runtime,manifest,release):
    from ..workflows.runs import canonical
    from .sessions import sanitize
    prepare(runtime)
    definition={'workflow_id':manifest['id'],'purpose':manifest['purpose'],'version':manifest['version'],
                'execution':manifest['execution'],'agent':manifest.get('resolved_agent'),
                'rubric':manifest['evaluation'],'judge_runtime':'selected execution host; exact model is recorded on each judgment'}
    definition=sanitize(definition)
    with runtime.connect() as c:c.execute('INSERT OR IGNORE INTO workflow_evaluation_definitions VALUES(?,?)',(release,canonical(definition)))
    if manifest.get('resolved_agent'):register_agent(runtime,manifest['resolved_agent'])
    for item in desired(runtime):
        with runtime.connect() as c:c.execute("INSERT OR IGNORE INTO native_evaluation_definitions VALUES(?,?,NULL,NULL,'pending',NULL)",(item['key'],canonical(item)))


def register_agent(runtime,agent):
    from ..workflows.runs import canonical
    from .sessions import sanitize
    prepare(runtime)
    agent=sanitize({key:agent[key] for key in ('id','description','skill_ids','capability_ids','permissions','produces','connection_ids') if key in agent})
    with runtime.connect() as c:c.execute('INSERT OR IGNORE INTO agent_evaluation_definitions VALUES(?,?)',(agent['id'],canonical(agent)))
    for item in desired(runtime):
        with runtime.connect() as c:c.execute("INSERT OR IGNORE INTO native_evaluation_definitions VALUES(?,?,NULL,NULL,'pending',NULL)",(item['key'],canonical(item)))


def desired(runtime):
    prepare(runtime)
    company=runtime.authority.company_id if runtime.authority else 'synthetic'
    result=[]
    for category,name,description in [
        ('director_turn','Director · Turn evidence and boundaries','Checks captured request, context, answer and tool evidence. Semantic judgment is separately assigned to the current host model.'),
        ('host_judgment','Codex / host model · Rubric judgments','Validates and records actual host-model verdicts with reasons, evidence and model identity. No separate Langfuse model connection is used.'),
        ('workflow_output','Workflows · Required output evaluations','Records the mandatory pinned-rubric evaluation of every delivered workflow output. Missing judgments remain missing.'),
        ('experiment','Experiments · Candidate outcome','Records actual candidate criterion outcomes; experiments remain distinct from production and do not promote releases.'),
    ]:
        result.append((category,name,description,[{'type':'stringObject','column':'metadata','key':'category','operator':'=','value':category}]))
    with runtime.connect() as c:rows=c.execute('SELECT release_digest,definition_json FROM workflow_evaluation_definitions').fetchall()
    for row in rows:
        d=json.loads(row['definition_json']);name='Workflow · '+d['workflow_id'].replace('-',' ').title()+' · '+d['purpose'][:100]+' · version '+d['version']
        filters=[{'type':'stringObject','column':'metadata','key':'workflow_id','operator':'=','value':d['workflow_id']},
                 {'type':'string','column':'version','operator':'=','value':d['version']},
                 {'type':'stringObject','column':'metadata','key':'category','operator':'=','value':'workflow_output'}]
        summary={**d,'rubric':{key:value for key,value in d['rubric'].items() if key not in {'cases','implementation_digest'}}}
        result.append(('workflow:'+row['release_digest'],name,'Pinned input/output rubric and host evaluator binding: '+json.dumps(summary,ensure_ascii=False),filters))
    with runtime.connect() as c:agents=c.execute('SELECT definition_json FROM agent_evaluation_definitions').fetchall()
    for row in agents:
        agent=json.loads(row[0]);result.append(('agent:'+agent['id'],'Agent · '+agent['id'].replace('-',' ').title()+' · '+agent.get('description','')[:100],
            'Agent responsibility and execution declaration: '+json.dumps(agent,ensure_ascii=False)+'. Quality is evaluated through the pinned rubric of each bound workflow and the selected host model; creating this definition does not qualify the agent.',
            [{'type':'stringObject','column':'metadata','key':'agent_id','operator':'=','value':agent['id']},
             {'type':'stringObject','column':'metadata','key':'category','operator':'=','value':'workflow_output'}]))
    return [{'key':key,'evaluator':{'name':name,'type':'code','description':description,'sourceCode':SOURCE,'sourceCodeLanguage':'TYPESCRIPT'},
             'rule':{'name':name+' · every matching result','enabled':True,'sampling':1.0,
                'filter':[{'type':'stringOptions','column':'environment','operator':'any of','value':['spielos-local']},
                          {'type':'stringObject','column':'metadata','key':'company_id','operator':'=','value':company}]+filters}}
            for key,name,description,filters in result]


def sync(runtime,client,*,limit=None,pending_only=False):
    import os,fcntl
    fd=os.open(runtime.path.parent/'native-evaluators.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return []
        return _sync(runtime,client,limit=limit,pending_only=pending_only)
    finally:os.close(fd)


def _sync(runtime,client,*,limit=None,pending_only=False):
    """Journal resource creation; lost responses are resolved by exact readback."""
    from ..workflows.runs import canonical
    from .sessions import policy
    config=policy(runtime)
    if client.project_id!=config.get('project_id') or client.base_url!=config.get('base_url'):raise PermissionError('Native evaluation destination differs from the approved company')
    client.verify_project();prepare(runtime);results=[]
    plans=desired(runtime)
    if pending_only:
        with runtime.connect() as c:
            plans=[p for p in plans if not (row:=c.execute('SELECT status FROM native_evaluation_definitions WHERE key=?',(p['key'],)).fetchone()) or row[0]!='verified']
    if limit is not None:plans=plans[:limit]
    if not plans:return []
    def inventory(kind):
        rows=[];cursor=None
        for _ in range(20):
            query={'limit':100}
            if cursor:query['cursor']=cursor
            value=client.request('GET','/api/public/v2/'+kind+'?'+urlencode(query));rows.extend(value.get('data',[]));cursor=(value.get('meta') or {}).get('cursor')
            if not cursor:return rows
        raise ValueError('Native definition pagination exceeded its budget')
    evaluators=inventory('evaluators');rules=inventory('evaluation-rules')
    for item in plans:
        key=item['key'];e=item['evaluator']
        with runtime.connect() as c:
            c.execute("INSERT OR IGNORE INTO native_evaluation_definitions VALUES(?,?,NULL,NULL,'pending',NULL)",(key,canonical(item)))
            state=dict(c.execute('SELECT * FROM native_evaluation_definitions WHERE key=?',(key,)).fetchone())
        found=[v for v in evaluators if v['name']==e['name'] and v.get('sourceCode')==SOURCE]
        if len(found)>1:raise ValueError('Native evaluator identity is ambiguous')
        if not found:
            if state['status']=='creating_evaluator':raise ValueError('An evaluator creation is unresolved; inspect exact native resource readback')
            with runtime.connect() as c:c.execute("UPDATE native_evaluation_definitions SET status='creating_evaluator' WHERE key=?",(key,))
            created=client.request('POST','/api/public/v2/evaluators',e);evaluators.append(created);found=[created]
        evaluator=client.request('GET','/api/public/v2/evaluators/'+quote(found[0]['id'],safe=''))
        if evaluator.get('sourceCode')!=SOURCE:raise ValueError('Native evaluator code differs from the approved definition')
        rule={**item['rule'],'evaluatorAssignments':[{'evaluatorId':evaluator['id'],'variableMapping':None}]}
        found_rules=[v for v in rules if v['name']==rule['name'] and any(a['evaluatorId']==evaluator['id'] for a in v.get('evaluatorAssignments',[]))]
        if len(found_rules)>1:raise ValueError('Native rule identity is ambiguous')
        if not found_rules:
            if state['status']=='creating_rule':raise ValueError('A rule creation is unresolved; inspect exact native resource readback')
            with runtime.connect() as c:c.execute("UPDATE native_evaluation_definitions SET status='creating_rule',evaluator_id=? WHERE key=?",(evaluator['id'],key))
            created=client.request('POST','/api/public/v2/evaluation-rules',rule);rules.append(created);found_rules=[created]
        actual=client.request('GET','/api/public/v2/evaluation-rules/'+quote(found_rules[0]['id'],safe=''))
        if actual.get('enabled') is not True or actual.get('sampling')!=1 or actual.get('filter')!=rule['filter']:raise ValueError('Native rule differs from the exact company/category/sampling contract')
        with runtime.connect() as c:c.execute("UPDATE native_evaluation_definitions SET evaluator_id=?,rule_id=?,status='verified',last_error=NULL WHERE key=?",(evaluator['id'],actual['id'],key))
        results.append({'name':e['name'],'evaluator_id':evaluator['id'],'rule_id':actual['id'],'status':evaluator.get('status'),'verified':True})
    return results
