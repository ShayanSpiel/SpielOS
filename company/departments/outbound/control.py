"""Outbound configuration compatibility for campaign knobs.

The owner (or the orchestrator session acting for the owner) edits this
file. It holds the workflow selection, historical goal defaults, and runtime
knobs used by the Outbound domain adapter.

Approvals and goal lifecycle are owned exclusively by the company runtime.
Approval state belongs only to the company runtime. Old approval keys in an
existing control file are ignored.

Machine-written state never lands here — that lives in the SQLite store.
"""

import json
import os
from pathlib import Path

DEFAULT_CONTROL = {
    "workflow": "email",
    "goal": {
        "name": "reply rate",
        "metric": "reply_rate",
        "target": 0.30,
        "evidence_window_hours": 48,
        "min_sample": 20,
    },
    "knobs": {
        "block_size": 50,
        "throttle_seconds": 150,
        "daily_cap": 200,
        "cohort_filters": {"min_tier": "plausible"},
    },
}


class Control:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path) as f:
                    data = json.load(f)
                for key, default in DEFAULT_CONTROL.items():
                    data.setdefault(key, default)
                return data
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULT_CONTROL))

    def save(self) -> None:
        os.makedirs(self.path.parent, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    def workflow(self) -> str:
        return str(self._data.get("workflow") or "email")

    def goal(self) -> dict:
        return self._data.get("goal") or {}

    def knobs(self) -> dict:
        return self._data.get("knobs") or {}
