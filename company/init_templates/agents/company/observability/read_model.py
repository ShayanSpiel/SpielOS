from __future__ import annotations

import json





def workflow_scorecard(runtime):
    """Bounded-run reporting with explicit populations and currency provenance."""
    from datetime import datetime
    import json
    runtime._actor('read')
    with runtime.connect() as connection:
        inventory=connection.execute('''SELECT COUNT(DISTINCT r.workflow_id),
            COUNT(DISTINCT CASE WHEN a.digest IS NOT NULL THEN r.workflow_id END),COUNT(*)
            FROM workflow_releases r LEFT JOIN workflow_release_acceptance a ON a.digest=r.digest''').fetchone()
        population=connection.execute('''SELECT COUNT(*),SUM(status='completed'),SUM(status='failed'),
            SUM(status='awaiting_review'),SUM(evaluation_json IS NOT NULL),
            SUM(CASE WHEN evaluation_json IS NOT NULL THEN json_extract(evaluation_json,'$.coverage_complete')=1 ELSE 0 END),
            AVG((julianday(updated_at)-julianday(created_at))*86400)
            FROM workflow_invocations WHERE kind='production' ''').fetchone()
        usage_rows=connection.execute('''SELECT u.stage,json_extract(u.usage_json,'$.status') AS usage_status,
            json_extract(u.usage_json,'$.currency') AS currency,COUNT(*) AS records,
            SUM(json_extract(u.usage_json,'$.cost')) AS cost
            FROM workflow_usage_events u JOIN workflow_invocations i ON i.id=u.run_id
            WHERE i.kind IN ('production','component') GROUP BY u.stage,usage_status,currency ''').fetchall()
        coverage=connection.execute('''SELECT COUNT(DISTINCT COALESCE(i.root_run_id,i.id)) FROM workflow_invocations i
            JOIN workflow_usage_events u ON u.run_id=i.id
            WHERE i.kind IN ('production','component') AND json_extract(u.usage_json,'$.status')!='unknown' ''').fetchone()[0]
        states=connection.execute('''SELECT json_extract(c.value,'$.state'),COUNT(*)
            FROM workflow_invocations i,json_each(i.evaluation_json,'$.criteria') c
            WHERE i.kind='production' GROUP BY json_extract(c.value,'$.state')''').fetchall()
        outbox=connection.execute("SELECT status,COUNT(*) FROM workflow_export_outbox GROUP BY status").fetchall()
        outcomes=[json.loads(row[0]) for row in connection.execute('SELECT measurement_json FROM workflow_outcome_observations ORDER BY rowid DESC LIMIT 50')]
        reviews=connection.execute("SELECT SUM(review_json IS NOT NULL),SUM(json_extract(review_json,'$.decision')='reject') FROM workflow_invocations WHERE kind='production'").fetchone()
        calibration=connection.execute("SELECT COUNT(DISTINCT c.id),COUNT(*),SUM(json_extract(r.value,'$.human_state')<>json_extract(r.value,'$.judge_state')) FROM workflow_judge_calibrations c,json_each(c.record_json,'$.ratings') r").fetchone()
        versions=connection.execute("SELECT i.release_digest,json_extract(r.manifest_json,'$.version') AS version,COUNT(*) AS runs FROM workflow_invocations i JOIN workflow_releases r ON r.digest=i.release_digest WHERE i.kind='production' GROUP BY i.release_digest ORDER BY MIN(i.created_at) DESC LIMIT 51").fetchall()
        unfinished=connection.execute("SELECT status,COUNT(*) FROM workflow_invocations WHERE kind='production' AND status NOT IN ('completed','failed','cancelled') GROUP BY status").fetchall()
    definition_ids=set()
    if runtime.home:
        from ..home import CompanyHome
        for path in (CompanyHome(runtime.home).content/'workflows').glob('*/workflow.json'):
            if path.is_symlink() or not path.resolve().is_relative_to(CompanyHome(runtime.home).content):continue
            try:
                definition=json.loads(path.read_text())
                if isinstance(definition,dict) and isinstance(definition.get('id'),str):definition_ids.add(definition['id'])
            except (ValueError,OSError):continue
    with runtime.connect() as connection:
        definition_ids.update(row[0] for row in connection.execute('SELECT DISTINCT workflow_id FROM workflow_releases'))
    workflow_count=len(definition_ids)
    count=int(population[0]);accepted=int(population[1] or 0)
    costs={};usage_status={'actual':0,'estimated':0,'unknown':0};stage_counts={}
    for row in usage_rows:
        status=row['usage_status'];usage_status[status]+=row['records']
        stage_counts[row['stage']]=stage_counts.get(row['stage'],0)+row['records']
        if row['cost'] is not None:
            currency=row['currency'];bucket=costs.setdefault(currency,{'actual':0,'estimated':0})
            bucket[status]+=row['cost']
    for bucket in costs.values():
        bucket['known_cost_per_accepted_output']=(bucket['actual']+bucket['estimated'])/accepted if accepted else None
        bucket['complete_total']=False # Unknown provider/host/evaluation cost is not zero.
    from ..operations import telemetry_status
    with runtime.connect() as connection:
        has_improvements=connection.execute("SELECT name FROM sqlite_master WHERE name='workflow_improvements'").fetchone()
        improvements=dict(connection.execute('SELECT stage,COUNT(*) FROM workflow_improvements GROUP BY stage')) if has_improvements else {}
        candidates=dict(connection.execute("SELECT status,COUNT(*) FROM workflow_invocations WHERE kind='candidate' GROUP BY status"))
    return {'development':{'improvements':improvements,'candidate_runs':candidates,
                           'direct_chat_work':'not inferred; work outside registered runs is not qualified'},
            'telemetry':telemetry_status(runtime),
            'inventory':{'workflows':workflow_count,'released_workflows':inventory[1],
                         'draft_only_workflows':workflow_count-inventory[1],'candidate_versions':inventory[2]},
            'runs':{'population':'production invocations only; candidate executions excluded','total':count,
                    'accepted_outputs':accepted,'failed':int(population[2] or 0),'awaiting_review':int(population[3] or 0),
                    'failure_rate':int(population[2] or 0)/count if count else None,
                    'reviewed_outputs':int(reviews[0] or 0),'review_rate':int(reviews[0] or 0)/count if count else None,
                    'rejected_reviews':int(reviews[1] or 0),
                    'evaluation_coverage':int(population[5] or 0)/count if count else None,
                    'mean_observed_lifecycle_seconds':population[6]},
            'criterion_results':dict(states),
            'human_judge_disagreement':{'calibrations':calibration[0],'ratings':calibration[1],
                'disagreements':int(calibration[2] or 0),'rate':int(calibration[2] or 0)/calibration[1] if calibration[1] else None,
                'population':'Independent recorded human/judge ratings of the same artifact; no ratings means unknown'},
            'versions_used':{'production':[dict(row) for row in versions[:50]],'truncated':len(versions)>50},
            'unresolved_operations':dict(unfinished),
            'usage':{'record_counts':usage_status,'stages':stage_counts,
                'runs_with_some_known_usage':coverage,'run_denominator':count,
                'coverage_fraction':coverage/count if count else None},
            'costs_by_currency':costs,'telemetry_events':dict(outbox),
            'business_outcomes':{'state':'recorded' if outcomes else 'unmeasured','observations':outcomes,'observation_window':None if not outcomes else 'Per explicit observation; windows are never combined implicitly'}}


def record_outcome(runtime,measurement):
    """An explicit observation, separate from output quality and release policy."""
    import uuid
    from ..evals.contracts import measurement_contract
    from ..workflows.runs import canonical,stamp
    actor=runtime._actor('configure')
    measurement=measurement_contract(measurement)
    runtime.manifest(measurement['release_digest'])
    identity='outcome-'+uuid.uuid4().hex
    with runtime.connect() as connection:
        connection.execute('INSERT INTO workflow_outcome_observations VALUES(?,?,?,?,?)',
            (identity,measurement['release_digest'],canonical(measurement),actor,stamp()))
        runtime._audit(connection,'outcome_observation',identity,measurement,actor=actor)
    return {'id':identity,**measurement,'actor':actor}
