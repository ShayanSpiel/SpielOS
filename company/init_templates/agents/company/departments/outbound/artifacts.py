"""Outbound artifact writer used from company-runtime steps.

  data/artifacts/snapshot-<n>.json      — OBSERVE output
  data/artifacts/intervention-<n>.json  — DECIDE output
  data/artifacts/batch-<id>.json        — ACT/PREPARE output
  data/artifacts/preview-<id>.md        — human review surface for the batch
  reports/report-<id>.md + REPORT.md    — EVALUATE output (the owner's read)

A failure is visible in exactly one artifact; a step is reproducible by
re-reading its inputs.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

PREVIEW_HEADER = """# {batch_id} — {n} emails · {skipped} skipped · ready for review

hypothesis: {hypothesis}
workflow: {workflow}

Review every email before approving: each one must name a real, per-lead
workflow (no segment-generic copy), stay within the copy rules, and be one
a human would send under their own name.
"""


class Artifacts:
    def __init__(self, artifacts_dir: Path, reports_dir: Path, logs_dir: Path):
        self.artifacts_dir = Path(artifacts_dir)
        self.reports_dir = Path(reports_dir)
        self.logs_dir = Path(logs_dir)
        for d in (self.artifacts_dir, self.reports_dir, self.logs_dir):
            os.makedirs(d, exist_ok=True)

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    def save_json(self, name: str, payload: dict) -> str:
        path = self.artifacts_dir / f"{name}.json"
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, path)
        return str(path)

    def save_snapshot(self, snapshot: dict) -> str:
        path = self.save_json(f"snapshot-{self._ts()}", snapshot)
        return path

    def save_intervention(self, intervention: dict) -> str:
        return self.save_json(f"intervention-{self._ts()}", intervention)

    def save_batch(self, batch: dict) -> str:
        return self.save_json(f"batch-{batch.get('id', 'unset')}", batch)

    def write_preview(self, batch: dict, workflow_name: str) -> str:
        path = self.artifacts_dir / f"preview-{batch.get('id', 'unset')}.md"
        lines = [PREVIEW_HEADER.format(
            batch_id=batch.get("id", "unset"),
            n=len(batch.get("emails", [])),
            skipped=len(batch.get("skipped", [])),
            hypothesis=batch.get("hypothesis", ""),
            workflow=workflow_name)]
        for i, e in enumerate(batch.get("emails", [])):
            lines.append(f"## {i + 1}. {e['lead_id']} — {e['subject']}\n")
            lines.append(e.get("body_text", "")[:700].strip() + "\n---\n")
        if batch.get("skipped"):
            lines.append("## Skipped (not composed)\n")
            for s in batch["skipped"]:
                lines.append(f"- {s.get('lead_id')}: {s.get('reason')}")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        return str(path)

    def write_report(self, batch_id: str, markdown: str) -> str:
        path = self.reports_dir / f"report-{batch_id}.md"
        with open(path, "w") as f:
            f.write(markdown)
        latest = self.reports_dir / "REPORT.md"
        with open(latest, "w") as f:
            f.write(markdown)
        return str(path)

    def log(self, line: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with open(self.logs_dir / "department.log", "a") as f:
            f.write(f"{ts}  {line}\n")
