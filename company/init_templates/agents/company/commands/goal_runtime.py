"""CLI adapter for the canonical clean core."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
import weakref
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..agents.core import AgentResult
from ..agents.loader import available_agents
from ..goals import GoalRepository
from ..layout import layout_summary
from ..resolution.core import ApprovalRepository
from ..state import Database
from ..observability import Observer
from ..work_orders import WorkOrderRepository, executor_identity
from ..workflows import Workflow, WorkflowRepository, WorkflowStep
from ..runtime.engine import Decision, Evaluation, GoalRuntime
from ..runtime.registry import departments
from ..runtime.util import compare


class CatalogController:
    """Translate portable Department declarations into clean Workflows."""

    def __init__(self, database: Database):
        self.database = database
        self.goals = GoalRepository(database)
        self.workflows = WorkflowRepository(database)
        self.departments = departments()

    def observe(self, context) -> dict:
        goal = context.goal
        handler = self.departments.get(goal.owner_id)
        kinds = tuple((getattr(handler, "evidence_metrics", {}) or {}).get(goal.metric) or ())
        if kinds:
            matching = [item for item in context.evidence if item.kind in kinds]
        elif handler is not None:
            # The department owns this metric space but does not declare a
            # mapping for this metric. Match only evidence whose payload
            # carries the metric key itself; never count unrelated kinds.
            matching = [item for item in context.evidence
                        if isinstance(item.payload.get(goal.metric),
                                      (int, float, bool))]
        else:
            # Departmentless owner (director): every evidence item is a
            # direct answer to the goal.
            matching = list(context.evidence)
        candidates = [item.payload[goal.metric] for item in matching
                      if isinstance(item.payload.get(goal.metric), (int, float, bool))]
        aggregation = goal.aggregation
        if aggregation == "count":
            value = len(matching)
        elif aggregation == "sum":
            value = sum(item for item in candidates if not isinstance(item, bool))
        elif aggregation == "latest":
            value = candidates[-1] if candidates else 0
        elif aggregation == "max":
            numeric = [item for item in candidates if not isinstance(item, bool)]
            value = max(numeric) if numeric else 0
        elif aggregation == "min":
            numeric = [item for item in candidates if not isinstance(item, bool)]
            value = min(numeric) if numeric else 0
        elif aggregation == "boolean_all":
            value = bool(candidates) and all(item is True for item in candidates)
        else:
            value = any(item is True for item in candidates)
        if goal.owner_id == "director" and goal.metric == "all_children_achieved":
            children = [item for item in self.goals.list() if item.parent_id == goal.id]
            value = bool(children) and all(item.status == "complete" for item in children)
        return {goal.metric: value, "evidence_ids": [item.id for item in matching]}

    def decide(self, context, observation: dict) -> Decision:
        goal = context.goal
        if compare(observation.get(goal.metric, 0), goal.operator, goal.target):
            return Decision("evaluate", "Goal evidence meets its target",
                            context={"result_ready": True})
        handler = self.departments.get(goal.owner_id)
        if handler is None:
            return Decision("request_agent", f"{goal.owner_id} must choose bounded work",
                            context={"agent_id": goal.owner_id,
                                     "evidence_kind": goal.metric})
        requested = (goal.config or {}).get("workflow")
        workflow = next((item for item in handler.workflows
                         if item.id == requested), None)
        if workflow is None:
            workflow = handler.workflows[0] if handler.workflows else None
        if workflow is None:
            return Decision("request_agent", f"{goal.owner_id} must produce {goal.metric}",
                            context={"agent_id": goal.owner_id,
                                     "evidence_kind": goal.metric})
        if not isinstance(workflow, Workflow):
            raise TypeError("Department workflows must use company.workflows.Workflow")
        workflow_id = f"{goal.owner_id}:{workflow.id}"
        self.workflows.save(Workflow(
            workflow_id, workflow.name, workflow.steps, goal.owner_id,
            workflow.version))
        return Decision("execute_workflow", workflow.name, workflow_id)

    def evaluate(self, context, decision: Decision, evidence: tuple) -> Evaluation:
        observation = self.observe(context)
        value = observation.get(context.goal.metric, 0)
        return Evaluation(
            compare(value, context.goal.operator, context.goal.target),
            {context.goal.metric: value}, "clean-core evidence evaluated",
            evidence_ids=tuple(observation["evidence_ids"]))


class AssignmentExecutor:
    """Park work for an external Host; never execute a capability implicitly."""

    def execute(self, agent, order) -> AgentResult:
        return AgentResult(
            "ask_user", message=f"WorkOrder {order.id} is ready for Agent {agent.id}")


class CleanCommandRuntime:
    """CLI projection backed exclusively by clean-core records."""

    # Read-only scratch snapshots are cached per (path, mtime, size) at
    # process scope: every model request used to copy the whole database.
    _SNAPSHOT_CACHE: dict[tuple[str, float, int], Path] = {}
    _SNAPSHOT_ROOT: Path | None = None
    _SNAPSHOT_FINALIZERS: list = []

    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        self._readonly_scratch = None
        self._scratch_finalizer = None
        database_path = self.path
        database_readonly = readonly
        if readonly:
            # Read commands use a scratch snapshot. This keeps the
            # requested database byte-for-byte read-only even when its schema
            # predates the current projection. Snapshots are cached per
            # (path, mtime, size) so repeated host requests over an
            # unchanged database cost one copy, not one per request.
            self._readonly_scratch = self._cached_snapshot(self.path)
            self._scratch_finalizer = None  # process-lifetime cache owns it
            database_path = self._readonly_scratch / "empty.sqlite"
            database_readonly = False
        self.database = Database(database_path, readonly=database_readonly)
        self.runtime = GoalRuntime(
            database_path, CatalogController(self.database), AssignmentExecutor(),
            agents=available_agents(self._home_from_database()),
            readonly=database_readonly)
        self.goals = self.runtime.goals
        self.runs = self.runtime.runs
        self.interventions = self.runtime.interventions
        self.evidence = self.runtime.evidence
        self.memory = self.runtime.memory
        self.work_orders_repository = WorkOrderRepository(self.database)
        self.approvals = ApprovalRepository(self.database)

    @classmethod
    def _cached_snapshot(cls, live: Path) -> Path:
        """One scratch copy of the live database per (path, mtime, size).

        Falls back to an empty snapshot when the database does not exist
        yet (fresh homes). Stale entries are evicted so a changed database
        is re-copied; each runtime still reads its snapshot read-write via
        SQLite while the live file is never opened for writing.
        """
        stamp = ((live.stat().st_mtime, live.stat().st_size)
                 if live.exists() else (0.0, 0))
        key = (str(live), *stamp)
        cached = cls._SNAPSHOT_CACHE.get(key)
        if cached is not None and (cached / "empty.sqlite").is_file():
            return cached
        if cls._SNAPSHOT_ROOT is None:
            cls._SNAPSHOT_ROOT = Path(tempfile.mkdtemp(prefix="spielos-readonly-"))
            import atexit
            atexit.register(shutil.rmtree, cls._SNAPSHOT_ROOT, True)
        # Evict stale snapshots of the same database (bounded cache).
        for other in [k for k in cls._SNAPSHOT_CACHE
                      if k[0] == key[0] and k != key]:
            cls._SNAPSHOT_CACHE.pop(other, None)
        scratch = cls._SNAPSHOT_ROOT / f"snapshot-{abs(hash(key))}"
        scratch.mkdir(parents=True, exist_ok=True)
        destination_path = scratch / "empty.sqlite"
        if live.exists():
            source = sqlite3.connect(f"file:{live}?mode=ro", uri=True)
            destination = sqlite3.connect(destination_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
        else:
            destination_path.touch()
        cls._SNAPSHOT_CACHE[key] = scratch
        return scratch

    def _home_from_database(self):
        """The home implied by the canonical database layout, when present.

        The state database lives at ``<home>/.spielos/state/company.sqlite``
        (or ``<state>/company.sqlite`` in tests), so its third parent names
        the home whose ``agents/installed`` layer this runtime executes for.
        Any other layout falls back to normal home discovery inside the
        loader.
        """
        parents = Path(self.path).absolute().parents
        return parents[2] if len(parents) >= 3 else None

    @staticmethod
    def _operator(value: str) -> str:
        return {"ge": "ge", ">=": "ge", "gt": "gt", ">": "gt",
                "eq": "eq", "==": "eq", "le": "le", "<=": "le",
                "lt": "lt", "<": "lt"}.get(value, value)

    @staticmethod
    def _validate_goal_metric(owner_id: str, metric: str) -> None:
        """Refuse goals a Department can never prove (D3).

        A goal whose owner is a declared Department must use a metric that
        department declares (in ``evidence_metrics`` or
        ``goal_schema["metrics"]``). Otherwise the goal would accept any
        evidence — or worse, none could ever satisfy it. Director-owned
        goals keep the departmentless ``request_agent`` path.
        """
        handler = departments().get(owner_id)
        if handler is None:
            return
        declared = set(getattr(handler, "evidence_metrics", {}) or ())
        schema = getattr(handler, "goal_schema", None) or {}
        declared.update(schema.get("metrics") or ())
        if metric in declared:
            return
        listed = ", ".join(sorted(declared)) or "(none declared)"
        raise ValueError(
            f"Department {owner_id!r} does not declare metric {metric!r}; "
            f"declared metrics: {listed}")

    def _require_writable(self) -> None:
        if self.readonly:
            raise PermissionError("clean-core runtime was opened read-only")

    def connect(self):
        return self.database.connect()

    def create_goal(self, **values) -> dict:
        self._require_writable()
        self._validate_goal_metric(values.get("owner_id") or "goal-runtime",
                                   values["metric"])
        goal = self.runtime.create_goal(
            values["name"], values["metric"], self._operator(values["operator"]),
            values["target"], parent_id=values.get("parent_id"),
            goal_id=values.get("goal_id"), owner_id=values.get("owner_id") or "goal-runtime",
            deadline=values.get("deadline"), config=values.get("config") or {})
        for target in (values.get("config") or {}).get("supports_goal_ids") or ():
            self.goals.add_support(goal.id, target)
        for target in (values.get("config") or {}).get("blocks_goal_ids") or ():
            self.goals.add_block(goal.id, target)
        return self._goal(goal)

    def _goal(self, goal) -> dict:
        run = self.runs.current(goal.id)
        return {"id": goal.id, "name": goal.name, "owner_id": goal.owner_id,
                "metric": goal.metric, "operator": goal.operator, "target": goal.target,
                "aggregation": goal.aggregation,
                "deadline": goal.deadline, "parent_id": goal.parent_id,
                "goal_status": "achieved" if goal.status == "complete" else goal.status,
                "config": goal.config or {}, "run_id": run.id, "run_type": "execution",
                "run_status": run.status, "stage": run.stage.value,
                "step": run.stage.value.lower(), "evidence_count": len(self.evidence.for_run(run.id)),
                "evidence_validity": "technical_only", "runtime_updated_at": "",
                "why_next": "Continue the persisted clean-core Run."}

    def status(self, goal_id: str) -> dict:
        goal = self.goals.get(goal_id); run = self.runs.current(goal_id)
        evidence = [asdict(item) for item in self.evidence.for_run(run.id)]
        goal_row = self._goal(goal)
        run_row = {"id": run.id, "sequence": run.sequence, "run_type": "execution",
                   "status": run.status, "evidence_validity": "technical_only"}
        attention = self.attention(goal_id=goal_id)
        return {"goal": goal_row, "run": run_row,
                "evidence": evidence, "evaluation": None if run.evaluation is None
                else asdict(run.evaluation),
                "pending_notifications": self.notifications(goal_id=goal_id),
                "attention": attention,
                "work_orders": self.work_orders(status="active", goal_id=goal_id)}

    def goal_summaries(self, *, statuses=None, goal_id=None, limit=100):
        values = [self._goal(item) for item in self.goals.list()
                  if goal_id is None or item.id == goal_id]
        if statuses:
            values = [item for item in values if item["goal_status"] in statuses]
        return values[:limit]

    def company_snapshot(self, recent_limit=5):
        values = self.goal_summaries(limit=100)
        active = [item for item in values if item["goal_status"] == "active"]
        paused = [item for item in values if item["goal_status"] == "paused"]
        terminal = [item for item in values
                    if item["goal_status"] in {"achieved", "abandoned"}]
        counts = {key: sum(item["goal_status"] == key for item in values)
                  for key in ("active", "achieved", "abandoned", "expired")}
        counts["total"] = len(values)
        with self.database.connect() as connection:
            goal_links = [dict(row) for row in connection.execute(
                "SELECT source_goal_id,target_goal_id,relation FROM core_goal_edges")]
        return {"counts": counts, "focus_goal": active[0] if active else None,
                "attention": self.attention(),
                "work_orders": self.work_orders(status="active", limit=20),
                "active_goals": active, "paused_goals": paused,
                "unread_results": self.unread_results(),
                "recent_memory": self.memories(limit=20),
                "goal_links": goal_links,
                "support_links": [item for item in goal_links
                                  if item["relation"] == "supports"],
                "block_links": [item for item in goal_links
                                if item["relation"] == "blocks"],
                "recent_results": terminal[:recent_limit]}

    def topology_audit(self):
        goals = self.goals.list()
        by_id = {item.id: item for item in goals}
        roots = sorted(item.id for item in goals if not item.parent_id)
        defects = []
        for goal in goals:
            if goal.parent_id and goal.parent_id not in by_id:
                defects.append({"goal_id": goal.id, "kind": "missing_parent",
                                "parent_id": goal.parent_id})
            seen, current = {goal.id}, goal
            while current.parent_id and current.parent_id in by_id:
                if current.parent_id in seen:
                    defects.append({"goal_id": goal.id, "kind": "parent_cycle"})
                    break
                seen.add(current.parent_id)
                current = by_id[current.parent_id]
        with self.database.connect() as connection:
            edges = [dict(row) for row in connection.execute(
                "SELECT source_goal_id,target_goal_id,relation FROM core_goal_edges")]
        for relation in ("supports", "blocks"):
            graph = {goal_id: set() for goal_id in by_id}
            for edge in (item for item in edges if item["relation"] == relation):
                source, target = edge["source_goal_id"], edge["target_goal_id"]
                if source not in by_id or target not in by_id:
                    defects.append({"goal_id": target, "kind": f"missing_{relation}_goal",
                                    "source_goal_id": source,
                                    "target_goal_id": target})
                    continue
                graph[source].add(target)
                if (relation == "blocks" and by_id[source].status == "abandoned"
                        and by_id[target].status == "active"):
                    defects.append({
                        "goal_id": target,
                        "kind": "permanently_blocked_by_abandoned_goal",
                        "blocker_goal_id": source})
            visiting, visited = set(), set()
            def visit(goal_id):
                if goal_id in visiting:
                    defects.append({"goal_id": goal_id,
                                    "kind": f"{relation[:-1]}_cycle"})
                    return
                if goal_id in visited:
                    return
                visiting.add(goal_id)
                for target in graph[goal_id]:
                    visit(target)
                visiting.remove(goal_id)
                visited.add(goal_id)
            for goal_id in sorted(graph):
                visit(goal_id)
        if len(roots) != 1:
            defects.extend({"goal_id": item,
                            "kind": "disconnected_non_primary_root"}
                           for item in roots)
        return {"goal_count": len(goals), "root_goal_ids": roots,
                "canonical_root_goal_id": roots[0] if len(roots) == 1 else None,
                "defects": defects}

    def approve(self, goal_id, note="", keys=(), scope="step"):
        """Grant approval keys and resume a waiting run.

        ``scope="step"`` (default) binds each granted key to the current
        intervention; the next run re-parks for its own approval. 
        ``scope="run"`` grants run-wide keys (intervention_id NULL): the
        repository's run-key fallback then satisfies every later
        intervention of the SAME run, so one approval carries a multi-step
        run through all of its remaining gates.
        """
        self._require_writable()
        if scope not in {"step", "run"}:
            raise ValueError("approve scope must be 'step' or 'run'")
        run = self.runs.current(goal_id)
        intervention = self.interventions.active_for_run(run.id)
        granted = set(keys)
        if intervention is not None:
            workflow_run = self.runtime.resolution.workflows.active_for_intervention(
                intervention.id)
            if workflow_run is not None:
                if workflow_run.current_step < len(workflow_run.steps):
                    required = workflow_run.steps[workflow_run.current_step].approval_keys
                    if required and not granted:
                        granted.update(required)
        if not granted:
            granted.add("execute")
        for key in granted:
            self.approvals.grant(
                goal_id=goal_id, run_id=run.id, key=key,
                intervention_id=None if (scope == "run" or intervention is None)
                else intervention.id,
                note=note)
        if run.status == "waiting":
            self.runtime.resume(goal_id)
        return self.status(goal_id)

    def add_evidence(self, goal_id, *, kind, source, payload, validity=None):
        self._require_writable()
        run = self.runs.current(goal_id)
        intervention = self.interventions.active_for_run(run.id)
        self.evidence.record(goal_id=goal_id, run_id=run.id, kind=kind,
                             intervention_id=None if intervention is None else intervention.id,
                             payload={**payload, "source": source,
                                      "validity": validity or "technical_only"})
        return self.status(goal_id)

    def once(self, goal_id, holder=None):
        self._require_writable()
        self.runtime.advance(goal_id)
        return self.status(goal_id)

    def tick(self, max_advances=100):
        self._require_writable()
        return self.runtime.tick(max_advances=max_advances)

    def watch(self, interval_seconds=5.0, goal_id=None, max_ticks=None):
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            result = (self.once(goal_id) if goal_id
                      else self.tick(max_advances=100))
            ticks += 1
            yield result
            if max_ticks is None or ticks < max_ticks:
                time.sleep(interval_seconds)

    def work_order(self, order_id):
        return self._order(self.work_orders_repository.get(order_id))

    def work_orders(self, status=None, goal_id=None, limit=100):
        with self.database.connect() as connection:
            clauses, args = [], []
            if goal_id:
                clauses.append("goal_id=?"); args.append(goal_id)
            if status in {"active", "open", "claimed"}:
                clauses.append("status IN ('open','claimed')" if status == "active" else "status=?")
                if status != "active": args.append(status)
            sql = "SELECT id FROM core_work_orders"
            if clauses: sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY created_at LIMIT ?"; args.append(limit)
            ids = [row[0] for row in connection.execute(sql, args)]
        return [self.work_order(item) for item in ids]

    def _order(self, order):
        return {**asdict(order), "needed": 1,
                "accepts_evidence": [order.brief.get("evidence_kind")]
                if order.brief.get("evidence_kind") else [], "why_next": "Agent assignment"}

    def claim_work_order(self, work_order_id, agent_id):
        self._require_writable()
        return self._order(self.work_orders_repository.claim(work_order_id, agent_id))

    def complete_work_order(self, work_order_id, agent_id, evidence,
                            learning=None):
        """Complete one order atomically; optionally persist learning.

        ``agent_id`` may be the bare agent id or the runtime's historical
        ``executor:<agent_id>`` claimant — both name the same executor
        (see company.work_orders.executor_identity). ``learning`` (the
        ``tasks --complete --learning`` flag) persists workflow-scope
        memory grounded in the evidence just recorded, with full
        Goal/Run/Intervention/Workflow lineage enforced by
        MemoryRepository.remember — the same guard the engine path uses.
        """
        self._require_writable()
        order = self.work_orders_repository.get(work_order_id)
        if order.status == "open":
            order = self.work_orders_repository.claim(work_order_id, agent_id)
        elif executor_identity(order.claimed_by or "") != executor_identity(agent_id):
            raise RuntimeError(
                f"work order is claimed by {order.claimed_by!r}, not {agent_id!r}")
        if not evidence:
            raise ValueError("completing a clean-core WorkOrder requires Evidence")
        first = evidence[0]
        order, evidence_ids = self.work_orders_repository.complete_with_evidence(
            work_order_id, {"evidence": evidence}, executor_id=agent_id,
            kind=first["kind"], payload=first.get("payload") or {},
            evidence_items=[(item["kind"], item.get("payload") or {})
                            for item in evidence],
            advance_workflow=bool(order.workflow_run_id), wake_run=True)
        if learning:
            self._remember_workflow_learning(order, learning, evidence_ids)
        return {"work_order": self._order(order)}

    def _remember_workflow_learning(self, order, learning, evidence_ids):
        """Persist workflow memory for a completed order (mirrors the
        ResolutionCycle executor path: evidence + lineage are mandatory)."""
        workflow_id = None
        if order.workflow_run_id:
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT workflow_id FROM core_workflow_runs WHERE id=?",
                    (order.workflow_run_id,)).fetchone()
            workflow_id = row[0] if row else None
        return self.memory.remember(
            "workflow", learning, evidence_ids=tuple(evidence_ids),
            goal_id=order.goal_id, run_id=order.run_id,
            intervention_id=order.intervention_id, workflow_id=workflow_id)

    def add_memory(self, scope, claim, evidence_ids=(), goal_id=None,
                   run_id=None, intervention_id=None, workflow_id=None):
        """CLI memory write path (`memory add`) for workflow/strategy scope.

        The engine guards stay the single authority: scope validity,
        evidence presence, and Goal/Run/Intervention lineage are enforced
        by MemoryRepository.remember; strategy learning additionally
        requires evidence from the named run.
        """
        self._require_writable()
        if scope not in {"workflow", "strategy"}:
            raise ValueError("memory add supports workflow and strategy scope; "
                             "owner memory is written with profile set")
        return self.memory.remember(
            scope, claim, evidence_ids=tuple(evidence_ids), goal_id=goal_id,
            run_id=run_id, intervention_id=intervention_id,
            workflow_id=workflow_id)

    def memories(self, limit=100, **_kwargs):
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute("""SELECT id,scope,claim,
                goal_id,run_id,intervention_id,workflow_id,confidence,status,
                supersedes_id,created_at FROM core_memory
                ORDER BY created_at DESC LIMIT ?""", (limit,))]

    @staticmethod
    def _profile(memory):
        key, separator, raw = memory.claim.partition(" = ")
        namespace, dot, claim_key = key.partition(".")
        try:
            value = json.loads(raw) if separator else memory.claim
        except json.JSONDecodeError:
            value = raw
        return {**asdict(memory), "namespace": namespace if dot else "owner",
                "claim_key": claim_key if dot else key, "value": value}

    def set_profile_claim(self, *, namespace, claim_key, value, scope="company",
                          goal_id=None, workflow_id=None, **_kwargs):
        self._require_writable()
        prefix = f"{namespace}.{claim_key} = "
        current = next((item for item in self.memory.relevant(
            scope="owner", limit=200) if item.claim.startswith(prefix)), None)
        memory = self.memory.remember(
            "owner", prefix + json.dumps(value, sort_keys=True), goal_id=goal_id,
            workflow_id=workflow_id, supersedes_id=current.id if current else None)
        return self._profile(memory)

    def owner_memory(self, *, goal_id=None, workflow_id=None, limit=200, **_kwargs):
        return tuple(self._profile(item) for item in self.memory.relevant(
            scope="owner", goal_id=goal_id, workflow_id=workflow_id, limit=limit))

    def clean_memory_summary(self):
        records = self.memories(limit=200)
        active = [item for item in records if item["status"] == "active"]
        by_scope = {scope: [item for item in active if item["scope"] == scope]
                    for scope in ("owner", "workflow", "strategy")}
        return {"schema_version": 3, "durable_memory": by_scope,
                "counts": {scope: len(items) for scope, items in by_scope.items()}}

    def assemble_context(self, *, prompt="", owner_id=None, workflow_id=None,
                         token_budget=None, **_kwargs):
        goals = [item for item in self.goals.list()
                 if item.status == "active" and (not owner_id or item.owner_id == owner_id)]
        goal = goals[0] if goals else None
        run = self.runs.current(goal.id) if goal else None
        evidence = self.evidence.for_goal(goal.id)[-20:] if goal else []
        memory = self.memory.relevant(
            goal_id=goal.id if goal else None, workflow_id=workflow_id, limit=20)
        lines = [f"Request: {prompt}" if prompt else "Current clean-core context"]
        sources = []
        if goal and run:
            lines.append(
                f"Goal: {goal.name} ({goal.id}) · Run {run.sequence} · {run.stage.value}/{run.status}")
            sources.append(f"goal:{goal.id}")
        if evidence:
            lines.append("Evidence: " + "; ".join(
                f"{item.kind}={json.dumps(item.payload, sort_keys=True)}"
                for item in evidence))
            sources.extend(item.id for item in evidence)
        if memory:
            lines.append("Memory: " + "; ".join(item.claim for item in memory))
            sources.extend(item.id for item in memory)
        attention = self.attention(limit=5)
        if attention:
            lines.append("Attention: " + "; ".join(
                f"{item.get('kind')}: {item.get('message') or 'owner input required'}"
                for item in attention))
            sources.extend(str(item.get("id")) for item in attention)
        profile = self.owner_memory(limit=8)
        if profile:
            lines.append("Profile: " + "; ".join(
                f"{item['namespace']}.{item['claim_key']}="
                f"{json.dumps(item['value'], sort_keys=True)}"
                for item in profile))
        home = self.path.parents[2] if len(self.path.parents) >= 3 else None
        if home is not None:
            lines.append("Layout: " + layout_summary(home))
        rendered = "\n".join(lines)
        if token_budget:
            rendered = rendered[:max(1, int(token_budget)) * 4]
        return {"context": rendered, "sources": sources,
                "goal_id": goal.id if goal else None,
                "run_id": run.id if run else None,
                "workflow_id": workflow_id}

    def notifications(self, status="pending", limit=100, goal_id=None, **_kwargs):
        clauses, args = ["status=?"], [status]
        if goal_id:
            clauses.append("goal_id=?"); args.append(goal_id)
        args.append(limit)
        with self.database.connect() as connection:
            rows = connection.execute("""SELECT * FROM core_notifications WHERE """
                + " AND ".join(clauses) + " ORDER BY created_at LIMIT ?", args)
            return [{**dict(row), "payload": json.loads(row["payload_json"])}
                    for row in rows]

    def acknowledge_notification(self, notification_id):
        self._require_writable()
        with self.database.connect() as connection:
            updated = connection.execute("""UPDATE core_notifications
                SET status='acknowledged', acknowledged_at=?
                WHERE id=? AND status='pending'""",
                (datetime.now(timezone.utc).isoformat(), notification_id))
            if not updated.rowcount:
                raise ValueError(f"unknown pending notification: {notification_id}")
        return {"id": notification_id, "status": "acknowledged"}

    def attention(self, limit=100, goal_id=None, **_kwargs):
        return [{"id": item["id"], "kind": item["kind"],
                 **item["payload"]} for item in self.notifications(
                     goal_id=goal_id, limit=limit)]

    def observe(self, goal_id=None, health=False):
        """Read-only observability projection (the company dashboard).

        ``observe`` alone renders the full dashboard: health counters,
        per-goal progress (stage, run, workflow position, open work
        orders), pending attention, and memory totals. ``--goal`` renders
        the causal trace for one Goal; ``--health`` renders only counters.
        """
        observer = Observer(self.database)
        if goal_id:
            return observer.trace(goal_id)
        if health:
            return observer.health()
        return observer.dashboard()

    def unread_results(self, goal_id=None, **_kwargs):
        clauses, args = ["r.status='complete'"], []
        if goal_id:
            clauses.append("r.goal_id=?"); args.append(goal_id)
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute("""SELECT r.id,r.goal_id,
                r.evaluation_json AS result FROM core_runs r WHERE """
                + " AND ".join(clauses) + " ORDER BY r.updated_at DESC LIMIT 20", args)]
