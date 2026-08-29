"""Bounded, host-neutral context assembly for disposable chat sessions.

Durable state is deliberately larger than model context.  This module builds a
small projection for SessionStart or one user prompt; Codex and OpenCode are
thin adapters over the same implementation.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .alignment import priority_score
from .memory import rank_experiment_memories, rank_workflow_memories
from .paths import find_project_root
from .service import RunnerService


BOOT_CHAR_BUDGET = 3600
TURN_CHAR_BUDGET = 5200
STRATEGY_FILES = {
    "focus": ("focus.md", {"focus", "priority", "ship", "build", "subtract"}),
    "icp": ("icp.md", {"icp", "buyer", "customer", "audience", "lead", "prospect"}),
    "positioning": ("positioning.md", {"positioning", "offer", "promise", "pricing", "category"}),
    "voice": ("voice.md", {"voice", "copy", "content", "write", "tone", "brand"}),
    "measurement": ("measurement.md", {"metric", "evidence", "measure", "outcome", "experiment"}),
    "method": ("operating-thesis.md", {"method", "workflow", "operate", "process", "autonomous"}),
}
BARE_GREETINGS = {
    "hi", "hello", "hey", "hiya", "howdy", "good morning",
    "good afternoon", "good evening",
}


def _terms(value: str | None) -> set[str]:
    return {item for item in re.findall(r"[a-z0-9][a-z0-9_-]+", (value or "").lower())
            if len(item) > 2}


def _compact_markdown(text: str, limit: int = 650) -> str:
    lines = []
    for raw in text.splitlines():
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        value = re.sub(r"^[-*>]+\s*", "", value)
        lines.append(value)
    compact = " ".join(lines)
    compact = re.sub(r"\s+", " ", compact).strip()
    return compact if len(compact) <= limit else compact[:limit - 1].rstrip() + "…"


def _bare_greeting(prompt: str) -> bool:
    normalized = re.sub(r"[^a-z0-9 ]+", "", (prompt or "").lower())
    return re.sub(r"\s+", " ", normalized).strip() in BARE_GREETINGS


def _strategy_root(project_root: Path) -> Path:
    vendored = project_root / ".agents" / "company" / "strategy"
    if vendored.is_dir():
        return vendored
    return Path(__file__).resolve().parents[1] / "strategy"


class ContextAssembler:
    def __init__(self, store, *, project_root: str | Path | None = None):
        self.store = store
        self.project_root = Path(project_root or find_project_root()).resolve()
        self.strategy_root = _strategy_root(self.project_root)

    def assemble(self, *, prompt: str = "", boot: bool = False,
                 owner_id: str | None = None, workflow_id: str | None = None,
                 step_id: str | None = None, token_budget: int | None = None) -> dict[str, Any]:
        query = _terms(prompt)
        budget = max(600, int(token_budget or
                              ((BOOT_CHAR_BUDGET if boot else TURN_CHAR_BUDGET) // 4)))
        char_budget = budget * 4
        sources: list[str] = []
        sections: list[tuple[int, str]] = []
        bare_greeting = _bare_greeting(prompt)

        if bare_greeting:
            sections.append((120,
                "Request route · bare greeting\n"
                "- Respond briefly as the Director and ask what the owner wants to move.\n"
                "- Make no tool calls. Do not run company status, overview, or any other "
                "command. Do not narrate or re-fetch company state."))
        sections.append((115,
            "State authority\n"
            "- This projection is the fresh company-state read for this exact request.\n"
            "- Never run company status or overview merely to confirm it. Use a targeted "
            "read only when requested detail is absent or the projection reports a conflict."))

        profile_lines = ([] if bare_greeting else
                         self._profile_lines(query, boot=boot, sources=sources))
        if profile_lines:
            sections.append((100, "Company profile\n" + "\n".join(profile_lines)))

        state_lines = self._state_lines(query, sources=sources)
        if state_lines:
            sections.append((95, "Company state\n" + "\n".join(state_lines)))

        claims = ([] if bare_greeting else
                  self._matching_profile_claims(query, workflow_id=workflow_id))
        if claims:
            sources.extend(item["id"] for item in claims)
            sections.append((90, "Durable company memory · owner direction\n" + "\n".join(
                f"- [{item['namespace']}.{item['claim_key']}] {self._render_value(item['value'])}"
                for item in claims[:8])))

        experiment = [] if bare_greeting else rank_experiment_memories(
            self._optional(self.store.experiment_memories, owner_id=owner_id, limit=100),
            prompt=prompt, owner_id=owner_id, workflow_id=workflow_id,
            step_id=step_id, limit=3)
        if experiment:
            sources.extend(item["id"] for item in experiment)
            sections.append((75, "Relevant experiment learning\n" + "\n".join(
                f"- [{item['id']}] {item['claim']} "
                f"(confidence {float(item.get('confidence') or 0):.2f}; "
                f"{item.get('confirmations', 0)} confirmation(s), "
                f"{item.get('contradictions', 0)} contradiction(s))"
                for item in experiment)))

        workflows = [] if bare_greeting else rank_workflow_memories(
            self._optional(self.store.workflow_memories, limit=100), prompt=prompt,
            workflow_id=workflow_id, limit=2)
        if workflows:
            sources.extend(item["id"] for item in workflows)
            sections.append((80, "Reusable Workflow instructions\n" + "\n".join(
                f"- [{item['id']}; {item['status']}] {item['title']}: "
                + "; ".join(str(step) for step in item.get("instructions") or ())
                for item in workflows)))

        friction = [] if bare_greeting else self._friction_lines(sources=sources)
        if friction:
            sections.append((85, "Open harness friction\n" + "\n".join(friction)))

        # This contract makes interpretation explicit while keeping hooks read-only.
        if not boot and not bare_greeting:
            sections.append((60,
                "Persistence rule\n"
                "Treat task-only instructions as temporary. When the owner explicitly says "
                "always/from now on/remember or directly updates a named Workflow, record a "
                "typed profile or Workflow-memory update with source scope before finishing. "
                "Do not infer a durable company fact from an ambiguous critique. Put generated "
                "work in the canonical artifact workspace, finalize only outcomes, and clean its "
                "work folder. Auto-open final folders only for owner-facing creative/content "
                "deliverables (video, image, audio, copy, document, or deck), never for code, "
                "packages, tests, logs, manifests, migration plans, or internal evidence unless "
                "the owner explicitly asks. Record "
                "tool, command, instruction, or result-shape friction before using a fallback."))

        rendered = "SpielOS context v2"
        kept = []
        for _, section in sorted(sections, key=lambda item: item[0], reverse=True):
            candidate = rendered + "\n\n" + section
            if len(candidate) > char_budget:
                remaining = char_budget - len(rendered) - 2
                if remaining > 160:
                    rendered += "\n\n" + section[:remaining - 1].rstrip() + "…"
                break
            rendered = candidate
            kept.append(section.splitlines()[0])
        version_material = json.dumps({"sources": sources, "context": rendered}, sort_keys=True)
        return {
            "schema_version": 2,
            "state_version": hashlib.sha256(version_material.encode()).hexdigest()[:16],
            "context": rendered,
            "sources": list(dict.fromkeys(sources)),
            "sections": kept,
            "estimated_tokens": max(1, (len(rendered) + 3) // 4),
            "budget_tokens": budget,
        }

    def _profile_lines(self, query: set[str], *, boot: bool, sources: list[str]) -> list[str]:
        selected = []
        for name, (filename, keywords) in STRATEGY_FILES.items():
            if not boot and query and not query.intersection(keywords):
                continue
            if boot and name not in {"focus", "icp", "positioning", "voice", "method"}:
                continue
            path = self.strategy_root / filename
            if not path.is_file():
                continue
            value = _compact_markdown(path.read_text(encoding="utf-8"), 520 if boot else 700)
            if value:
                selected.append(f"- {name}: {value}")
                sources.append(f"strategy:{filename}")
        return selected

    def _state_lines(self, query: set[str], *, sources: list[str]) -> list[str]:
        active = self.store.goal_summaries(statuses=("active",), limit=100)
        active.sort(key=lambda item: (-priority_score(item), item.get("created_at") or ""))
        service = RunnerService(self.project_root, self.store.path).status()
        work_order_count = len(self.store.work_orders(status="active", limit=100))
        runner = "running" if service["running"] else "paused"
        lines = [f"- Snapshot: fresh for this model request; runner {runner}; "
                 f"{len(active)} active Goal(s); {work_order_count} open work order(s)."]
        if not active:
            return lines + ["- No active company outcome."]
        roots = [item for item in active if not item.get("parent_id")]
        focus = (roots or active)[0]
        relevant = [focus]
        for item in active:
            text = f"{item.get('name')} {item.get('metric')} {item.get('owner_id')}"
            if item["id"] != focus["id"] and query.intersection(_terms(text)):
                relevant.append(item)
        lines.append(f"- Focus: {focus['name']} [{focus['id']}] — "
                     f"{focus['goal_status']}/{focus['run_status']}; "
                     f"{focus.get('why_next') or 'active'}")
        status_request = bool(query.intersection(
            {"status", "state", "pulse", "goals", "priorities", "progress"}))
        visible = active if status_request else relevant[1:4]
        for item in visible[:5]:
            if item["id"] == focus["id"]:
                continue
            lines.append(f"- Relevant Goal: {item['name']} [{item['id']}] — {item['run_status']}")
        attention = self.store.attention(5)
        for item in attention[:3]:
            lines.append(f"- Attention: {item['kind']} on {item['name']} — "
                         f"{item.get('required_user_action') or item.get('message') or item.get('why_next')}")
        sources.extend(f"goal:{item['id']}" for item in (visible[:5] if status_request else relevant[:4]))
        return lines

    def _matching_profile_claims(self, query: set[str], *, workflow_id: str | None) -> list[dict]:
        claims = list(self._optional(
            self.store.profile_claims, workflow_id=workflow_id, limit=100))
        if not query:
            return claims[:8]
        scored = []
        for item in claims:
            text = " ".join((item.get("namespace") or "", item.get("claim_key") or "",
                             json.dumps(item.get("value"), ensure_ascii=False),
                             item.get("source_excerpt") or ""))
            score = len(query.intersection(_terms(text)))
            if score or item.get("authority") == "owner_explicit":
                scored.append((score, item.get("updated_at") or "", item))
        scored.sort(reverse=True, key=lambda value: (value[0], value[1]))
        return [item for _, _, item in scored]

    def _friction_lines(self, *, sources: list[str]) -> list[str]:
        from .friction import friction_summary

        summary = friction_summary(project_root=self.project_root)
        if not summary["event_count"]:
            return []
        recent = summary["recent"][:2]
        sources.extend(f"friction:{item['fingerprint']}" for item in recent)
        lines = [f"- {summary['event_count']} recorded event(s), "
                 f"{summary['unique_count']} unique mismatch(es)."]
        lines.extend(
            f"- [{item['kind']}] {item['source']}: expected {item['expected']}; "
            f"actual {item['actual']}"
            for item in recent)
        return lines

    @staticmethod
    def _render_value(value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _optional(reader, **kwargs):
        """Treat not-yet-migrated optional memory tables as an empty layer."""

        try:
            return reader(**kwargs)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            return ()


def codex_hook_output(projection: dict[str, Any], event_name: str) -> dict[str, Any]:
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": projection["context"],
        },
    }
