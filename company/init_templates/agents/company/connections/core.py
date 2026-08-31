"""Logical external capability definition resolved by a Host."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Connection:
    id: str
    capabilities: tuple[str, ...] = ()
    requires_approval: bool = True
