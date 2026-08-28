"""One portable command surface for Codex, OpenCode, and humans."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .runtime.models import GoalStatus
from .runtime.registry import departments
from .runtime.runner import Runner
from .runtime.loop import Runtime
from .runtime.paths import find_project_root
from .runtime.service import RunnerService

PROJECT_ROOT = find_project_root()
DEFAULT_DB = PROJECT_ROOT / ".spielos" / "state" / "company.sqlite"


def build_parser():
    parser = argparse.ArgumentParser(prog="python3 -m company")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--version", action="store_true",
                        help="print the spielos version and exit")
    commands = parser.add_subparsers(dest="command", required=True)
    departments_parser = commands.add_parser("departments")
    departments_parser.add_argument("--json", action="store_true")
    commands.add_parser("catalog")
    init = commands.add_parser("init", help="scaffold a self-contained harness home (see README)")
    init.add_argument("--dir", default=".", help="target directory (default: cwd)")
    init.add_argument("--force", action="store_true", help="overwrite existing files")
    init.add_argument("--minimal", action="store_true",
                      help="legacy alias — the fresh spine (no departments) is already the default")
    init.add_argument("--all-departments", action="store_true",
                      help="vendor every example department + website skills")
    init.add_argument("--department", action="append", default=[],
                      help="vendor this starter department from templates (repeatable)")
    init.add_argument("-y", "--yes", action="store_true",
                      help="non-interactive: accept defaults, never prompt")
    init.add_argument("--json", action="store_true",
                      help="print the machine-readable receipt instead of the human card")
    add_cmd = commands.add_parser("add", help="install a department bundle (.sdep) or built-in id into this home")
    add_cmd.add_argument("source", help="path/to.bundle.sdep, bundle dir, or built-in department id")
    add_cmd.add_argument("--force", action="store_true")
    add_cmd.add_argument("--dir", help="exact SpielOS home to modify (default: current/nearest home)")
    refresh = commands.add_parser("refresh", help="re-vendor the runtime spine + host adapters from newest templates (user layer preserved)")
    refresh.add_argument("--force", action="store_true", default=True)
    refresh.add_argument("--dir", help="exact SpielOS home to update (default: current/nearest home)")
    agent = commands.add_parser("agent", help="first-class worker operations")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    compile_cmd = agent_commands.add_parser("compile",
        help="compile a department workflow into a first-class agent worker")
    compile_cmd.add_argument("department", help="department id")
    compile_cmd.add_argument("--workflow", required=True, help="workflow id inside the department")
    compile_cmd.add_argument("--name", help="worker name (default: <department>-<workflow>)")
    compile_cmd.add_argument("--force", action="store_true")
    compile_cmd.add_argument("--dir", help="exact SpielOS home to modify (default: current/nearest home)")
    strategy = commands.add_parser("strategy", help="show the read-only Strategy Kernel")
    strategy.add_argument("--topic", action="append", default=[])
    strategy.add_argument("--scope", action="append", default=[])
    strategy.add_argument("--layer", action="append", choices=(
        "intent", "model", "policy", "constitution"), default=[])
    strategy.add_argument("--max-sections", type=int, default=8)
    strategy.add_argument("--json", action="store_true")
    department = commands.add_parser("department", help="install/validate Department Lego packages")
    department_commands = department.add_subparsers(dest="department_command", required=True)
    install = department_commands.add_parser("install")
    install.add_argument("--spec", help="department_spec JSON object")
    install.add_argument("--file", help="path to department_spec JSON file")
    install.add_argument("--force", action="store_true")
    install.add_argument("--id", help="override/default department id")
    install.add_argument("--version", help="override/default version")
    install.add_argument("--dir", help="exact SpielOS home to modify (default: current/nearest home)")
    validate = department_commands.add_parser("validate")
    validate.add_argument("--spec", help="department_spec JSON object")
    validate.add_argument("--file", help="path to department_spec JSON file")
    validate.add_argument("--id", help="override/default department id")
    dept_list = department_commands.add_parser("list")
    dept_list.add_argument("--json", action="store_true")
    dept_export = department_commands.add_parser("export",
        help="bundle one department (+ its company skills) into a portable .sdep")
    dept_export.add_argument("id", help="department id to export")
    dept_export.add_argument("--out", default=".", help="output directory")
    workgroup = commands.add_parser("workgroup", help="validate and install Worker-owned Workgroup packages")
    workgroup_commands = workgroup.add_subparsers(dest="workgroup_command", required=True)
    for name in ("validate", "install"):
        item = workgroup_commands.add_parser(name)
        item.add_argument("--spec", help="Workgroup JSON object")
        item.add_argument("--file", help="path to Workgroup JSON file")
        if name == "install":
            item.add_argument("--force", action="store_true")
            item.add_argument("--dir", help="exact SpielOS home to modify (default: source checkout/current home)")
    workgroup_commands.add_parser("list")
    goal = commands.add_parser("goal")
    goals = goal.add_subparsers(dest="goal_command", required=True)
    create = goals.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--owner", required=True)
    create.add_argument("--metric", required=True)
    create.add_argument("--operator", choices=("ge", "gt", "eq", "le", "lt"), default="ge")
    create.add_argument("--target", required=True)
    create.add_argument("--deadline")
    create.add_argument("--parent")
    create.add_argument("--supports", action="append", default=[],
                        help="Goal ID this Goal causally supports; repeat for a support DAG")
    create.add_argument("--priority", choices=("critical", "high", "normal", "low", "deferred"))
    create.add_argument("--config", default="{}")
    create.add_argument("--id")
    create.add_argument("--run-type", default="execution",
                        choices=("business_experiment", "execution", "diagnostic", "system_improvement", "evaluation", "system_test"))
    create.add_argument("--hypothesis", default="{}", help="JSON: statement, variable, prediction")
    create.add_argument("--controlled", default="{}", help="JSON object of fixed variables")
    create.add_argument("--changed", default="{}", help="JSON object of changed variables")
    create.add_argument("--validity", default="business",
                        choices=("business", "technical_only", "contaminated", "invalid"))
    create.add_argument("--parent-run")
    create.add_argument("--triggered-by")
    create.add_argument("--resume-run")
    create.add_argument("--json", action="store_true")
    goal_list = goals.add_parser("list")
    goal_list.add_argument("--json", action="store_true")
    show = goals.add_parser("show"); show.add_argument("goal_id")
    show.add_argument("--json", action="store_true")
    link = goals.add_parser("link"); link.add_argument("goal_id")
    link.add_argument("--supports", required=True)
    link.add_argument("--json", action="store_true")
    once = commands.add_parser("once"); once.add_argument("goal_id")
    once.add_argument("--json", action="store_true")
    next_run = commands.add_parser("next"); next_run.add_argument("goal_id")
    next_run.add_argument("--json", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("goal_id", nargs="?")
    status.add_argument("--history", action="store_true",
                        help="show bounded terminal-goal history")
    status.add_argument("--limit", type=int, default=5,
                        help="number of recent history records (1-100)")
    status.add_argument("--raw", action="store_true",
                        help="show the complete stored payload for explicit audit work")
    status.add_argument("--json", action="store_true",
                        help="render the compact projection as JSON")
    approve = commands.add_parser("approve"); approve.add_argument("goal_id"); approve.add_argument("--note", default="")
    approve.add_argument("--scope", choices=("per_action", "per_run", "everything_approved"),
                         help="approval mode for this Goal: approve now AND record the policy "
                              "(per_run/everything_approved), or just approve (per_action/none)")
    approve.add_argument("--json", action="store_true")
    directive = commands.add_parser("directive", help="durable owner operating direction")
    directive_commands = directive.add_subparsers(dest="directive_command", required=True)
    directive_add = directive_commands.add_parser("add")
    directive_add.add_argument("--text", required=True)
    directive_add.add_argument("--goal")
    directive_add.add_argument("--scope", choices=("company", "goal"), default="company")
    directive_add.add_argument("--json", action="store_true")
    directive_list = directive_commands.add_parser("list")
    directive_list.add_argument("--goal")
    directive_list.add_argument("--json", action="store_true")
    directive_retire = directive_commands.add_parser("retire")
    directive_retire.add_argument("directive_id")
    directive_retire.add_argument("--json", action="store_true")
    for name in ("pause", "resume", "abandon"):
        item = commands.add_parser(name); item.add_argument("goal_id")
        item.add_argument("--json", action="store_true")
    retry = commands.add_parser("retry"); retry.add_argument("goal_id")
    retry.add_argument("--json", action="store_true")
    report = commands.add_parser("report"); report.add_argument("goal_id"); report.add_argument("--events", type=int, default=10); report.add_argument("--json", action="store_true")
    evidence = commands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    reply = evidence_commands.add_parser("reply"); reply.add_argument("goal_id"); reply.add_argument("--recipient", required=True); reply.add_argument("--note", default="")
    reply.add_argument("--json", action="store_true")
    add = evidence_commands.add_parser("add"); add.add_argument("goal_id"); add.add_argument("--kind", required=True); add.add_argument("--source", required=True); add.add_argument("--payload", default="{}"); add.add_argument("--validity")
    add.add_argument("--json", action="store_true")
    change = commands.add_parser("change")
    change_commands = change.add_subparsers(dest="change_command", required=True)
    complete = change_commands.add_parser("complete"); complete.add_argument("task_id"); complete.add_argument("--passed", action="store_true"); complete.add_argument("--deployed", action="store_true"); complete.add_argument("--result", default="{}")
    complete.add_argument("--json", action="store_true")
    runner = commands.add_parser("runner")
    runner_commands = runner.add_subparsers(dest="runner_command", required=True)
    tick = runner_commands.add_parser("tick"); tick.add_argument("goal_id", nargs="?"); tick.add_argument("--max-advances", type=int, default=100)
    watch = runner_commands.add_parser("watch"); watch.add_argument("goal_id", nargs="?"); watch.add_argument("--interval", type=float, default=2.0); watch.add_argument("--max-ticks", type=int)
    wake = runner_commands.add_parser("wake", help="sleep and emit deterministic Director wake events for one Goal")
    wake.add_argument("goal_id")
    wake.add_argument("--every", type=float, default=600.0,
                      help="seconds between wake events (default: 600)")
    wake.add_argument("--instruction", default="Continue the Goal cycle and handle its next actionable work.")
    wake.add_argument("--at", help="one wake at an ISO-8601 timestamp; then exit")
    wake.add_argument("--max-wakes", type=int)
    start = runner_commands.add_parser("start"); start.add_argument("--interval", type=float, default=2.0)
    start.add_argument("--json", action="store_true")
    runner_commands.add_parser("enable")
    stop = runner_commands.add_parser("stop")
    stop.add_argument("--json", action="store_true")
    status = runner_commands.add_parser("status")
    status.add_argument("--json", action="store_true")
    notifications = commands.add_parser("notifications")
    notification_commands = notifications.add_subparsers(dest="notification_command", required=True)
    listed = notification_commands.add_parser("list"); listed.add_argument("--status", choices=("pending", "delivered")); listed.add_argument("--limit", type=int, default=100)
    listed.add_argument("--json", action="store_true")
    acknowledge = notification_commands.add_parser("ack"); acknowledge.add_argument("notification_id")
    acknowledge.add_argument("--json", action="store_true")
    dispatch = commands.add_parser("dispatch", help="record and read dispatch retry attempts (Watchdog v2 retry ledger)")
    dispatch_commands = dispatch.add_subparsers(dest="dispatch_command", required=True)
    record = dispatch_commands.add_parser("record")
    record.add_argument("goal_id")
    record.add_argument("--run", required=True)
    record.add_argument("--attempt", type=int, required=True)
    record.add_argument("--status", required=True)
    record.add_argument("--next-retry-at")
    record.add_argument("--error")
    record.add_argument("--json", action="store_true")
    dispatch_list = dispatch_commands.add_parser("list")
    dispatch_list.add_argument("--goal")
    dispatch_list.add_argument("--limit", type=int, default=20)
    dispatch_list.add_argument("--json", action="store_true")
    tasks = commands.add_parser("tasks", help="list durable employee work orders")
    tasks.add_argument("work_order_id", nargs="?")
    tasks.add_argument("--status", choices=("active", "open", "claimed", "done", "cancelled"),
                       default="active")
    tasks.add_argument("--goal")
    tasks.add_argument("--limit", type=int, default=50)
    tasks.add_argument("--json", action="store_true")
    tasks.add_argument("--claim", metavar="WORKER_ID")
    tasks.add_argument("--complete", metavar="WORKER_ID")
    tasks.add_argument("--evidence", default="[]",
                       help="JSON array of {kind,source?,payload?,validity?}")
    evals = commands.add_parser("eval", help="reusable LLM-as-judge eval suites")
    eval_commands = evals.add_subparsers(dest="eval_command", required=True)
    eval_list = eval_commands.add_parser("list")
    eval_list.add_argument("--json", action="store_true")
    eval_run = eval_commands.add_parser("run")
    eval_run.add_argument("suite_id")
    eval_run.add_argument("--payload", required=True,
                          help="path to the payload JSON (e.g. campaign-approved.json)")
    eval_run.add_argument("--judge-response",
                          help="path to a JSON document of judge verdicts; "
                               "without it the command renders the request and reads verdicts from stdin")
    eval_run.add_argument("--goal", help="goal_id to attach the eval_report evidence to")
    eval_run.add_argument("--validity", choices=("business", "technical_only"),
                          help="override the suite's recorded evidence validity")
    eval_run.add_argument("--json", action="store_true")
    return parser


def scalar(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _runtime_mode(args) -> str | None:
    """How the CLI should open the company database, if at all.

    None: no Runtime (catalog, package inspection, runner process control).
    read: query-only snapshot. write: an explicit mutating command.
    """

    if args.command in {"departments", "catalog", "strategy", "init", "add",
                        "refresh", "agent"}:
        return None
    if args.command in {"department", "workgroup"}:
        return None
    if args.command == "runner" and args.runner_command in {"status", "start", "stop", "enable"}:
        return None
    if args.command == "status":
        return "read"
    if args.command == "report":
        return "read"
    if args.command == "goal" and getattr(args, "goal_command", None) in {"list", "show"}:
        return "read"
    if args.command == "notifications" and args.notification_command == "list":
        return "read"
    if args.command == "dispatch" and args.dispatch_command == "list":
        return "read"
    if args.command == "tasks" and not getattr(args, "claim", None) and not getattr(args, "complete", None):
        return "read"
    if args.command == "eval" and args.eval_command == "list":
        return None
    return "write"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv or "-V" in argv:
        # Checked before argparse: required subcommands would reject a bare
        # --version otherwise.
        from .runtime.config import VERSION
        print(f"spielos {VERSION}")
        return 0
    if not argv:
        # Bare `spielos`: the destination folder is the product. In a home,
        # show company state; in a folder without a spine, onboard it. The
        # source checkout is exempt (dev mode keeps the parser help).
        from .runtime.paths import find_project_root, package_vendored_root

        vendored = package_vendored_root()
        in_source_repo = (vendored is not None
                          and "site-packages" not in str(vendored))
        root = find_project_root()
        if not in_source_repo:
            if (root / ".agents" / "company").is_dir():
                runtime = Runtime(DEFAULT_DB, readonly=True)
                service = RunnerService(PROJECT_ROOT,
                                        Path(DEFAULT_DB)).status()
                snapshot = runtime.company_snapshot(5)
                snapshot["automation"] = {
                    "enabled": service["enabled"], "running": service["running"],
                    "pid": service["pid"], "started_at": service.get("started_at"),
                }
                print(render_status(snapshot))
                return 0
            from .runtime.onboard import run_init
            return run_init()
    args = build_parser().parse_args(argv)
    mode = _runtime_mode(args)
    runtime = Runtime(args.db, readonly=(mode == "read")) if mode else None
    exit_code = 0
    try:
        if args.command == "init":
            from .runtime.onboard import run_init
            return run_init(dir=args.dir, force=args.force,
                            minimal=not args.all_departments,
                            departments=args.department or None,
                            assume_yes=args.yes, as_json=args.json)
        if args.command == "add":
            from .runtime.export import add_department
            receipt = add_department(args.source, force=args.force,
                                     home=args.dir)
            print(json.dumps(receipt, indent=2))
            return 0
        if args.command == "department" and args.department_command == "export":
            from .runtime.export import export_department
            receipt = export_department(args.id, Path(args.out).expanduser())
            print(json.dumps(receipt, indent=2))
            return 0
        if args.command == "workgroup":
            from .runtime.workgroup_install import install_workgroup, validate_workgroup_spec
            if args.workgroup_command == "list":
                from .runtime.registry import workgroups
                output = [{"id": group.id, "workers": list(group.agent_ids),
                           "workflows": [flow.id for flow in group.workflows]}
                          for group in workgroups().values()]
            else:
                payload = (json.loads(Path(args.file).read_text()) if args.file else
                           json.loads(args.spec) if args.spec else None)
                if not isinstance(payload, dict):
                    raise ValueError("provide --spec JSON or --file path")
                defects = validate_workgroup_spec(payload)
                if args.workgroup_command == "validate":
                    output = {"ok": not defects, "defects": defects}
                else:
                    from .runtime.paths import package_vendored_root, selected_project_root, validate_home_destination
                    selected = validate_home_destination(selected_project_root(args.dir))
                    company_home = selected / ".agents" / "company"
                    root = (selected / "company" / "workgroups" if not company_home.is_dir()
                            and package_vendored_root() == selected else company_home / "workgroups")
                    if not root.parent.is_dir():
                        raise ValueError(f"no harness home at {selected}; run `spielos init --dir {selected}` first")
                    output = install_workgroup(payload, root=root, force=args.force)
            print(json.dumps(output, indent=2))
            return 0
        if args.command == "refresh":
            from .runtime.export import refresh_home
            receipt = refresh_home(force=True, target=args.dir)
            if getattr(args, "json", False):
                print(json.dumps(receipt, indent=2))
            else:
                print(render_refresh(receipt))
            return 0
        if args.command == "agent" and args.agent_command == "compile":
            from .runtime.agent_compile import compile_agent
            receipt = compile_agent(args.department, args.workflow,
                                    args.name, force=args.force, home=args.dir)
            print(json.dumps(receipt, indent=2))
            return 0
        if args.command == "departments":
            output = [{"id": key, "version": value.version, "description": value.description,
                       "goal_schema": value.goal_schema}
                      for key, value in departments().items()]
        elif args.command == "catalog":
            from .runtime.catalog import catalog
            output = catalog()
        elif args.command == "strategy":
            from .runtime.models import Goal
            from .runtime.strategy import (
                load_strategy_kernel, select_strategy_context, strategy_kernel_summary)
            kernel = load_strategy_kernel()
            if args.topic or args.scope or args.layer:
                synthetic = Goal(
                    id="strategy-view", name="Inspect canonical strategy",
                    owner_id="director", metric="strategy_state", operator="eq",
                    target="current", deadline=None, parent_id=None,
                    goal_status="active", config={"strategy_context": {
                        "topics": args.topic, "scopes": args.scope or ["director"],
                        "layers": args.layer or ["model", "policy", "constitution"],
                    }})
                output = select_strategy_context(
                    synthetic, kernel, max_sections=args.max_sections)
            else:
                output = strategy_kernel_summary(kernel)
        elif args.command == "department":
            from .runtime.install import (
                install_department, normalize_department_spec, validate_department_spec)
            from .runtime.package import package_spec, validate_package
            if args.department_command == "list":
                output = []
                for key, value in sorted(departments().items()):
                    defects = validate_package(value)
                    output.append({**package_spec(value), "package_defects": defects,
                                   "lego": not defects})
            else:
                if args.file:
                    payload = json.loads(Path(args.file).read_text())
                elif args.spec:
                    payload = json.loads(args.spec)
                else:
                    raise ValueError("provide --spec JSON or --file path")
                if not isinstance(payload, dict):
                    raise ValueError("department_spec must be a JSON object")
                if args.department_command == "validate":
                    normalized = normalize_department_spec(
                        payload, default_id=args.id)
                    defects = validate_department_spec(normalized)
                    output = {"ok": not defects, "defects": defects, "package": normalized}
                else:
                    from .runtime.paths import (
                        package_vendored_root, selected_project_root,
                        validate_home_destination)
                    selected = validate_home_destination(
                        selected_project_root(args.dir))
                    company_home = selected / ".agents" / "company"
                    source_root = package_vendored_root()
                    source_checkout = (not company_home.is_dir()
                                       and source_root == selected)
                    if source_checkout:
                        company_home = selected / "company"
                    if not company_home.is_dir():
                        raise ValueError(
                            f"no harness home at {selected}; "
                            f"run `spielos init --dir {selected}` first")
                    install_root = (None if source_checkout else
                                    company_home / "departments")
                    installed_agents_root = (None if source_checkout else
                                              company_home / "agents" / "installed")
                    output = install_department(
                        payload, default_id=args.id, default_version=args.version,
                        force=args.force, root=install_root,
                        agents_root=installed_agents_root)
        elif args.command == "goal" and args.goal_command == "create":
            config = json.loads(args.config)
            hypothesis = json.loads(args.hypothesis)
            controlled = json.loads(args.controlled)
            changed = json.loads(args.changed)
            if not isinstance(config, dict):
                raise ValueError("--config must be a JSON object")
            if args.supports:
                config["supports_goal_ids"] = list(dict.fromkeys(args.supports))
            if args.priority:
                config["priority"] = args.priority
            output = runtime.create_goal(name=args.name, owner_id=args.owner, metric=args.metric,
                operator=args.operator, target=scalar(args.target), deadline=args.deadline,
                parent_id=args.parent, config=config, goal_id=args.id, run_type=args.run_type,
                hypothesis=hypothesis or None, controlled_variables=controlled, changed_variables=changed,
                evidence_validity=args.validity, parent_run_id=args.parent_run,
                triggered_by_run_id=args.triggered_by, resume_run_id=args.resume_run)
        elif args.command == "goal" and args.goal_command == "list":
            output = runtime.store.goal_summaries(limit=100)
        elif args.command == "goal" and args.goal_command == "link":
            output = runtime.link_support(args.goal_id, args.supports)
        elif args.command == "goal":
            output = runtime.status(args.goal_id)
        elif args.command == "once":
            output = runtime.once(args.goal_id)
        elif args.command == "next":
            runtime.next(args.goal_id)
            Runner(runtime).tick(args.goal_id)
            output = runtime.status(args.goal_id)
        elif args.command == "status":
            if args.goal_id and args.history:
                raise ValueError("status accepts either GOAL_ID or --history, not both")
            if args.raw:
                output = runtime.status(args.goal_id) if args.goal_id else runtime.list_goals()
            elif args.goal_id:
                output = runtime.goal_summary(args.goal_id)
            elif args.history:
                output = runtime.goal_history(args.limit)
            else:
                service = RunnerService(PROJECT_ROOT, Path(args.db)).status()
                output = runtime.company_snapshot(args.limit)
                output["automation"] = {
                    "enabled": service["enabled"], "running": service["running"],
                    "pid": service["pid"], "started_at": service.get("started_at"),
                }
            if not args.raw and not args.json:
                print(render_status(output, history=args.history))
                return 0
        elif args.command == "approve":
            runtime.approve(args.goal_id, args.note, scope=args.scope)
            output = runtime.status(args.goal_id)
        elif args.command == "directive":
            if args.directive_command == "add":
                scope = "goal" if args.goal else args.scope
                output = runtime.store.record_directive(
                    args.text, scope=scope, goal_id=args.goal)
            elif args.directive_command == "retire":
                output = runtime.store.retire_directive(args.directive_id)
            else:
                goal_ids = (args.goal,) if args.goal else ()
                output = list(runtime.store.directives(goal_ids=goal_ids, limit=100))
        elif args.command in ("pause", "resume", "abandon"):
            statuses = {"pause": GoalStatus.PAUSED, "resume": GoalStatus.ACTIVE, "abandon": GoalStatus.ABANDONED}
            output = runtime.set_goal_status(args.goal_id, statuses[args.command])
        elif args.command == "retry":
            output = runtime.retry(args.goal_id)
        elif args.command == "evidence":
            if args.evidence_command == "reply":
                runtime.add_evidence(args.goal_id, kind="reply", source="manual_inbox_confirmation",
                                     payload={"recipient": args.recipient, "note": args.note},
                                     validity="technical_only")
            else:
                runtime.add_evidence(args.goal_id, kind=args.kind, source=args.source,
                                     payload=json.loads(args.payload), validity=args.validity)
            Runner(runtime).tick(args.goal_id)
            output = runtime.status(args.goal_id)
        elif args.command == "change":
            output = runtime.complete_change(args.task_id, passed=args.passed,
                                             deployed=args.deployed, result=json.loads(args.result))
            Runner(runtime).tick(output["goal"]["id"])
            output = runtime.status(output["goal"]["id"])
        elif args.command == "runner":
            runner = Runner(runtime)
            if args.runner_command == "tick":
                output = runner.tick(args.goal_id, args.max_advances)
            elif args.runner_command == "watch":
                # The daemon reports pending attention but never acknowledges
                # it. Only a host that actually displays an exact id may mark
                # that notification delivered.
                from .runtime.notifications import pending_notifications
                for result in runner.watch(args.interval, args.goal_id, args.max_ticks):
                    pending = len(pending_notifications(runtime.store))
                    print(json.dumps({**result, "notifications_pending": pending},
                                     ensure_ascii=False, default=str), flush=True)
                return 0
            elif args.runner_command == "wake":
                for event in runner.wake(
                        args.goal_id, every_seconds=args.every,
                        instruction=args.instruction, at=args.at,
                        max_wakes=args.max_wakes,
                        runner_status=lambda: RunnerService(PROJECT_ROOT, Path(args.db)).status()):
                    print(json.dumps(event, ensure_ascii=False, default=str), flush=True)
                return 0
            else:
                service = RunnerService(PROJECT_ROOT, Path(args.db))
                if args.runner_command == "start":
                    output = service.start(args.interval)
                elif args.runner_command == "stop":
                    output = service.stop()
                elif args.runner_command == "enable":
                    output = service.enable()
                else:
                    output = service.status()
        elif args.command == "notifications":
            if args.notification_command == "list":
                output = runtime.store.notifications(args.status, args.limit)
            else:
                output = runtime.store.acknowledge_notification(args.notification_id)
        elif args.command == "dispatch":
            if args.dispatch_command == "record":
                output = runtime.store.record_dispatch_retry(
                    args.goal_id, args.run, args.attempt, args.status,
                    first_error=args.error, next_retry_at=args.next_retry_at)
            else:
                output = runtime.store.dispatch_retries(
                    goal_id=args.goal, limit=args.limit)
        elif args.command == "tasks":
            if args.claim or args.complete:
                if not args.work_order_id:
                    raise ValueError("tasks --claim/--complete requires WORK_ORDER_ID")
                if args.claim and args.complete:
                    raise ValueError("choose either --claim or --complete")
                if args.claim:
                    output = runtime.claim_work_order(args.work_order_id, args.claim)
                else:
                    evidence = json.loads(args.evidence)
                    if not isinstance(evidence, list):
                        raise ValueError("--evidence must be a JSON array")
                    output = runtime.complete_work_order(
                        args.work_order_id, args.complete, evidence)
                    output = {
                        "work_order": runtime.store.work_order(args.work_order_id),
                        "goal": runtime.status(output["work_order"]["goal_id"]),
                    }
            elif args.work_order_id:
                output = runtime.store.work_order(args.work_order_id)
            else:
                output = runtime.store.work_orders(
                    status=args.status, goal_id=args.goal, limit=args.limit)
            if not args.json and not args.work_order_id:
                print(render_tasks(output))
                return 0
        elif args.command == "eval":
            from .evals import (
                get_suite, render_request, report_to_evidence, run_suite,
                suite_spec, suites as installed_eval_suites,
            )
            if args.eval_command == "list":
                output = {"evals": [suite_spec(suite) for suite in
                                     sorted(installed_eval_suites().values(),
                                            key=lambda item: item.id)]}
            else:
                suite = get_suite(args.suite_id)
                payload = json.loads(Path(args.payload).read_text())
                if not isinstance(payload, dict):
                    raise ValueError("eval payload must be a JSON object")
                request = render_request(suite, payload)
                if args.judge_response:
                    verdicts_raw = json.loads(Path(args.judge_response).read_text())
                else:
                    # Interact: render the structured request, then read the
                    # agent-written verdict document from stdin.
                    print(json.dumps(request, indent=2, ensure_ascii=False))
                    print("\nJudge the request above. Paste the verdict JSON "
                          "document, then end input (Ctrl-D / EOF).",
                          file=sys.stderr)
                    raw = sys.stdin.read()
                    if not raw.strip():
                        raise ValueError(
                            "no judge response received; re-run with "
                            "--judge-response <path> or paste verdict JSON on stdin")
                    verdicts_raw = json.loads(raw)
                report = run_suite(suite, payload, verdicts_raw,
                                   validity=args.validity)
                evidence_id = None
                if args.goal:
                    state = runtime.add_evidence(
                        args.goal, kind="eval_report", source=f"evals:{suite.id}",
                        payload=report_to_evidence(report), validity=report.validity)
                    evidence_id = (state["evidence"] or [{}])[-1].get("id")
                output = {"request": request, "report": report_to_evidence(report),
                          "goal": args.goal, "evidence_id": evidence_id}
                # A failing eval is a failed gate: exit non-zero so pipelines
                # (and the acceptance test) can rely on the exit code.
                exit_code = 0 if report.overall else 1
        else:
            state = runtime.status(args.goal_id)
            output = {**state, "events": runtime.store.events(args.goal_id, args.events),
                      "memory": runtime.store.memories(state["goal"]["owner_id"], args.goal_id)}
            if not args.json:
                print(render_report(output))
                return 0
        if getattr(args, "json", False):
            print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
        else:
            print(_render_default(args, output))
        return exit_code
    except (KeyError, RuntimeError, ValueError, json.JSONDecodeError,
            sqlite3.OperationalError) as exc:
        message = str(exc).strip("'")
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, indent=2), file=sys.stderr)
        else:
            print(f"company: {message}", file=sys.stderr)
        return 1


def render_report(state):
    goal, cycle, run = state["goal"], state["cycle"], state["run"]
    latest = state.get("latest_result") or {}
    evaluation = state.get("evaluation") or latest.get("evaluation") or {}
    evidence = state.get("evidence") or latest.get("evidence") or []
    decisions = state.get("decisions") or latest.get("decisions") or []
    evaluated_run = latest.get("run") or run
    metrics = evaluation.get("metrics") or {}
    lines = [f"# Goal report: {goal['name']}", "",
             f"- Goal: `{goal['metric']} {goal['operator']} {goal['target']}`",
             f"- Goal status: `{goal['goal_status']}`",
             f"- Run: `{evaluated_run['id']}` · `{evaluated_run['run_type']}` · owner `{evaluated_run['owner_id']}@{evaluated_run['owner_version']}`",
             f"- Runtime: `{cycle['stage']}.{cycle['step']}` · `{cycle['run_status']}`",
             f"- Evidence validity: `{evaluated_run['evidence_validity']}`"]
    if evaluated_run.get("contamination_reason"):
        lines.append(f"- Contamination: {evaluated_run['contamination_reason']}")
    if metrics:
        lines += ["", "## Metrics"] + [f"- {key}: {value}" for key, value in metrics.items()]
    if evidence:
        lines += ["", "## Evidence"] + [f"- `{item['kind']}` via {item['source']} ({item['validity']})"
                                          for item in evidence]
    if decisions:
        lines += ["", "## Decisions"] + [f"- `{item['decision_type']}`: {item['rationale']}"
                                           for item in decisions]
    if evaluation:
        lines += ["", "## Evaluation", f"- Verdict: `{evaluation['verdict']}`",
                  f"- Goal met: `{bool(evaluation['goal_met'])}`"]
        if evaluation.get("next_experiment"):
            lines += ["", "## Proposed next run"] + [
                f"- {key}: {value}" for key, value in evaluation["next_experiment"].items()]
            lines += ["", "## Required action",
                      "The next valid run starts automatically; guarded actions still need approval."]
    if cycle["run_status"] == "awaiting_approval":
        preview = cycle.get("data", {}).get("action_result", {}).get("preview_path")
        lines += ["", "## Required action", "Review and approve the prepared action."]
        if preview:
            lines.append(f"Preview: `{preview}`")
    return "\n".join(lines) + "\n"


def _goal_line(item):
    line = (f"- {item['name']} (`{item['id']}`) · {item['owner_id']} · "
            f"{item['goal_status']} / {item['run_status']} · "
            f"{item['stage']}.{item['step']}")
    if item.get("goal_status") in {"active", "proposed"} and item.get("why_next"):
        line += f"\n  {item['why_next']}"
    return line


def _goal_hierarchy_lines(items):
    """Compact one-parent tree; semantic support edges stay in the JSON view."""

    by_parent = {}
    ids = {item["id"] for item in items}
    for item in items:
        by_parent.setdefault(item.get("parent_id"), []).append(item)
    roots = [item for item in items if item.get("parent_id") not in ids]
    lines = []

    def visit(item, depth):
        rendered = _goal_line(item).splitlines()
        prefix = "  " * depth
        lines.append(prefix + rendered[0])
        lines.extend(prefix + line for line in rendered[1:])
        for child in by_parent.get(item["id"], []):
            visit(child, depth + 1)

    for root in roots:
        visit(root, 0)
    return lines


def _work_order_line(item):
    accepts = ", ".join(item.get("accepts_evidence") or []) or "capability handoff"
    goal_name = item.get("goal_name") or item.get("goal_id")
    line = (f"- `{item['id']}` · {item['employee_id']} · {goal_name} (`{item['goal_id']}`) · "
            f"need {item['needed']} × [{accepts}]")
    if item.get("why_next"):
        line += f"\n  {item['why_next']}"
    brief = item.get("brief") or {}
    if brief.get("message"):
        line += f"\n  {brief['message']}"
    return line


def render_tasks(items):
    lines = [f"# Work orders ({len(items)})", ""]
    if not items:
        lines.append("- None.")
    else:
        lines.extend(_work_order_line(item) for item in items)
    lines += ["", "Any host can pick one up, write accepted evidence, then `company retry GOAL_ID`."]
    return "\n".join(lines) + "\n"


def render_status(value, history=False):
    """Human-first status output that stays small as the audit ledger grows."""

    if isinstance(value, list):
        lines = ["# Goal history", ""]
        lines.extend(_goal_line(item) for item in value)
        return "\n".join(lines + (["", "No matching history."] if not value else [])) + "\n"
    if "goal" in value:
        item = value["goal"]
        lines = [f"# {item['name']}", "",
                 f"- Goal: `{item['id']}`",
                 f"- Owner: `{item['owner_id']}`",
                 f"- Outcome: `{item['metric']} {item['operator']} {item['target']}`",
                 f"- Goal status: `{item['goal_status']}`",
                 f"- Current run: `{item['run_id']}` · `{item['run_type']}` · `{item['run_status']}`",
                 f"- Runtime: `{item['stage']}.{item['step']}`",
                 f"- Evidence: `{item['evidence_count']}` item(s) · validity `{item['evidence_validity']}`",
                 f"- Updated: `{item['runtime_updated_at']}`"]
        if item.get("why_next"):
            lines.append(f"- Why/next: `{item['why_next']}`")
        if item.get("verdict"):
            lines.append(f"- Latest evaluation: `{item['verdict']}` · goal met `{item['goal_met']}`")
        work_orders = value.get("work_orders") or []
        if work_orders:
            lines += ["", f"## Open work orders ({len(work_orders)})"]
            lines.extend(_work_order_line(item) for item in work_orders)
        if value["attention"]:
            lines += ["", "## Needs attention"]
            for attention in value["attention"]:
                required = attention.get("required_user_action") or attention.get("message") or "Review"
                lines.append(f"- `{attention['kind']}`: {required}")
                interaction = attention.get("approval_interaction") or {}
                if interaction:
                    lines.extend([
                        f"  - Question: {interaction['question']}",
                        f"  - Action: {interaction['action']}",
                        f"  - Artifact: {interaction.get('artifact') or 'none'}",
                        f"  - Destination: {interaction['destination']}",
                        f"  - Scope: {interaction['scope']}",
                        f"  - Risk: {interaction['risk']}",
                        f"  - Consequence: {interaction['consequence']}",
                        f"  - Fallback: `{interaction['fallback_command']}`",
                    ])
        elif not work_orders and value["unread_results"]:
            lines += ["", "## Unread result",
                      f"- `{value['unread_results'][0]['kind']}` is ready to report."]
        elif not work_orders:
            lines += ["", "No action required."]
        return "\n".join(lines) + "\n"

    automation = value["automation"]
    if automation.get("running"):
        started = f", started {automation['started_at']}" if automation.get("started_at") else ""
        header = (f"Local runner: **running** (pid {automation['pid']}{started}); "
                  "goals only advance while this machine is on.")
    else:
        header = ("Local runner: **paused** - start with `company runner start`; "
                  "goals only advance while this machine is on.")
    lines = ["# SpielOS company", "", header, ""]
    focus = value.get("focus_goal")
    lines.append("## Focus now")
    if focus:
        lines.append(_goal_line(focus))
        if focus.get("why_next"):
            lines += ["", "## Why", f"- {focus['why_next']}"]
    else:
        lines.append("- No active company outcome.")
    attention = value["attention"]
    lines += ["", f"## Need from you ({len(attention)})"]
    if attention:
        for item in attention:
            required = item.get("required_user_action") or item.get("message") or "Review"
            lines.append(f"- `{item['kind']}` · {item['name']} (`{item['goal_id']}`): {required}")
    else:
        lines.append("- Nothing requires action.")
    work_orders = value.get("work_orders") or []
    lines += ["", f"## Moving · Open work orders ({len(work_orders)})"]
    if work_orders:
        lines.extend(_work_order_line(item) for item in work_orders)
    else:
        lines.append("- None.")
    active = value["active_goals"]
    lines += ["", f"## Active goals ({len(active)}) · hierarchy"]
    lines.extend(_goal_hierarchy_lines(active)) if active else lines.append("- None.")
    proposed = value.get("proposed_goals") or []
    if proposed:
        lines += ["", f"## Proposed / deferred ({len(proposed)})"]
        lines.extend(_goal_line(item) for item in proposed)
    if value["paused_goals"]:
        lines += ["", f"## Paused ({len(value['paused_goals'])})"]
        lines.extend(_goal_line(item) for item in value["paused_goals"])
    if value["unread_results"]:
        lines += ["", f"## Unread results ({len(value['unread_results'])})"]
        lines.extend(f"- `{item['kind']}` · {item['name']} (`{item['goal_id']}`)"
                     + (f": {item['why_next']}" if item.get("why_next") else "")
                     for item in value["unread_results"])
    memories = value.get("recent_memory") or []
    if memories:
        lines += ["", "## Learned"]
        lines.extend(f"- {item['claim']}" for item in memories)
    directives = value.get("directives") or []
    if directives:
        lines += ["", "## Company direction"]
        lines.extend(f"- {item['text']}" for item in directives)
    recent = value["recent_results"]
    lines += ["", f"## Recent results ({len(recent)})"]
    lines.extend(_goal_line(item) for item in recent) if recent else lines.append("- None.")
    counts = value["counts"]
    terminal = counts["achieved"] + counts["abandoned"] + counts["expired"]
    lines += ["", f"History: {terminal} terminal goal(s), {counts['total']} total. ",
              "Use `company status --history --limit N` for more or `--raw` for the full audit payload."]
    return "\n".join(lines) + "\n"


# ---- Card-style renders (default output for every user-facing command) ----


def _result_message(item):
    """The human message of a notification payload, when present."""
    payload = item.get("payload") or {}
    result = payload.get("result")
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("message")
    return None


def _render_default(args, output) -> str:
    """Human-first card render for the command that just ran.

    Commands without a dedicated renderer (catalog, department install,
    runner tick, tasks WORK_ORDER_ID, status --raw, ...) keep the raw JSON
    projection: they are machine views or runtime plumbing.
    """
    command = args.command
    if command == "refresh":
        return render_refresh(output)
    if command == "departments":
        return render_departments(output)
    if command == "strategy":
        return render_strategy(output)
    if command == "department" and args.department_command == "list":
        return render_department_packages(output)
    if command == "goal":
        if args.goal_command == "create":
            return render_goal_created(output)
        if args.goal_command == "list":
            return render_goal_list(output)
        return render_goal_state(output["goal"]["name"], output)
    if command == "notifications":
        if args.notification_command == "ack":
            return render_notification_ack(output)
        return render_notifications_list(output)
    if command == "dispatch":
        if args.dispatch_command == "record":
            return render_dispatch_record(output)
        return render_dispatch_list(output)
    if command == "evidence":
        kind = "reply" if args.evidence_command == "reply" else args.kind
        return render_goal_state(f"Evidence added: {kind}", output)
    if command == "eval":
        if args.eval_command == "list":
            return render_evals_list(output)
        return render_evals_run(output)
    if command == "change":
        return render_goal_state(f"Change complete: {output['goal']['name']}", output)
    if command == "runner":
        titles = {"start": "Runner started", "stop": "Runner stopped",
                  "enable": "Runner enabled", "status": "Runner status"}
        return render_runner(titles[args.runner_command], output)
    titles = {"pause": "Paused", "resume": "Resumed", "abandon": "Abandoned",
              "approve": "Approved", "retry": "Retried", "once": "Run once",
              "next": "Next run started"}
    if command in titles:
        return render_goal_state(f"{titles[command]}: {output['goal']['name']}", output)
    return json.dumps(output, indent=2, ensure_ascii=False, default=str)


def render_goal_state(title, value):
    """Card for a full runtime.status() projection (goal/show and transitions)."""
    goal, cycle, run = value["goal"], value["cycle"], value["run"]
    lines = [f"# {title}", "",
             f"- Goal: `{goal['id']}`",
             f"- Owner: `{goal['owner_id']}`",
             f"- Outcome: `{goal['metric']} {goal['operator']} {goal['target']}`",
             f"- Goal status: `{goal['goal_status']}`",
             f"- Current run: `{run['id']}` · `{run['run_type']}` · `{run['status']}`",
             f"- Runtime: `{cycle['stage']}.{cycle['step']}` · `{cycle['run_status']}`",
             f"- Evidence: `{len(value.get('evidence') or [])}` item(s)"]
    if run.get("evidence_validity"):
        lines.append(f"- Evidence validity: `{run['evidence_validity']}`")
    pending = [item for item in (value.get("pending_notifications") or [])
               if item.get("status") == "pending"]
    if pending:
        lines.append(f"- Pending notifications: `{len(pending)}`")
    return "\n".join(lines) + "\n"


def render_goal_created(value):
    """Card for the goal create confirmation (a raw goal row)."""
    lines = [f"# Goal created: {value['name']}", "",
             f"- Goal: `{value['id']}`",
             f"- Owner: `{value['owner_id']}`",
             f"- Outcome: `{value['metric']} {value['operator']} {value['target']}`",
             f"- Status: `{value['goal_status']}`"]
    alignment = (value.get("config") or {}).get("alignment")
    if alignment:
        lines.append(f"- Alignment: `{alignment.get('judgment')}`")
    return "\n".join(lines) + "\n"


def render_goal_list(items):
    """Card for `company goal list`."""
    lines = [f"# Goals ({len(items)})", ""]
    if items:
        lines.extend(_goal_line(item) for item in items)
    else:
        lines.append("- None.")
    lines += ["", "Create goals with `company goal create`; inspect one with `company goal show GOAL_ID`."]
    return "\n".join(lines) + "\n"


def _notification_line(item):
    message = _result_message(item)
    line = (f"- `{item['id']}` · `{item['kind']}` · {item['goal_id']} · "
            f"status `{item['status']}`")
    if item.get("why_next"):
        line += f"\n  {item['why_next']}"
    if message:
        line += f"\n  {message}"
    return line


def render_notifications_list(items):
    pending = sum(1 for item in items if item.get("status") == "pending")
    lines = [f"# Notifications ({len(items)}, {pending} pending)", ""]
    if items:
        lines.extend(_notification_line(item) for item in items)
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def render_notification_ack(item):
    lines = [f"# Notification acknowledged", "",
             f"- Notification: `{item['id']}`",
             f"- Kind: `{item['kind']}`",
             f"- Goal: `{item['goal_id']}`",
             f"- Status: `{item['status']}`"]
    return "\n".join(lines) + "\n"


def render_refresh(value):
    """Card for `company refresh` — the update step after `pipx upgrade`."""
    lines = ["# SpielOS home refreshed", "",
             f"- Refreshed files: `{value.get('refreshed_files', 0)}`",
             "- Preserved: strategy, assets, departments, installed agents, "
             "config.user.json, .spielos/ state"]
    lines += ["", "Confirm with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents "
              "python3 -B -m company status`."]
    return "\n".join(lines) + "\n"


def render_departments(items):
    lines = [f"# Departments ({len(items)})", ""]
    if items:
        for item in items:
            lines.append(f"- `{item['id']}` v{item['version']} — {item['description']}")
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def render_department_packages(items):
    lines = [f"# Department packages ({len(items)})", ""]
    if not items:
        lines.append("- None.")
    for item in items:
        line = f"- `{item['id']}` v{item['version']} — {item['description']}"
        if item.get("lego"):
            line += " · installable Lego package"
        defects = item.get("package_defects") or []
        if defects:
            line += f"\n  package defects: {', '.join(defects)}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def render_strategy(value):
    """Card for the Strategy Kernel summary or a bounded context selection."""
    if "current_intent" in value:
        intent = value.get("current_intent") or {}
        lines = [f"# Strategy context: {intent.get('name') or intent.get('goal_id')}", "",
                 f"- State hash: `{value.get('state_hash')}`",
                 f"- Sections: `{len(value.get('sections') or [])}` of `{value.get('section_limit')}`",
                 f"- Memory separate: `{value.get('memory_separate')}`",
                 f"- Strategy mutable: `{value.get('strategy_mutable')}`",
                 ""]
        for section in value.get("sections") or []:
            lines.append(f"- `{section['id']}` — {section['heading']} (`{section['source']}`)")
    else:
        lines = [f"# Strategy kernel", "",
                 f"- Schema version: `{value.get('schema_version')}`",
                 f"- Authority: `{value.get('authority')}`",
                 f"- Mutation: `{value.get('mutation')}`",
                 ""]
        for layer, atoms in (value.get("layers") or {}).items():
            lines.append(f"## {layer.capitalize()} ({len(atoms)})")
            for atom in atoms:
                lines.append(f"- `{atom['id']}` — {atom['heading']}")
    return "\n".join(lines) + "\n"


def render_runner(title, value):
    """Card for RunnerService status/start/stop/enable output."""
    lines = [f"# {title}", ""]
    if value.get("running"):
        started = f" · started {value.get('started_at')}" if value.get("started_at") else ""
        lines += [f"- State: `running` (pid `{value.get('pid')}`{started})",
                  f"- Enabled: `{value.get('enabled')}`",
                  f"- Log: `{value.get('log_path')}`"]
    else:
        lines += [f"- State: `stopped`",
                  f"- Enabled: `{value.get('enabled')}`",
                  f"- Log: `{value.get('log_path')}`",
                  "",
                  "Start automation with `company runner start`."]
    return "\n".join(lines) + "\n"


def render_evals_list(value):
    """Card for `company eval list`."""
    items = value.get("evals") or []
    lines = [f"# Eval suites ({len(items)})", ""]
    for suite in items:
        criteria = suite.get("criteria") or []
        lines.append(f"- `{suite['id']}` · {suite['name']}")
        lines.append(f"  - department `{suite['department_id']}` · payload "
                     f"`{suite['payload_kind']}` · {len(criteria)} criteria · "
                     f"validity `{suite['validity']}`")
        for criterion in criteria:
            lines.append(f"  - `{criterion['id']}` — {criterion['name']} "
                         f"({criterion['source']}, {criterion['severity']})")
    lines += ["", "Run one suite with `company eval run SUITE_ID --payload PATH`."]
    return "\n".join(lines) + "\n"


def render_evals_run(value):
    """Card for `company eval run`: per-item verdict summary with pass/fail."""
    report = value.get("report") or {}
    request = value.get("request") or {}
    items = report.get("per_item") or {}
    lines = [f"# Eval report: {report.get('suite_id')}",
             "",
             f"- Payload: `{report.get('payload_id')}` · kind `{report.get('payload_kind')}`",
             f"- Overall: `{'pass' if report.get('overall') else 'FAIL'}` ",
             f"- Thresholds: `{report.get('thresholds')}`",
             f"- Judge: `{report.get('judge_connector')}` · validity "
             f"`{report.get('validity')}` · {report.get('generated_at')}"]
    if value.get("evidence_id"):
        lines.append(f"- Evidence: `{value['evidence_id']}` on goal `{value['goal']}`")
    lines += ["", "## Per item"]
    for item_id, verdicts in items.items():
        state = "pass" if report.get("per_item_pass", {}).get(item_id) else "FAIL"
        lines.append(f"- {item_id}: `{state}`")
        for verdict in verdicts.values():
            marker = "ok " if verdict.get("pass") else "FAIL"
            lines.append(f"  - [{marker}] {verdict['criterion_id']}: {verdict['reason']}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
