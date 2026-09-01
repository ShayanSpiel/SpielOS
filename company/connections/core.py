"""Logical external capability definition resolved by a Host."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Connection:
    id: str
    description: str = ""
    capabilities: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ("codex", "opencode")
    unattended: bool = False
    required_environment: tuple[str, ...] = ()

    @property
    def requires_approval(self) -> bool:
        return not self.unattended


# Compatibility import alias; both names construct the same domain record.
ConnectionSpec = Connection
