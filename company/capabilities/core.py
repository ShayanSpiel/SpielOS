"""Raw abilities exposed by Hosts and selected by Agent identity."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    """A named ability such as browser, terminal, or filesystem access.

    Capabilities contain no Goal, Workflow, or execution state. Hosts decide
    how an ability is implemented; Agents only declare the identities they may
    use, and Connections separately describe external access.
    """

    id: str
    description: str = ""
    host_ids: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    unattended: bool = False

    @property
    def requires_approval(self) -> bool:
        return not self.unattended
