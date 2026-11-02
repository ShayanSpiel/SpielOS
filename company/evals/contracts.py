"""Versioned criterion checks for examples and previously unseen production inputs.

Judges supply attributable evidence. A technical pass never manufactures a
business outcome, and the aggregation cannot average away a hard failure.
"""
from __future__ import annotations
import math,re

STATES={'pass','fail','missing','error','not_applicable'}


def field(value,path):
    if path in ('','/'):return value
    if not isinstance(path,str) or not path.startswith('/'):
        raise ValueError('Check paths must be JSON pointers')
    for part in path[1:].split('/'):
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def check_rule(rule,output,inputs):
    kind=rule.get('kind');value=field(output,rule.get('path','/'))
    if kind in {'event_count','event_order'}:
        if not isinstance(value,list):raise ValueError('Behavior checks require actual recorded events')
        def matches(event,expected):
            try:return isinstance(event,dict) and all(field(event,path)==wanted for path,wanted in expected.items())
            except (KeyError,IndexError,TypeError,ValueError):return False
        if kind=='event_count':
            count=sum(matches(event,rule['match']) for event in value)
            return rule.get('min',0)<=count<=rule.get('max',float('inf'))
        remaining=iter(value)
        return all(any(matches(event,expected) for event in remaining) for expected in rule['sequence'])
    if kind=='equals_input':return value==field(inputs,rule['input_path'])
    if kind=='sum_input':return value==sum(field(inputs,rule['input_path']))
    if kind=='length_input':return value==len(field(inputs,rule['input_path']))
    if kind=='equals':return value==rule['value']
    if kind=='nonempty':return isinstance(value,(str,list,dict)) and bool(value.strip() if isinstance(value,str) else value)
    if kind=='length':return rule.get('min',0)<=len(value)<=rule.get('max',float('inf'))
    if kind=='range':return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and rule.get('min',float('-inf'))<=value<=rule.get('max',float('inf'))
    if kind=='pattern':return isinstance(value,str) and re.fullmatch(rule['pattern'],value) is not None
    if kind=='contains':return rule['value'] in value
    raise ValueError('Unsupported deterministic criterion check')


def calibration(records,*,maximum_disagreement=0.2):
    if not isinstance(records,list) or not records:raise ValueError('Human-rated calibration examples are required')
    if not isinstance(maximum_disagreement,(int,float)) or isinstance(maximum_disagreement,bool) or not 0<=maximum_disagreement<=1:raise ValueError('Calibration disagreement policy must be a fraction from zero to one')
    ids=[row.get('case_id') for row in records]
    if any(not isinstance(item,str) or not item for item in ids) or len(ids)!=len(set(ids)):
        raise ValueError('Calibration needs distinct identified examples')
    for row in records:
        if not row.get('human_reviewer') or not row.get('artifact_digest') or row.get('human_state') not in {'pass','fail'} or row.get('judge_state') not in {'pass','fail'}:
            raise ValueError('Calibration requires attributed human and judge ratings of the same artifact')
    rate=sum(row['human_state']!=row['judge_state'] for row in records)/len(records)
    return {'samples':len(records),'disagreement_rate':rate,'maximum_disagreement':maximum_disagreement,
            'state':'pass' if rate<=maximum_disagreement else 'fail'}


def validate_criterion(criterion):
    evaluator=criterion.get('evaluator')
    if evaluator not in {'reference','check','human','model'}:raise ValueError('Missing or unsupported evaluator')
    if not criterion.get('source') or not criterion.get('anchors') or criterion.get('severity') not in {'block','warn'}:
        raise ValueError('Criteria need sources, rating anchors and severity')
    if evaluator=='check':
        rule=criterion.get('check')
        if not isinstance(rule,dict) or rule.get('kind') not in {'equals_input','sum_input','length_input','equals','nonempty','length','range','pattern','contains','event_count','event_order'}:
            raise ValueError('Deterministic criteria need an executable check')
        if rule['kind']=='event_count' and (not isinstance(rule.get('match'),dict) or not rule['match'] or not {'min','max'}&set(rule)):
            raise ValueError('Event count checks need content matching and a count policy')
        if rule['kind']=='event_order' and (not isinstance(rule.get('sequence'),list) or len(rule['sequence'])<2 or any(not isinstance(x,dict) or not x for x in rule['sequence'])):
            raise ValueError('Event ordering requires at least two explicit event matches')
        # Syntax errors must block release, rather than become a runtime surprise.
        if rule['kind']=='pattern':re.compile(rule['pattern'])
    if evaluator in {'human','model'} and 'threshold' in criterion:
        if not isinstance(criterion['threshold'],(int,float)) or isinstance(criterion['threshold'],bool) or not 0<=criterion['threshold']<=1 or not criterion.get('threshold_reason'):
            raise ValueError('Rating threshold needs an example-based justification')
    if evaluator=='model':
        judge=criterion.get('judge',{})
        if not all(isinstance(judge.get(key),str) and judge[key] for key in ('model','prompt_digest','version')):
            raise ValueError('Model judging requires a pinned model, prompt and evaluator version')
        result=calibration(judge.get('calibration'),maximum_disagreement=judge.get('maximum_disagreement',0.2))
        if result['state']!='pass':raise ValueError('Model judge disagrees with its human calibration beyond policy')


def evaluate(manifest,output,*,inputs,case_id=None,verdicts=None,evaluator=None,producer=None):
    from ..workflows.runs import digest,validate
    validate(manifest['output_schema'],output,'output')
    cases=manifest['evaluation']['cases']
    case=next((item for item in cases if item['id']==case_id),None) if case_id else None
    if case_id and case is None:raise ValueError('Unknown evaluation case')
    supplied=verdicts or {}
    if not isinstance(supplied,dict):raise ValueError('Criterion verdicts must be keyed objects')
    criteria=manifest['evaluation']['criteria']
    if set(supplied)-{row['id'] for row in criteria}:raise ValueError('Unexpected criterion verdict')
    results={}
    artifact=digest(output)
    for criterion in criteria:
        cid=criterion['id'];kind=criterion['evaluator'];score=None;self_judged=False
        identity='check-v1' if kind=='check' else 'reference-v1' if kind=='reference' else evaluator
        applicable=case is None or cid in case.get('applicable_criteria',[row['id'] for row in criteria])
        if not applicable:
            state,reason='not_applicable','Excluded by the pinned case applicability policy'
        elif kind=='reference':
            state='pass' if case and output==case['reference'] else 'fail' if case else 'missing'
            reason='Compared complete output with pinned reference' if case else 'A new input needs an applicable check or attributed reference review'
        elif kind=='check':
            try:
                state='pass' if check_rule(criterion['check'],output,inputs) else 'fail'
                reason='Executed pinned '+criterion['check']['kind']+' check'
            except (KeyError,IndexError,TypeError,ValueError) as exc:
                state,reason='error','Criterion could not inspect the required output field: '+type(exc).__name__
        else:
            verdict=supplied.get(cid,{})
            if not isinstance(verdict,dict):raise ValueError('Each criterion verdict must be an object')
            state,reason=verdict.get('state','missing'),verdict.get('reason','')
            if state not in STATES:raise ValueError('Invalid evaluation state')
            if not identity or not reason:state='missing'
            if manifest.get('evaluation',{}).get('standard')=='spielos-evaluation/2' and state in {'pass','fail'}:
                if not verdict.get('evidence') or verdict.get('artifact_digest')!=artifact:state='missing'
            if verdict.get('artifact_digest',artifact)!=artifact:raise ValueError('Review refers to another artifact')
            score=verdict.get('score')
            if score is not None:
                if not isinstance(score,(int,float)) or isinstance(score,bool) or not math.isfinite(score) or not 0<=score<=1:raise ValueError('Criterion scores must be finite values from zero to one')
                if state in {'pass','fail'} and 'threshold' in criterion:
                    state='pass' if score>=criterion['threshold'] else 'fail'
            elif 'threshold' in criterion and state in {'pass','fail'}:state='missing'
            if state=='not_applicable' and not criterion.get('allow_not_applicable',False):state='missing'
            self_judged=bool(identity and producer and identity==producer)
            if kind=='model':
                judge=criterion['judge']
                if any(verdict.get(key)!=judge[key] for key in ('model','prompt_digest','version')) or not verdict.get('evidence') or verdict.get('artifact_digest')!=artifact:
                    state='missing'
                identity=judge['version']
            if criterion.get('media_review') and state in {'pass','fail'}:
                inspection=verdict.get('inspection',{})
                if inspection.get('artifact_digest')!=artifact or not inspection.get('render_digest') or not inspection.get('observations'):
                    state='missing'
        results[cid]={'state':state,'reason':reason,'score':score,'evaluator':identity,
                      'self_judged':self_judged,'artifact_digest':artifact,
                      'source':criterion['source'],'evaluator_type':kind,'evaluator_version':identity if kind in {'reference','check','model'} else 'human-review-v1'}
    blocking=any(results[c['id']]['state']=='fail' for c in criteria if c['severity']=='block')
    states={row['state'] for row in results.values()}
    complete=all(row['state'] in {'pass','fail','not_applicable'} for row in results.values())
    # Excluding every blocking criterion cannot create a passing population.
    population=any(results[c['id']]['state'] in {'pass','fail'} for c in criteria if c['severity']=='block')
    state='fail' if blocking else 'error' if 'error' in states else 'missing' if not complete or not population else 'pass'
    return {'state':state,'case_id':case_id,'rubric_version':manifest['evaluation']['version'],
            'release_digest':digest(manifest),'artifact_digest':artifact,'criteria':results,
            'coverage_complete':complete and population,'quality_domain':'output_quality',
            'business_outcome':'unmeasured','self_judged':any(row['self_judged'] for row in results.values())}


def measurement_contract(value):
    """Validate an observed outcome without inferring causality or a baseline."""
    from datetime import datetime,timezone
    required={'metric_id','name','definition','unit','direction','population','window_start','window_end',
              'value','sample_size','minimum_sample_size','minimum_reason','source','baseline','release_digest'}
    if not isinstance(value,dict) or required-set(value) or set(value)-required-{'unknown_reason'}:
        raise ValueError('Outcome measurement needs its definition, unit, population, observation window and provenance')
    for key in ('metric_id','name','definition','unit','population','minimum_reason','source','release_digest'):
        if not isinstance(value[key],str) or not value[key].strip():raise ValueError('Outcome measurement needs '+key)
    if value['direction'] not in {'increase','decrease','maintain'}:raise ValueError('Metric direction must be explicit')
    try:start=datetime.fromisoformat(value['window_start']);end=datetime.fromisoformat(value['window_end'])
    except (ValueError,TypeError):raise ValueError('Observation windows need ISO timestamps')
    if start.tzinfo is None or end.tzinfo is None or end<=start or end>datetime.now(timezone.utc):
        raise ValueError('Observed outcome windows must be ordered, timezone-aware and already elapsed')
    for key in ('sample_size','minimum_sample_size'):
        if not isinstance(value[key],int) or isinstance(value[key],bool) or value[key]<(1 if key=='minimum_sample_size' else 0):
            raise ValueError('Sample populations must be explicit nonnegative integers')
    def numeric(number):return isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number)
    baseline=value['baseline']
    if not isinstance(baseline,dict) or baseline.get('state') not in {'unknown','observed'}:raise ValueError('Baseline is observed or explicitly unknown')
    if baseline['state']=='unknown':
        if set(baseline)!={'state','reason'} or not baseline['reason']:raise ValueError('Unknown baseline needs its reason')
    elif set(baseline)!={'state','value','source'} or not numeric(baseline['value']) or not baseline['source']:
        raise ValueError('Observed baseline needs a finite reading and source')
    if value['value'] is None:
        if not value.get('unknown_reason'):raise ValueError('Unknown reading requires its reason')
        state='unknown'
    elif not numeric(value['value']):raise ValueError('Outcome readings must be finite numbers or explicitly unknown')
    else:state='observed' if value['sample_size']>=value['minimum_sample_size'] else 'insufficient_evidence'
    return {**value,'state':state,'attribution':'association_only; causal impact is not established'}


def record_judge_calibration(runtime,*,judge,ratings,maximum_disagreement=0.2,reason):
    """An authenticated independent reviewer owns the actual artifact ratings."""
    from ..workflows.runs import canonical,digest,stamp
    actor=runtime._actor('review')
    if not isinstance(judge,dict) or set(judge)!={'model','prompt_digest','version'} or any(not isinstance(value,str) or not value for value in judge.values()) or not reason:
        raise ValueError('Calibration needs its pinned judge and explicit review rationale')
    if not isinstance(ratings,list) or not ratings:raise ValueError('Calibration needs actual independently reviewed artifacts')
    records=[];seen=set()
    for rating in ratings:
        if not isinstance(rating,dict) or not all(rating.get(key) for key in ('run_id','human_state','judge_state','judge_source')):
            raise ValueError('Each calibration rating needs its run and attributable human/judge evidence')
        run=runtime.get(rating['run_id'])
        if run['output'] is None:raise ValueError('Calibration cannot rate an absent output')
        if runtime.authority and run['actor']==actor:raise PermissionError('The artifact producer cannot sign its independent calibration')
        artifact=digest(run['output'])
        if artifact in seen:raise ValueError('Repeated artifacts cannot inflate calibration evidence')
        seen.add(artifact)
        records.append({'case_id':run['id'],'human_state':rating['human_state'],'judge_state':rating['judge_state'],
                        'human_reviewer':actor,'artifact_digest':artifact,'judge_source':rating['judge_source']})
    if {row['human_state'] for row in records}!={'pass','fail'}:raise ValueError('Calibration requires both accepted and rejected human examples')
    result=calibration(records,maximum_disagreement=maximum_disagreement)
    record={'judge':judge,'ratings':records,'policy':result,'reviewer':actor,'reason':reason}
    identity=digest(record)
    with runtime.connect() as connection:
        connection.execute('INSERT OR IGNORE INTO workflow_judge_calibrations VALUES(?,?,?,?)',(identity,canonical(record),actor,stamp()))
        runtime._audit(connection,'judge_calibration',identity,record,actor=actor)
    return {'calibration_id':identity,**record}
