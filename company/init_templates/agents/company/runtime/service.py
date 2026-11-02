"""Read-only inventory of the retired product runner; no process launcher."""
from __future__ import annotations
import json,os
from pathlib import Path


class RunnerService:
    """Compatibility inventory only. Scheduling belongs to the selected host."""
    def __init__(self,project_root,db_path):
        from .boundary import require_runtime_destination
        require_runtime_destination(db_path)
        self.project_root=Path(project_root);self.db_path=Path(db_path)
        self.state_dir=self.db_path.parent;self.pid_path=self.state_dir/'runner.pid'
        self.log_path=self.state_dir/'runner.log';self.control_path=self.state_dir/'automation.json'

    def start(self,*args,**kwargs):raise RuntimeError('The product runner is retired. Use an explicit host wake for a bounded workflow.')
    def enable(self,*args,**kwargs):raise RuntimeError('The product runner is retired; scheduling belongs to the selected host.')
    def stop(self,*args,**kwargs):raise RuntimeError('Inventory the recorded process and retire that exact obsolete schedule explicitly; no unrelated process was stopped.')

    def status(self):
        metadata={}
        if self.pid_path.is_file():
            try:metadata=json.loads(self.pid_path.read_text())
            except (ValueError,OSError):metadata={'issue':'Unreadable historical runner record'}
        return {'retired':True,'enabled':False,'recorded_process':metadata,
                'policy':'read-only inventory; no process started, signalled or replayed'}


def automation_enabled(state_dir):
    """Historical callers cannot enable the retired product scheduler."""
    return False
