"""Research store Connection: the shared research-signal and brief archive."""
from __future__ import annotations


class ResearchStoreConnection:
    """Read-only signal queries plus delivered-brief writes."""

    def signals(self, week: str) -> list[dict]:
        """Return the week's research signals (may be empty, never invented)."""
        raise NotImplementedError("wired by the host at runtime")

    def deliver(self, brief_markdown: str) -> str:
        """Deliver one rendered brief; returns its store id."""
        raise NotImplementedError("wired by the host at runtime")
