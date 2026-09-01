"""One portable command surface for Codex, OpenCode, and humans."""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .runtime.models import GoalStatus
from .runtime.runner import Runner
from .runtime.loop import CompatibilityRuntime
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
    commands.add_parser("catalog")
    departments_parser = commands.add_parser("departments", help="list installed Departments")
    departments_parser.add_argument("--json", action="store_true")
    overview = commands.add_parser(
        "overview", help="one view of Goals, Departments, Agents, assignments, and health")
    overview.add_argument("--json", action="store_true")
    observatory = commands.add_parser(
        "observatory", help="live visual map of architecture, activity, and coherence")
    observatory.add_argument(
        "--snapshot", action="store_true",
        help="print one read-only observability snapshot instead of serving the UI")
    observatory.add_argument("--host", default="127.0.0.1")
    observatory.add_argument("--port", type=int, default=8765)
    observatory.add_argument(
        "--no-open", action="store_true", help="serve without opening a browser window")
    observatory.add_argument("--json", action="store_true")
    init = commands.add_parser("init", help="scaffold a self-contained harness home (see README)")
    init.add_argument("--dir", default=".", help="target directory (default: cwd)")
    init.add_argument("--force", action="store_true", help="overwrite existing files")
    init.add_argument("--all-departments", action="store_true",
                      help="vendor every bundled Department")
    init.add_argument("--department", action="append", default=[],
                      help="vendor this Department from templates (repeatable)")
    init.add_argument("-y", "--yes", action="store_true",
                      help="non-interactive: accept defaults, never prompt")
    init.add_argument("--json", action="store_true",
                      help="print the machine-readable receipt instead of the human card")
    update = commands.add_parser(
        "update", help="update a home from the installed SpielOS release (user layer preserved)")
    update.add_argument("--force", action="store_true", default=True)
    update.add_argument("--dir", help="exact SpielOS home to update (default: current/nearest home)")
    update.add_argument("--json", action="store_true")
    refresh = commands.add_parser("refresh", help="compatibility alias for `spielos update`")
    refresh.add_argument("--force", action="store_true", default=True)
    refresh.add_argument("--dir", help="exact SpielOS home to update (default: current/nearest home)")
    refresh.add_argument("--json", action="store_true")
    add_cmd = commands.add_parser(
        "add", help="install a Department bundle (.sdep), bundle directory, or built-in id")
    add_cmd.add_argument("source")
    add_cmd.add_argument("--force", action="store_true")
    add_cmd.add_argument("--dir", help="exact SpielOS home to modify")
    agent = commands.add_parser("agent", help="first-class Agent operations")
    agent_commands = agent.add_subparsers(dest="agent_command", required=True)
    agent_list = agent_commands.add_parser(
        "list", help="list every bounded Agent")
    agent_list.add_argument("--json", action="store_true")
    compile_cmd = agent_commands.add_parser("compile",
        help="compile a Department Workflow into a first-class Agent")
    compile_cmd.add_argument("department", help="Department id")
    compile_cmd.add_argument("--workflow", required=True, help="Workflow id inside the Department")
    compile_cmd.add_argument("--name", help="Agent name (default: <department>-<workflow>)")
    compile_cmd.add_argument("--force", action="store_true")
    compile_cmd.add_argument("--dir", help="exact SpielOS home to modify (default: current/nearest home)")
    strategy = commands.add_parser("strategy", help="show the read-only Strategy Kernel")
    strategy.add_argument("--topic", action="append", default=[])
    strategy.add_argument("--scope", action="append", default=[])
    strategy.add_argument("--category", action="append", choices=(
        "company", "icp", "positioning", "priorities", "constraints", "preferences"),
        default=[])
    strategy.add_argument("--max-sections", type=int, default=8)
    strategy.add_argument("--json", action="store_true")
    context = commands.add_parser("context", help="assemble bounded host context")
    context.add_argument("--prompt", default="")
    context.add_argument("--boot", action="store_true")
    context.add_argument("--owner")
    context.add_argument("--workflow")
    context.add_argument("--step")
    context.add_argument("--trigger-context", default="{}",
                         help="JSON object used for Workflow-memory applicability")
    context.add_argument("--dependency", action="append", default=[],
                         help="available dependency id (repeatable)")
    context.add_argument("--token-budget", type=int)
    context.add_argument("--json", action="store_true")
    profile = commands.add_parser("profile", help="typed company-profile overlays")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_set = profile_commands.add_parser("set")
    profile_set.add_argument("--namespace", required=True)
    profile_set.add_argument("--key", required=True)
    profile_set.add_argument("--value", required=True)
    profile_set.add_argument("--scope", choices=("company", "goal", "workflow"), default="company")
    profile_set.add_argument("--goal")
    profile_set.add_argument("--workflow")
    profile_set.add_argument("--source-ref")
    profile_set.add_argument("--source-excerpt", default="")
    profile_set.add_argument("--authority", default="owner_explicit")
    profile_set.add_argument("--json", action="store_true")
    profile_list = profile_commands.add_parser("list")
    profile_list.add_argument("--goal")
    profile_list.add_argument("--workflow")
    profile_list.add_argument("--json", action="store_true")
    memory = commands.add_parser("memory", help="learned experiment and Workflow memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    memory_summary = memory_commands.add_parser(
        "summary", help="show every durable memory layer without inspecting SQLite")
    memory_summary.add_argument("--json", action="store_true")
    experiment_list = memory_commands.add_parser("experiments")
    experiment_list.add_argument("--owner")
    experiment_list.add_argument("--json", action="store_true")
    workflow_list = memory_commands.add_parser("workflows")
    workflow_list.add_argument("--json", action="store_true")
    workflow_observe = memory_commands.add_parser("observe-workflow")
    workflow_observe.add_argument("--workflow", required=True)
    workflow_observe.add_argument("--behavior-key")
    workflow_observe.add_argument("--title", required=True)
    workflow_observe.add_argument("--instructions", required=True,
                                  help="JSON array of concise reusable steps")
    workflow_observe.add_argument("--trigger", default="{}")
    workflow_observe.add_argument("--dependencies", default="[]")
    workflow_observe.add_argument("--department")
    workflow_observe.add_argument("--source-ref")
    workflow_observe.add_argument("--explicit-update", action="store_true")
    workflow_observe.add_argument("--json", action="store_true")
    apply_memory = memory_commands.add_parser(
        "apply-candidate", help="resolve one model-extracted typed memory candidate")
    apply_memory.add_argument("--candidate", required=True, help="typed candidate JSON object")
    apply_memory.add_argument("--json", action="store_true")
    consolidate = memory_commands.add_parser("consolidate")
    consolidate.add_argument("--json", action="store_true")
    department = commands.add_parser(
        "department", help="validate, install, list, and export portable Department packages")
    department_commands = department.add_subparsers(dest="department_command", required=True)
    for name in ("validate", "install"):
        item = department_commands.add_parser(name)
        item.add_argument("--spec", help="Department JSON object")
        item.add_argument("--file", help="path to Department JSON file")
        item.add_argument("--id", help="override/default Department id")
        if name == "install":
            item.add_argument("--force", action="store_true")
            item.add_argument("--dir", help="exact SpielOS home to modify")
    department_commands.add_parser("list").add_argument("--json", action="store_true")
    department_export = department_commands.add_parser("export")
    department_export.add_argument("id", help="Department id")
    department_export.add_argument("--out", default=".")
    artifact = commands.add_parser(
        "artifact", help="prepare, finalize, clean, and present canonical outcomes")
    artifact_commands = artifact.add_subparsers(dest="artifact_command", required=True)
    prepare = artifact_commands.add_parser("prepare")
    prepare.add_argument("--goal", required=True)
    prepare.add_argument("--run", required=True)
    prepare.add_argument("--workflow")
    prepare.add_argument("--json", action="store_true")
    finalize = artifact_commands.add_parser("finalize")
    finalize.add_argument("--goal", required=True)
    finalize.add_argument("--run", required=True)
    finalize.add_argument("--workflow")
    finalize.add_argument("--file", action="append", required=True)
    finalize.add_argument("--label", default="")
    finalize.add_argument("--copy", action="store_true",
                          help="copy finals instead of moving them out of the work folder")
    finalize.add_argument("--keep-work", action="store_true",
                          help="retain declared intermediates instead of cleaning the work folder")
    finalize.add_argument("--open", action="store_true",
                          help="open the final outcome folder after finalization")
    finalize.add_argument("--json", action="store_true")
    artifact_list = artifact_commands.add_parser("list")
    artifact_list.add_argument("--goal")
    artifact_list.add_argument("--json", action="store_true")
    present = artifact_commands.add_parser("present")
    present.add_argument("path")
    present.add_argument("--open", action="store_true")
    present.add_argument("--json", action="store_true")
    friction = commands.add_parser(
        "friction", help="record and inspect misleading tools, commands, or instructions")
    friction_commands = friction.add_subparsers(dest="friction_command", required=True)
    friction_report = friction_commands.add_parser("report")
    friction_report.add_argument("--kind", required=True)
    friction_report.add_argument("--source", required=True)
    friction_report.add_argument("--expected", required=True)
    friction_report.add_argument("--actual", required=True)
    friction_report.add_argument("--fallback", default="")
    friction_report.add_argument("--goal")
    friction_report.add_argument("--json", action="store_true")
    friction_list = friction_commands.add_parser("list")
    friction_list.add_argument("--limit", type=int, default=100)
    friction_list.add_argument("--json", action="store_true")
    migration = commands.add_parser(
        "migration", help="inspect and normalize foreign files or harnesses safely")
    migration_commands = migration.add_subparsers(dest="migration_command", required=True)
    for name in ("inspect", "plan"):
        item = migration_commands.add_parser(name)
        item.add_argument("--from", dest="source", required=True)
        if name == "plan":
            item.add_argument("--out")
        item.add_argument("--json", action="store_true")
    core_plan = migration_commands.add_parser(
        "core-plan", help="preview an explicit legacy-Goal cutover without writing")
    core_plan.add_argument("--goal", action="append", required=True,
                           help="legacy Goal id to migrate (repeatable)")
    core_plan.add_argument("--json", action="store_true")
    core_apply = migration_commands.add_parser(
        "core-apply", help="back up state and migrate explicitly selected Goals")
    core_apply.add_argument("--goal", action="append", required=True,
                            help="legacy Goal id to migrate (repeatable)")
    core_apply.add_argument("--backup", help="exact backup destination")
    core_apply.add_argument("--json", action="store_true")
    goal = commands.add_parser("goal")
    goals = goal.add_subparsers(dest="goal_command", required=True)
    create = goals.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--owner", required=True)
    create.add_argument("--metric", required=True)
    create.add_argument(
        "--aggregation",
        choices=("count", "sum", "latest", "max", "min", "boolean_all", "boolean_any"),
        default="latest")
    create.add_argument("--operator", choices=("ge", "gt", "eq", "le", "lt"), default="ge")
    create.add_argument("--target", required=True)
    create.add_argument("--deadline")
    create.add_argument("--parent")
    create.add_argument("--supports", action="append", default=[],
                        help="Goal ID this Goal causally supports; repeat for a support DAG")
    create.add_argument("--blocks", action="append", default=[],
                        help="Goal ID this Goal blocks from running; repeat for a block DAG")
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
    topology = goals.add_parser(
        "topology", help="audit the parent tree, support DAG, and block DAG")
    topology.add_argument("--json", action="store_true")
    show = goals.add_parser("show"); show.add_argument("goal_id")
    show.add_argument("--json", action="store_true")
    link = goals.add_parser("link"); link.add_argument("goal_id")
    link_relation = link.add_mutually_exclusive_group(required=True)
    link_relation.add_argument("--supports")
    link_relation.add_argument("--blocks")
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
    tick = runner_commands.add_parser("tick"); tick.add_argument("goal_id", nargs="?"); tick.add_argument("--max-advances", type=int, default=100); tick.add_argument("--json", action="store_true")
    watch = runner_commands.add_parser("watch"); watch.add_argument("goal_id", nargs="?"); watch.add_argument("--interval", type=float, default=2.0); watch.add_argument("--max-ticks", type=int); watch.add_argument("--json", action="store_true")
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
    dispatch = commands.add_parser("dispatch", help="record and read dispatch retry attempts")
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
    tasks = commands.add_parser("tasks", help="list durable Agent work orders")
    tasks.add_argument("work_order_id", nargs="?")
    tasks.add_argument("--status", choices=("active", "open", "claimed", "done", "cancelled"),
                       default="active")
    tasks.add_argument("--goal")
    tasks.add_argument("--limit", type=int, default=50)
    tasks.add_argument("--json", action="store_true")
    tasks.add_argument("--claim", metavar="AGENT_ID")
    tasks.add_argument("--complete", metavar="AGENT_ID")
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

    if args.command in {"catalog", "departments", "strategy", "init", "update", "refresh",
                        "add", "agent", "department", "artifact", "friction", "migration"}:
        return None
    if args.command == "runner" and args.runner_command in {"status", "start", "stop", "enable"}:
        return None
    if args.command in {"status", "context", "overview", "observatory"}:
        return "read"
    if args.command == "report":
        return "read"
    if args.command == "goal" and getattr(args, "goal_command", None) in {"list", "show", "topology"}:
        return "read"
    if args.command == "notifications" and args.notification_command == "list":
        return "read"
    if args.command == "dispatch" and args.dispatch_command == "list":
        return "read"
    if args.command == "tasks" and not getattr(args, "claim", None) and not getattr(args, "complete", None):
        return "read"
    if args.command == "eval" and args.eval_command == "list":
        return None
    if args.command == "profile" and args.profile_command == "list":
        return "read"
    if args.command == "memory" and args.memory_command in {"summary", "experiments", "workflows"}:
        return "read"
    return "write"


def _uses_goal_authority(args) -> bool:
    """Commands that must never cross the active Goal-state boundary."""

    return args.command in {
        "goal", "once", "next", "status", "approve", "pause", "resume",
        "abandon", "retry", "evidence", "tasks", "runner", "report", "change",
        "memory", "profile", "context", "overview", "observatory",
    } or (args.command == "eval" and getattr(args, "goal", None))


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
                runtime = CompatibilityRuntime(DEFAULT_DB, readonly=True)
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
    runtime = None
    if mode:
        if _uses_goal_authority(args):
            from .commands import CleanCommandRuntime, goal_authority
            runtime = (CleanCommandRuntime(args.db, readonly=(mode == "read"))
                       if goal_authority(args.db) == "clean-core" else
                       CompatibilityRuntime(args.db, readonly=(mode == "read")))
        else:
            runtime = CompatibilityRuntime(args.db, readonly=(mode == "read"))
    exit_code = 0
    try:
        if args.command == "init":
            from .runtime.onboard import run_init
            return run_init(dir=args.dir, force=args.force,
                            minimal=not args.all_departments,
                            departments=args.department or None,
                            assume_yes=args.yes, as_json=args.json)
        if args.command == "observatory":
            from .runtime.observability import collect_snapshot, serve_observatory

            if args.snapshot:
                output = collect_snapshot(runtime, project_root=PROJECT_ROOT)
            else:
                serve_observatory(
                    runtime, project_root=PROJECT_ROOT, host=args.host, port=args.port,
                    open_browser=not args.no_open)
                return 0
        elif args.command == "artifact":
            from .runtime.artifacts import (
                finalize_workspace, list_artifacts, prepare_workspace,
                present_artifact)
            if args.artifact_command == "prepare":
                output = prepare_workspace(
                    goal_id=args.goal, run_id=args.run,
                    workflow_id=args.workflow, project_root=PROJECT_ROOT)
            elif args.artifact_command == "finalize":
                output = finalize_workspace(
                    goal_id=args.goal, run_id=args.run, files=args.file,
                    workflow_id=args.workflow, label=args.label,
                    move=not args.copy, cleanup_work=not args.keep_work,
                    project_root=PROJECT_ROOT)
                if args.open:
                    output["presentation"] = present_artifact(
                        output["final"], open_folder=True, project_root=PROJECT_ROOT)
            elif args.artifact_command == "present":
                output = present_artifact(
                    args.path, open_folder=args.open, project_root=PROJECT_ROOT)
            else:
                output = list_artifacts(goal_id=args.goal, project_root=PROJECT_ROOT)
        elif args.command == "friction":
            from .runtime.friction import friction_events, record_friction
            if args.friction_command == "report":
                output = record_friction(
                    kind=args.kind, source=args.source, expected=args.expected,
                    actual=args.actual, fallback=args.fallback,
                    goal_id=args.goal, project_root=PROJECT_ROOT)
            else:
                output = friction_events(project_root=PROJECT_ROOT, limit=args.limit)
        elif args.command == "migration":
            if args.migration_command in {"core-plan", "core-apply"}:
                from .state import Database, migrate_legacy_goals
                from .state.migration import backup_database, plan_legacy_goal_migration

                database = Database(args.db)
                plan = plan_legacy_goal_migration(database, args.goal)
                if args.migration_command == "core-plan":
                    output = plan
                else:
                    if plan["missing"] or plan["core_conflicts"]:
                        raise ValueError(
                            "core cutover refused: resolve missing Goals and core conflicts first")
                    backup = (Path(args.backup).expanduser().resolve() if args.backup else
                              Path(args.db).with_name(
                                  "company.before-core-cutover-" +
                                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") +
                                  ".sqlite"))
                    if backup.exists():
                        raise ValueError(f"backup destination already exists: {backup}")
                    backup_database(database, backup)
                    result = migrate_legacy_goals(database, args.goal)
                    output = {"plan": plan, **result, "backup": str(backup),
                              "authority": "clean-core"}
            else:
                from .runtime.migration import inspect_source, migration_plan
                output = (inspect_source(args.source) if args.migration_command == "inspect"
                          else migration_plan(args.source))
            if args.migration_command == "plan" and args.out:
                destination = Path(args.out).expanduser().resolve()
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(
                    json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
                output["plan_path"] = str(destination)
        elif args.command == "agent" and args.agent_command == "list":
            from .runtime.catalog import catalog
            output = catalog()["agents"]
        elif args.command in {"departments", "department"}:
            from .runtime.registry import departments
            if args.command == "departments" or args.department_command == "list":
                output = [{"id": item.id, "version": item.version,
                           "agents": list(item.agent_ids),
                           "workflows": [flow.id for flow in item.workflows]}
                          for item in departments().values()]
            elif args.department_command == "export":
                from .runtime.export import export_department
                output = export_department(args.id, Path(args.out).expanduser())
            else:
                from .runtime.install import (
                    install_department, normalize_department_spec, validate_department_spec)
                payload = (json.loads(Path(args.file).read_text()) if args.file else
                           json.loads(args.spec) if args.spec else None)
                if not isinstance(payload, dict):
                    raise ValueError("provide --spec JSON or --file path")
                normalized = normalize_department_spec(payload, default_id=args.id)
                defects = validate_department_spec(normalized)
                if args.department_command == "validate":
                    output = {"ok": not defects, "defects": defects,
                              "package": normalized}
                else:
                    if args.dir:
                        from .runtime.paths import selected_project_root, validate_home_destination
                        home = validate_home_destination(selected_project_root(args.dir))
                        output = install_department(
                            normalized, force=args.force,
                            root=home / ".agents/company/departments",
                            agents_root=home / ".agents/company/agents/installed")
                    else:
                        output = install_department(normalized, force=args.force)
            print(json.dumps(output, indent=2))
            return 0
        elif args.command == "add":
            from .runtime.export import add_department
            output = add_department(args.source, force=args.force, target=args.dir)
            print(json.dumps(output, indent=2))
            return 0
        elif args.command in {"update", "refresh"}:
            from .runtime.export import refresh_home
            receipt = refresh_home(force=True, target=args.dir)
            if getattr(args, "json", False):
                print(json.dumps(receipt, indent=2))
            else:
                print(render_update(receipt))
            return 0
        elif args.command == "agent" and args.agent_command == "compile":
            from .runtime.agent_compile import compile_agent
            receipt = compile_agent(args.department, args.workflow,
                                    args.name, force=args.force, home=args.dir)
            print(json.dumps(receipt, indent=2))
            return 0
        elif args.command == "catalog":
            from .runtime.catalog import catalog
            output = catalog()
        elif args.command == "overview":
            from .runtime.catalog import company_overview
            output = company_overview(runtime, project_root=PROJECT_ROOT)
        elif args.command == "strategy":
            from .runtime.models import Goal
            from .runtime.strategy import (
                load_strategy_kernel, select_strategy_context, strategy_kernel_summary)
            kernel = load_strategy_kernel()
            if args.topic or args.scope or args.category:
                synthetic = Goal(
                    id="strategy-view", name="Inspect canonical strategy",
                    owner_id="director", metric="strategy_state", operator="eq",
                    target="current", deadline=None, parent_id=None,
                    goal_status="active", config={"strategy_context": {
                        "topics": args.topic, "scopes": args.scope or ["director"],
                        "categories": args.category,
                    }})
                output = select_strategy_context(
                    synthetic, kernel, max_sections=args.max_sections)
            else:
                output = strategy_kernel_summary(kernel)
        elif args.command == "context":
            trigger_context = json.loads(args.trigger_context)
            if not isinstance(trigger_context, dict):
                raise ValueError("--trigger-context must be a JSON object")
            if hasattr(runtime, "assemble_context"):
                output = runtime.assemble_context(
                    prompt=args.prompt, boot=args.boot, owner_id=args.owner,
                    workflow_id=args.workflow, step_id=args.step,
                    trigger_context=trigger_context,
                    available_dependencies=args.dependency,
                    token_budget=args.token_budget)
            else:
                from .runtime.context import ContextAssembler
                output = ContextAssembler(runtime.store, project_root=PROJECT_ROOT).assemble(
                    prompt=args.prompt, boot=args.boot, owner_id=args.owner,
                    workflow_id=args.workflow, step_id=args.step,
                    trigger_context=trigger_context,
                    available_dependencies=args.dependency,
                    token_budget=args.token_budget)
            if not args.json:
                print(output["context"])
                return 0
        elif args.command == "profile":
            if args.profile_command == "set":
                output = runtime.store.set_profile_claim(
                    namespace=args.namespace, claim_key=args.key,
                    value=scalar(args.value), scope=args.scope,
                    goal_id=args.goal, workflow_id=args.workflow,
                    authority=args.authority, source_ref=args.source_ref,
                    source_excerpt=args.source_excerpt)
            else:
                output = list(runtime.store.profile_claims(
                    goal_id=args.goal, workflow_id=args.workflow, limit=200))
        elif args.command == "memory":
            if args.memory_command == "summary":
                if hasattr(runtime, "clean_memory_summary"):
                    output = runtime.clean_memory_summary()
                else:
                    profile_claims = list(runtime.store.profile_claims(limit=200))
                    directives = list(runtime.store.directives(limit=100))
                    experiments = list(runtime.store.experiment_memories(limit=200))
                    workflows = list(runtime.store.workflow_memories(limit=200))
                    legacy = list(runtime.store.recent_memories(50))
                    output = {
                    "schema_version": 2,
                    "durable_memory": {
                        "company_profile": profile_claims,
                        "operating_directives": directives,
                        "experiment_learning": experiments,
                        "workflow_memory": workflows,
                        "legacy_learning": legacy,
                    },
                    "counts": {
                        "company_profile": len(profile_claims),
                        "operating_directives": len(directives),
                        "experiment_learning": len(experiments),
                        "workflow_memory": len(workflows),
                        "legacy_learning": len(legacy),
                    },
                    "interpretation": (
                        "All five categories are durable memory. An empty learning category "
                        "does not mean owner profile memory is absent."
                    ),
                    }
            elif args.memory_command == "experiments":
                output = ([item for item in runtime.memories(200)
                           if item["scope"] == "strategy" and item["status"] == "active"]
                          if hasattr(runtime, "clean_memory_summary") else
                          list(runtime.store.experiment_memories(
                              owner_id=args.owner, limit=200)))
            elif args.memory_command == "workflows":
                output = ([item for item in runtime.memories(200)
                           if item["scope"] == "workflow" and item["status"] == "active"]
                          if hasattr(runtime, "clean_memory_summary") else
                          list(runtime.store.workflow_memories(limit=200)))
            elif args.memory_command == "observe-workflow":
                if hasattr(runtime, "clean_memory_summary"):
                    raise ValueError(
                        "clean Workflow Memory is written from evidence-backed Goal execution")
                instructions = json.loads(args.instructions)
                dependencies = json.loads(args.dependencies)
                trigger = json.loads(args.trigger)
                if not isinstance(instructions, list) or not isinstance(dependencies, list):
                    raise ValueError("--instructions and --dependencies must be JSON arrays")
                if not isinstance(trigger, dict):
                    raise ValueError("--trigger must be a JSON object")
                output = runtime.store.observe_workflow_memory(
                    workflow_id=args.workflow, title=args.title,
                    behavior_key=args.behavior_key,
                    instructions=instructions, trigger=trigger,
                    dependencies=dependencies, department_id=args.department,
                    source_ref=args.source_ref, explicit_update=args.explicit_update)
            elif args.memory_command == "apply-candidate":
                if hasattr(runtime, "clean_memory_summary"):
                    raise ValueError(
                        "legacy memory candidates are available only in compatibility inspection")
                from .runtime.memory_capture import apply_candidate
                candidate = json.loads(args.candidate)
                output = apply_candidate(runtime.store, candidate)
            else:
                if hasattr(runtime, "clean_memory_summary"):
                    raise ValueError(
                        "legacy memory consolidation is available only in compatibility inspection")
                output = runtime.store.consolidate_operating_memory()
        elif args.command == "goal" and args.goal_command == "create":
            config = json.loads(args.config)
            hypothesis = json.loads(args.hypothesis)
            controlled = json.loads(args.controlled)
            changed = json.loads(args.changed)
            if not isinstance(config, dict):
                raise ValueError("--config must be a JSON object")
            if args.supports:
                config["supports_goal_ids"] = list(dict.fromkeys(args.supports))
            if args.blocks:
                config["blocks_goal_ids"] = list(dict.fromkeys(args.blocks))
            if args.priority:
                config["priority"] = args.priority
            config["aggregation"] = args.aggregation
            output = runtime.create_goal(name=args.name, owner_id=args.owner, metric=args.metric,
                operator=args.operator, target=scalar(args.target), deadline=args.deadline,
                parent_id=args.parent, config=config, goal_id=args.id, run_type=args.run_type,
                hypothesis=hypothesis or None, controlled_variables=controlled, changed_variables=changed,
                evidence_validity=args.validity, parent_run_id=args.parent_run,
                triggered_by_run_id=args.triggered_by, resume_run_id=args.resume_run)
        elif args.command == "goal" and args.goal_command == "list":
            output = runtime.goal_summaries(limit=100)
        elif args.command == "goal" and args.goal_command == "topology":
            output = runtime.topology_audit()
        elif args.command == "goal" and args.goal_command == "link":
            output = (runtime.link_support(args.goal_id, args.supports)
                      if args.supports else runtime.link_block(args.goal_id, args.blocks))
        elif args.command == "goal":
            output = runtime.status(args.goal_id)
        elif args.command == "once":
            output = runtime.once(args.goal_id)
        elif args.command == "next":
            runtime.next(args.goal_id)
            if isinstance(runtime, CompatibilityRuntime):
                from .runtime.legacy_runner import LegacyRunner
                LegacyRunner(runtime).tick(args.goal_id)
            else:
                runtime.tick()
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
            if isinstance(runtime, CompatibilityRuntime):
                from .runtime.legacy_runner import LegacyRunner
                LegacyRunner(runtime).tick(args.goal_id)
            else:
                runtime.tick()
            output = runtime.status(args.goal_id)
        elif args.command == "change":
            output = runtime.complete_change(args.task_id, passed=args.passed,
                                             deployed=args.deployed, result=json.loads(args.result))
            if isinstance(runtime, CompatibilityRuntime):
                from .runtime.legacy_runner import LegacyRunner
                LegacyRunner(runtime).tick(output["goal"]["id"])
            else:
                Runner(runtime).tick(output["goal"]["id"])
            output = runtime.status(output["goal"]["id"])
        elif args.command == "runner":
            if isinstance(runtime, CompatibilityRuntime):
                from .runtime.legacy_runner import LegacyRunner
                runner = LegacyRunner(runtime)
            else:
                runner = Runner(runtime)
            if args.runner_command == "tick":
                output = (runner.tick(args.goal_id, args.max_advances)
                          if isinstance(runtime, CompatibilityRuntime)
                          else runtime.tick(args.max_advances))
            elif args.runner_command == "watch":
                # The daemon reports pending attention but never acknowledges
                # it. Only a host that actually displays an exact id may mark
                # that notification delivered.
                from .runtime.notifications import pending_notifications
                stream = (runner.watch(args.interval, args.goal_id, args.max_ticks)
                          if isinstance(runtime, CompatibilityRuntime)
                          else runtime.watch(args.interval, args.goal_id, args.max_ticks))
                for result in stream:
                    pending = (len(pending_notifications(runtime.store))
                               if isinstance(runtime, CompatibilityRuntime) else 0)
                    print(json.dumps({**result, "notifications_pending": pending},
                                     ensure_ascii=False, default=str), flush=True)
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
    line = (f"- `{item['id']}` · {item['agent_id']} · {goal_name} (`{item['goal_id']}`) · "
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

    Commands without a dedicated renderer (catalog, Department install,
    runner tick, tasks WORK_ORDER_ID, status --raw, ...) keep the raw JSON
    projection: they are machine views or runtime plumbing.
    """
    command = args.command
    if command == "overview":
        return render_overview(output)
    if command == "artifact":
        return render_artifact(args, output)
    if command == "friction":
        return render_friction(args, output)
    if command == "migration":
        return render_migration(args, output)
    if command == "agent" and args.agent_command == "list":
        return render_agents(output)
    if command in {"update", "refresh"}:
        return render_update(output)
    if command == "strategy":
        return render_strategy(output)
    if command == "goal":
        if args.goal_command == "create":
            return render_goal_created(output)
        if args.goal_command == "list":
            return render_goal_list(output)
        if args.goal_command == "topology":
            return render_goal_topology(output)
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
        if args.runner_command in titles:
            return render_runner(titles[args.runner_command], output)
        return json.dumps(output, indent=2, ensure_ascii=False, default=str)
    titles = {"pause": "Paused", "resume": "Resumed", "abandon": "Abandoned",
              "approve": "Approved", "retry": "Retried", "once": "Run once",
              "next": "Next run started"}
    if command in titles:
        return render_goal_state(f"{titles[command]}: {output['goal']['name']}", output)
    return json.dumps(output, indent=2, ensure_ascii=False, default=str)


def render_overview(value):
    goals, topology = value["goals"], value["goals"]["topology"]
    lines = ["# Company overview", "",
             f"- Runtime: `{value['runtime']['version']}`",
             f"- Goals: `{goals['counts']['total']}` total · "
             f"`{goals['counts']['active']}` active",
             f"- Goal roots: `{len(topology['root_goal_ids'])}` · "
             f"topology defects `{topology['defect_count']}`",
             f"- Departments: `{len(value['departments'])}`",
             f"- Agents: `{len(value['agents'])}`",
             f"- Skills: `{len(value['skills'])}` · Connections: `{len(value['connections'])}`",
             f"- Open work orders: `{len(value['work_orders'])}`",
             f"- Recorded friction: `{value['friction']['event_count']}` event(s)",
             f"- Artifact root: `{value['artifacts']['root']}`"]
    focus = goals.get("focus")
    if focus:
        lines += ["", "## Focus",
                  f"- {focus['name']} (`{focus['id']}`) · "
                  f"`{focus['goal_status']}/{focus['run_status']}`",
                  f"- {focus.get('why_next') or 'No next action recorded.'}"]
    if value["departments"]:
        lines += ["", "## Departments and Agents"]
        for department in value["departments"]:
            names = ", ".join(department["agent_ids"]) or "none"
            health = "healthy" if department.get("lego") else "invalid"
            lines.append(f"- `{department['id']}` — {names} · `{health}`")
    if topology["defect_count"]:
        lines += ["", "## Topology health",
                  "- The Goal graph is not migration-ready; run `company goal topology`."]
    return "\n".join(lines) + "\n"


def render_goal_topology(value):
    lines = ["# Goal topology", "",
             f"- Goals: `{value['goal_count']}`",
             f"- Roots: `{len(value['root_goal_ids'])}`",
             f"- Canonical primary root: `{value['canonical_root_goal_id'] or 'none'}`",
             f"- Defects: `{len(value['defects'])}`"]
    if value["root_goal_ids"]:
        lines += ["", "## Roots"] + [f"- `{item}`" for item in value["root_goal_ids"]]
    if value["defects"]:
        lines += ["", "## Defects"] + [
            f"- `{item['goal_id']}` · {item['kind']}" for item in value["defects"]]
    safe = (value.get("migration_plan") or {}).get("safe_first") or []
    if safe:
        lines += ["", "## Safe migration order"] + [f"{index}. {item}"
                for index, item in enumerate(safe, 1)]
    return "\n".join(lines) + "\n"


def render_agents(items):
    lines = [f"# Agents ({len(items)})", ""]
    for item in items:
        skills = ", ".join(item.get("skill_ids") or ()) or "no Skills"
        outputs = ", ".join(item.get("produces") or ()) or "no declared outputs"
        lines.append(f"- `{item['id']}` · Skills: {skills} · Produces: {outputs}")
    if not items:
        lines.append("- None installed.")
    return "\n".join(lines) + "\n"


def render_artifact(args, value):
    if args.artifact_command == "list":
        lines = [f"# Artifacts ({len(value)})", ""]
        lines += [f"- `{item.get('status', 'unknown')}` · `{item['workspace']}`"
                  for item in value] or ["- None."]
        return "\n".join(lines) + "\n"
    if args.artifact_command == "prepare":
        return ("# Artifact workspace prepared\n\n"
                f"- Work here: `{value['work']}`\n"
                f"- Final outcomes: `{value['final']}`\n"
                f"- Manifest: `{value['manifest']}`\n")
    if args.artifact_command == "finalize":
        opened = (value.get("presentation") or {}).get("opened")
        lines = ["# Outcome ready", "", f"- Final folder: `{value['final']}`",
                 f"- Final files: `{len(value['files'])}`",
                 f"- Working files cleaned: `{value['work_cleaned']}`"]
        if args.open:
            lines.append(f"- Folder opened: `{bool(opened)}`")
        return "\n".join(lines) + "\n"
    return ("# Outcome presented\n\n"
            f"- Path: `{value['path']}`\n- Folder: `{value['folder']}`\n"
            f"- Folder opened: `{value['opened']}`\n")


def render_friction(args, value):
    if args.friction_command == "report":
        return ("# Friction recorded\n\n"
                f"- Kind: `{value['kind']}`\n- Source: `{value['source']}`\n"
                f"- Expected: {value['expected']}\n- Actual: {value['actual']}\n"
                f"- Fingerprint: `{value['fingerprint']}`\n")
    lines = [f"# Friction events ({len(value)})", ""]
    lines += [f"- `{item['kind']}` · {item['source']} · {item['actual']}"
              for item in value] or ["- None."]
    return "\n".join(lines) + "\n"


def render_migration(args, value):
    if args.migration_command in {"core-plan", "core-apply"}:
        plan = value.get("plan", value)
        lines = [f"# Clean-core migration {args.migration_command}", "",
                 f"- Selected: `{len(plan.get('selected') or [])}`",
                 f"- Missing: `{len(plan.get('missing') or [])}`",
                 f"- Core conflicts: `{len(plan.get('core_conflicts') or [])}`",
                 f"- Parent links omitted: `{len(plan.get('parents_omitted') or [])}`",
                 f"- Support links omitted: `{len(plan.get('supports_omitted') or [])}`"]
        if value.get("backup"):
            lines += [f"- Backup: `{value['backup']}`",
                      f"- Migrated: `{len(value.get('migrated') or [])}`",
                      "- Authority: `clean-core` (compatibility writes are now disabled)"]
        else:
            lines += ["", "Review omissions, then apply the same explicit Goal selection."]
        return "\n".join(lines) + "\n"
    inspection = value.get("inspection", value)
    inventory = inspection["inventory"]
    lines = [f"# Migration {args.migration_command}", "",
             f"- Source: `{inspection['source']}`",
             f"- Detected version: `{inspection['detected_version'] or 'unknown'}`",
             f"- Departments found: `{len(inventory['departments'])}`",
             f"- Legacy capability packages to convert: `{len(inventory['retired_workgroups'])}`",
             f"- Operational state present: `{inventory['has_operational_state']}`",
             f"- Source fingerprint: `{inspection['fingerprint']}`"]
    if args.migration_command == "plan":
        lines += [f"- Conversion units: `{len(value['units'])}`",
                  f"- State action: `{value['state_action']}`"]
        if value.get("plan_path"):
            lines.append(f"- Plan written: `{value['plan_path']}`")
    lines += ["", "Foreign runtime files are never installed as the current spine; "
              "unknown material is quarantined for review."]
    return "\n".join(lines) + "\n"


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


def render_update(value):
    """Card for `spielos update` after installing a newer release."""
    lines = ["# SpielOS home updated", "",
             f"- Runtime: `{value.get('from_version') or 'unknown'}` → "
             f"`{value.get('version') or 'unknown'}`",
             f"- Updated files: `{value.get('refreshed_files', 0)}`",
             "- Preserved: strategy, assets, Departments, installed Agents, "
             "config.user.json, .spielos/ state"]
    lines += ["", "Reopen OpenCode or Codex, select the Director, and continue; "
              "fresh company state is injected automatically."]
    return "\n".join(lines) + "\n"


render_refresh = render_update


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
        for category, atoms in (value.get("categories") or {}).items():
            lines.append(f"## {category.capitalize()} ({len(atoms)})")
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
        lines.append(f"  - Department `{suite['department_id']}` · payload "
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
