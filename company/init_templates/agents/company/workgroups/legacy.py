"""Temporary adapter from legacy Department packages to Worker-owned work.

This is deliberately the only bridge that knows about ``departments/``.  The
runtime discovers Workgroups, then resolves every workflow to its lead Worker.
As packages move to ``workgroups/<id>/workers/``, this adapter is removed
without changing goals, work orders, approvals, or evidence persistence.
"""

from __future__ import annotations

from ..agents import agents as installed_agents
from ..runtime.interpreter import InterpretedDepartment
from ..runtime.models import Department, WorkgroupSpec, WorkerSpec, WorkflowSpec


def _lead_for(department: Department, workflow: WorkflowSpec) -> str:
    mapping = getattr(department, "workflow_agents", None) or {}
    return str(mapping.get(workflow.id) or (workflow.agent_ids or ("",))[0])


def workgroup_from_legacy(department: Department) -> WorkgroupSpec:
    """Project one legacy package into the canonical Workgroup shape."""

    by_worker: dict[str, list[WorkflowSpec]] = {}
    workflows = tuple(getattr(department, "workflows", ()) or ())
    for workflow in workflows:
        worker_id = _lead_for(department, workflow)
        if worker_id:
            by_worker.setdefault(worker_id, []).append(workflow)
    roster = installed_agents()
    workers: list[WorkerSpec] = []
    for worker_id in tuple(getattr(department, "agent_ids", ()) or ()):
        agent = roster.get(worker_id)
        owned = tuple(by_worker.get(worker_id, ()))
        if agent is None:
            agent = WorkerSpec(worker_id, worker_id, (), (), (), workgroup_id=department.id)
        workers.append(WorkerSpec(
            id=agent.id,
            description=agent.description,
            skill_ids=agent.skill_ids,
            permissions=agent.permissions,
            produces=agent.produces,
            workgroup_id=department.id,
            workflows=owned,
        ))
    schema = dict(getattr(department, "goal_schema", None) or {})
    return WorkgroupSpec(
        id=department.id,
        version=str(getattr(department, "version", "0.0.0")),
        description=str(getattr(department, "description", "")),
        workers=tuple(workers),
        metrics=tuple(schema.get("metrics") or ()),
        config_schema=dict(schema.get("config") or {}),
        evidence_metrics={key: tuple(value) for key, value in
                          (getattr(department, "evidence_metrics", None) or {}).items()},
    )


class WorkgroupHandler(InterpretedDepartment, Department):
    """Compatibility runtime adapter; execution resolves to a Worker workflow."""

    def __init__(self, workgroup: WorkgroupSpec, legacy: Department):
        self.workgroup = workgroup
        self._legacy = legacy
        self.id = self.department_id = workgroup.id
        self.version = workgroup.version
        self.description = workgroup.description
        self.agent_ids = tuple(worker.id for worker in workgroup.workers)
        self.workflows = tuple(
            workflow for worker in workgroup.workers for workflow in worker.workflows)
        self.workflow_agents = {
            workflow.id: worker.id
            for worker in workgroup.workers for workflow in worker.workflows
        }
        self.evidence_metrics = dict(workgroup.evidence_metrics)
        self.goal_schema = {"metrics": list(workgroup.metrics),
                            "config": dict(workgroup.config_schema)}
        self.default_strategy_context = getattr(legacy, "default_strategy_context", None)

    def __getattr__(self, name):
        """Expose legacy package-only hooks while the package is extracted."""
        return getattr(self._legacy, name)

    def worker_for_workflow(self, workflow_id: str | None) -> WorkerSpec | None:
        for worker in self.workgroup.workers:
            if workflow_id is None and worker.workflows:
                return worker
            if any(item.id == workflow_id for item in worker.workflows):
                return worker
        return None

    def _uses_legacy_exception(self, ctx) -> bool:
        predicate = getattr(self._legacy, "uses_email_exception", None)
        return bool(predicate and predicate(ctx))

    def observe(self, ctx):
        if self._uses_legacy_exception(ctx):
            return self._legacy.observe(ctx)
        return InterpretedDepartment.observe(self, ctx)

    def decide(self, ctx, observation):
        if self._uses_legacy_exception(ctx):
            return self._legacy.decide(ctx, observation)
        return InterpretedDepartment.decide(self, ctx, observation)

    def act(self, ctx, decision):
        if self._uses_legacy_exception(ctx):
            return self._legacy.act(ctx, decision)
        return InterpretedDepartment.act(self, ctx, decision)

    def evaluate(self, ctx, action_result):
        if self._uses_legacy_exception(ctx):
            return self._legacy.evaluate(ctx, action_result)
        return InterpretedDepartment.evaluate(self, ctx, action_result)
