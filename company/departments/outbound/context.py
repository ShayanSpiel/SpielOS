"""Outbound context: the bundle of substrate every workflow step receives.

The loop passes this one object around. It holds the STATE (store), the
human-written CONTROL (control.json), the active WORKFLOW bundle, and the
artifact/report/log locations. Steps never reach for global paths.
"""

from dataclasses import dataclass
from pathlib import Path

from . import workflows
from .data import OutboundStore
from .artifacts import Artifacts
from .control import Control
from .policy import Policy


@dataclass
class Context:
    store: OutboundStore
    control: Control
    workflow: workflows.Workflow
    artifacts: Artifacts
    policy: Policy
    stop_file: Path
    data_dir: Path
    reports_dir: Path
    dry: bool = False


def build_context(dry: bool = False) -> Context:
    """Build domain context without creating another lifecycle or runner."""
    from ...runtime.paths import find_project_root

    project_root = find_project_root()
    agents_root = project_root / ".agents"
    data_dir = project_root / ".spielos" / "state" / "outbound"
    artifacts_dir = project_root / ".spielos" / "artifacts" / "outbound"
    logs_dir = data_dir / "logs"
    workflows.import_all()
    store = OutboundStore(data_dir / "outbound.sqlite")
    control = Control(data_dir / "control.json")
    workflow = workflows.get("email")
    return Context(store=store, control=control, workflow=workflow,
                   artifacts=Artifacts(artifacts_dir, artifacts_dir, logs_dir),
                   policy=Policy(workflow), stop_file=data_dir / "STOP",
                   data_dir=data_dir, reports_dir=artifacts_dir, dry=dry)
