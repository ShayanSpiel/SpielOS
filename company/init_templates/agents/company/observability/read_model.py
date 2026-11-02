from __future__ import annotations

import json

from ..state import Database


class Observer:
    def __init__(self, database: Database):
        self.database = database

    def health(self) -> dict:
        with self.database.connect() as connection:
            def count(table: str, where: str = "") -> int:
                return connection.execute(
                    f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
            return {
                "goals": count("core_goals"),
                "active_goals": count("core_goals", "WHERE status='active'"),
                "runs": count("core_runs"),
                "active_interventions": count(
                    "core_interventions", "WHERE status IN ('running','waiting')"),
                "open_work_orders": count(
                    "core_work_orders", "WHERE status IN ('open','claimed')"),
                "evidence": count("core_evidence"),
                "memory": count("core_memory"),
            }

    def trace(self, goal_id: str) -> dict:
        """Explain why execution happened by walking Goal → Run → Intervention."""
        with self.database.connect() as connection:
            goal = connection.execute(
                "SELECT * FROM core_goals WHERE id=?", (goal_id,)).fetchone()
            if goal is None:
                raise KeyError(f"unknown goal: {goal_id}")
            runs = connection.execute(
                "SELECT * FROM core_runs WHERE goal_id=? ORDER BY sequence", (goal_id,)
            ).fetchall()
            values = []
            for run in runs:
                interventions = connection.execute(
                    "SELECT * FROM core_interventions WHERE run_id=? ORDER BY created_at",
                    (run["id"],),
                ).fetchall()
                values.append({
                    "id": run["id"], "sequence": run["sequence"],
                    "stage": run["stage"], "status": run["status"],
                    "interventions": [{
                        "id": item["id"], "kind": item["kind"],
                        "description": item["description"], "status": item["status"],
                        "outcome": item["resolution_outcome"],
                        "context": json.loads(item["context_json"]),
                    } for item in interventions],
                })
        return {"goal": {"id": goal["id"], "name": goal["name"],
                         "status": goal["status"]}, "runs": values}

    def dashboard(self) -> dict:
        """One read-only company dashboard projection.

        Health counters, per-goal progress with stage/run/work-order state,
        pending attention, and workflow step positions — everything an owner
        or Director needs to see where the company stands, derived only
        from clean core tables.
        """
        with self.database.connect() as connection:
            goals = [dict(row) for row in connection.execute("""
                SELECT g.id, g.name, g.status, g.metric, g.target_json,
                       m.owner_id,
                       (SELECT COUNT(*) FROM core_evidence e
                         WHERE e.goal_id = g.id) AS evidence_count,
                       (SELECT COUNT(*) FROM core_work_orders w
                         WHERE w.goal_id = g.id
                           AND w.status IN ('open','claimed')) AS open_orders
                FROM core_goals g
                LEFT JOIN core_goal_metadata m ON m.goal_id = g.id
                ORDER BY CASE g.status WHEN 'active' THEN 0
                         WHEN 'paused' THEN 1 ELSE 2 END, g.created_at""")]
            for goal in goals:
                run = connection.execute("""SELECT id, sequence, stage,
                    status FROM core_runs WHERE goal_id=?
                    ORDER BY sequence DESC LIMIT 1""", (goal["id"],)).fetchone()
                if run is not None:
                    goal["run_id"] = run["id"]
                    goal["run_sequence"] = run["sequence"]
                    goal["stage"] = run["stage"]
                    goal["run_status"] = run["status"]
                    workflow_run = connection.execute("""
                        SELECT wr.id, wr.workflow_id, wr.current_step, wr.status,
                               (SELECT COUNT(*) FROM core_work_orders w
                                 WHERE w.workflow_run_id = wr.id) AS orders,
                               wr.steps_json
                        FROM core_workflow_runs wr WHERE wr.run_id=?
                        ORDER BY wr.created_at DESC LIMIT 1""", (run["id"],)).fetchone()
                    if workflow_run is not None:
                        goal["workflow_id"] = workflow_run["workflow_id"]
                        goal["workflow_status"] = workflow_run["status"]
                        goal["workflow_orders"] = workflow_run["orders"]
                        steps = json.loads(workflow_run["steps_json"] or "[]")
                        if steps:
                            goal["workflow_step"] = workflow_run["current_step"] + 1
                            goal["workflow_steps_total"] = len(steps)
            attention = [dict(row) for row in connection.execute("""
                SELECT id, goal_id, kind, payload_json, created_at
                FROM core_notifications WHERE status='pending'
                ORDER BY created_at LIMIT 20""")]
            for item in attention:
                item["payload"] = json.loads(item.pop("payload_json"))
            memory = {row[0]: row[1] for row in connection.execute("""
                SELECT scope, COUNT(*) FROM core_memory
                WHERE status='active' GROUP BY scope""")}
            # L3 repetition signal (issue #3): the same bounded direct
            # work executed over and over is the strongest hint the work
            # is reusable operational structure. The shape is the
            # EXECUTION pattern — same goal, same agent, same evidence
            # kind, same payload-key signature — so materially
            # equivalent work groups even when each instruction is
            # worded differently (the semantic repetition DECIDE
            # crystallizes a Workflow from). Three or more completed
            # orders surface as one bounded entry (at most five).
            # Read-only projection — no clustering, no embeddings.
            # Column order mirrors the SELECT below: 0 goal_id, 1
            # agent_id, 2 evidence kind, 3 evidence payload, 4 order brief.
            shapes: dict[tuple, dict] = {}
            for row in connection.execute("""SELECT work.goal_id, work.agent_id,
                evidence.kind, evidence.payload_json, work.brief_json, work.id
                FROM core_work_orders work
                JOIN core_evidence evidence ON evidence.work_order_id=work.id
                WHERE work.step_id='direct' AND work.status='completed'"""):
                try:
                    signature = tuple(sorted(json.loads(row[3])))
                except (json.JSONDecodeError, TypeError):
                    signature = ()
                shape = (row[0], row[1], row[2], signature)
                entry = shapes.setdefault(shape, {
                    "goal_id": row[0], "agent_id": row[1],
                    "evidence_kind": row[2], "orders": [],
                    "instructions": []})
                entry["orders"].append(row[5])
                try:
                    instruction = " ".join(
                        (json.loads(row[4]).get("instruction") or "").split())
                except (json.JSONDecodeError, TypeError):
                    instruction = ""
                if instruction:
                    entry["instructions"].append(instruction)
            repetition = [
                {"goal_id": entry["goal_id"], "agent_id": entry["agent_id"],
                 "evidence_kind": entry["evidence_kind"],
                 "completed_orders": len(entry["orders"]),
                 "instruction": (entry["instructions"][-1]
                                 if entry["instructions"] else None),
                 "suggestion": "this repeated work is reusable operational "
                               "structure — the runtime crystallizes a "
                               "Workflow from it"}
                for entry in sorted(
                    shapes.values(),
                    key=lambda item: (-len(item["orders"]), item["goal_id"]))
                if len(entry["orders"]) >= 3][:5]
        return {"health": self.health(), "goals": goals,
                "attention": attention, "memory": memory,
                "repetition": repetition}


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
