"""Validated, read-only Strategy Kernel over existing authoritative sources."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


COMPANY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = COMPANY_ROOT / "strategy" / "kernel.json"
LAYERS = ("intent", "model", "policy", "constitution")
MAX_CONTEXT_SECTIONS = 8


def _source_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("strategy source must be a non-empty relative path")
    root = root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"strategy source escapes company authority: {value}") from exc
    if path.suffix != ".md" or not path.is_file():
        raise ValueError(f"strategy source is not an existing Markdown file: {value}")
    return path


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    match = None
    level = 0
    for index, line in enumerate(lines):
        found = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if found and found.group(2) == heading:
            match, level = index, len(found.group(1))
            break
    if match is None:
        raise ValueError(f"strategy heading not found: {heading}")
    end = len(lines)
    for index in range(match + 1, len(lines)):
        found = re.match(r"^(#{1,6})\s+", lines[index])
        if found and len(found.group(1)) <= level:
            end = index
            break
    return "\n".join(lines[match:end]).strip()


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item for item in value):
        raise ValueError(f"strategy atom {field} must be a non-empty string array")
    return tuple(value)


def load_strategy_kernel(
        manifest_path: Path | str = MANIFEST_PATH,
        *, company_root: Path | str = COMPANY_ROOT) -> dict[str, Any]:
    """Load and validate the logical Kernel without changing any source."""

    manifest_path = Path(manifest_path)
    root = Path(company_root).resolve()
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    layers = manifest.get("layers")
    if not isinstance(layers, dict) or tuple(layers) != LAYERS:
        raise ValueError("strategy kernel layers must be Intent, Model, Policy, Constitution in order")
    views = manifest.get("views")
    if not isinstance(views, dict) or set(views) != {
            "icp", "positioning", "voice", "measurement"}:
        raise ValueError("strategy kernel must expose ICP, positioning, voice, and measurement views")

    sources: dict[str, dict[str, str]] = {}
    atoms: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for layer in LAYERS:
        entries = layers[layer]
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"strategy layer {layer} must contain at least one atom")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("strategy atoms must be objects")
            identifier = entry.get("id")
            if (not isinstance(identifier, str) or not identifier.startswith(f"{layer}.")
                    or identifier in identifiers):
                raise ValueError(f"invalid or duplicate strategy atom id: {identifier}")
            identifiers.add(identifier)
            source = entry.get("source")
            heading = entry.get("heading")
            if not isinstance(heading, str) or not heading:
                raise ValueError(f"strategy atom {identifier} needs a heading")
            path = _source_path(root, source)
            text = path.read_text()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            sources[source] = {"path": source, "sha256": digest}
            atoms.append({
                "id": identifier,
                "layer": layer,
                "source": source,
                "source_sha256": digest,
                "heading": heading,
                "topics": _strings(entry.get("topics"), "topics"),
                "scopes": _strings(entry.get("scopes"), "scopes"),
                "required": entry.get("required") is True,
                "content": _section(text, heading),
            })

    for name, source in views.items():
        _source_path(root, source)
        if source not in sources:
            raise ValueError(f"strategy view {name} is not represented in the Kernel: {source}")
    state_material = raw + b"".join(
        f"{key}:{sources[key]['sha256']}\n".encode() for key in sorted(sources))
    return {
        "schema_version": manifest.get("schema_version"),
        "authority": manifest.get("authority"),
        "state_hash": hashlib.sha256(state_material).hexdigest(),
        "views": dict(views),
        "layers": {layer: [atom for atom in atoms if atom["layer"] == layer]
                   for layer in LAYERS},
        "sources": [sources[key] for key in sorted(sources)],
    }


def strategy_kernel_summary(kernel: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reference-only public projection; source content remains in its files."""

    kernel = kernel or load_strategy_kernel()
    return {
        "schema_version": kernel["schema_version"],
        "authority": kernel["authority"],
        "state_hash": kernel["state_hash"],
        "views": kernel["views"],
        "layers": {
            layer: [{key: atom[key] for key in (
                "id", "source", "heading", "topics", "scopes", "required")}
                    for atom in kernel["layers"][layer]]
            for layer in LAYERS
        },
        "sources": kernel["sources"],
        "mutation": "proposal_only_owner_authorized",
    }


def select_strategy_context(goal: Any, kernel: dict[str, Any] | None = None,
                            *, max_sections: int = MAX_CONTEXT_SECTIONS) -> dict[str, Any]:
    """Select direct strategy references only when a Goal explicitly asks.

    Most Goals need their measurable intent, not a four-layer strategy graph.
    Avoid loading or validating the legacy Kernel on every runtime transition;
    an explicit ``strategy_context`` selector keeps the old bounded reference
    view available for workflows that genuinely consume it.
    """

    config = goal.config if hasattr(goal, "config") else goal.get("config", {})
    owner_id = goal.owner_id if hasattr(goal, "owner_id") else goal.get("owner_id")
    selector = config.get("strategy_context") or {}
    if not isinstance(selector, dict):
        selector = {}
    current_intent = {
        "goal_id": goal.id if hasattr(goal, "id") else goal.get("id"),
        "name": goal.name if hasattr(goal, "name") else goal.get("name"),
        "metric": goal.metric if hasattr(goal, "metric") else goal.get("metric"),
        "operator": goal.operator if hasattr(goal, "operator") else goal.get("operator"),
        "target": goal.target if hasattr(goal, "target") else goal.get("target"),
    }
    if not selector and kernel is None:
        return {
            "state_hash": None,
            "current_intent": current_intent,
            "selector": {"topics": [], "scopes": [], "layers": []},
            "sections": [],
            "section_limit": MAX_CONTEXT_SECTIONS,
            "memory_separate": True,
            "strategy_mutable": False,
            "kernel_loaded": False,
        }
    kernel = kernel or load_strategy_kernel()
    topics = selector.get("topics") or ()
    scopes = selector.get("scopes") or (owner_id,)
    layers = selector.get("layers") or ("model", "policy", "constitution")
    if not isinstance(topics, (list, tuple)):
        topics = ()
    if not isinstance(scopes, (list, tuple)):
        scopes = (owner_id,)
    if not isinstance(layers, (list, tuple)):
        layers = ()
    topic_set = {str(item) for item in topics if item}
    scope_set = {str(item) for item in scopes if item}
    layer_set = {str(item) for item in layers if item in LAYERS}
    limit = max(1, min(int(max_sections), MAX_CONTEXT_SECTIONS))

    selected = []
    for layer in LAYERS:
        for atom in kernel["layers"][layer]:
            scope_match = "all" in atom["scopes"] or bool(scope_set.intersection(atom["scopes"]))
            explicit_match = (layer in layer_set and bool(topic_set.intersection(atom["topics"])))
            if scope_match and (atom["required"] or explicit_match):
                selected.append(atom)
            if len(selected) >= limit:
                break
        if len(selected) >= limit:
            break
    return {
        "state_hash": kernel["state_hash"],
        "current_intent": current_intent,
        "selector": {"topics": sorted(topic_set), "scopes": sorted(scope_set),
                     "layers": sorted(layer_set)},
        "sections": selected,
        "section_limit": MAX_CONTEXT_SECTIONS,
        "memory_separate": True,
        "strategy_mutable": False,
        "kernel_loaded": True,
    }
