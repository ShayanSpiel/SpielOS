"""Explicit repository roles keep runtime writes out of product and website trees."""

import json
from pathlib import Path

MARKER = ".spielos-boundary.json"


def restricted_repository(path: str | Path) -> tuple[Path, str] | None:
    candidate = Path(path).expanduser().resolve()
    for root in (candidate, *candidate.parents):
        marker = root / MARKER
        if not marker.is_file():
            continue
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            role = payload.get("role")
        except (OSError, ValueError, AttributeError) as error:
            raise ValueError(f"invalid repository boundary marker: {marker}") from error
        if role in {"source", "website"}:
            return root, role
        if role == "home":
            continue
        raise ValueError(f"unknown repository role in {marker}")
    return None


def require_runtime_destination(path: str | Path) -> None:
    boundary = restricted_repository(path)
    if boundary:
        root, role = boundary
        raise ValueError(
            f"{root} is a {role} repository; runtime state and company content "
            "belong in a separate SpielOS home. Select that home explicitly.")
