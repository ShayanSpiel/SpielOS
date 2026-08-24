"""Judge connector abstraction for the evals Lego piece.

A JudgeConnector is the pluggable seam between the eval engine and whoever
supplies verdicts.  Two implementations ship with the framework:

- AgentJudgeConnector (default): honest in this harness.  It renders a
  structured EvalRequest (criterion text + payload excerpts), the calling
  agent supplies verdicts (via `company eval run --judge-response <json>` or
  interactive stdin), the connector validates the shape, and the engine
  computes the report.

- HttpJudgeConnector: an optional provider-API seam.  Declared so a hosted
  judge provider can be wired later; it is NOT required to function in this
  change and raises NotImplementedError on compute until then.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import EvalReport, EvalSuite


@runtime_checkable
class JudgeConnector(Protocol):
    """The pluggable verdict-supply seam used by the eval engine."""

    id: str

    def render_request(self, suite: EvalSuite, payload: dict[str, Any]) -> dict[str, Any]:
        """Structured, judge-readable rendering of the suite + payload items."""
        ...

    def validate(self, suite: EvalSuite, payload: dict[str, Any],
                 verdicts_raw: dict[str, Any]) -> list[str]:
        """Return shape errors for a raw verdict document (empty = valid)."""
        ...


class AgentJudgeConnector:
    """Default connector: the calling agent is the honest judge.

    The connector renders the request, validates the supplied verdicts, and
    delegates report computation to the engine (run_suite).  It never invents
    verdicts itself.
    """

    id = "agent:cli"

    def render_request(self, suite: EvalSuite, payload: dict[str, Any]) -> dict[str, Any]:
        from .engine import render_request

        return render_request(suite, payload)

    def validate(self, suite: EvalSuite, payload: dict[str, Any],
                 verdicts_raw: dict[str, Any]) -> list[str]:
        from .engine import validate_verdicts

        return validate_verdicts(suite, payload, verdicts_raw)


class HttpJudgeConnector:
    """Optional provider-API seam for a hosted judge.

    The seam is deliberately inert in this change: the harness runs with the
    honest AgentJudgeConnector.  Wiring a provider later means implementing
    `compute` behind the same EvalRequest contract and registering the
    connector id on the CLI.
    """

    id = "http:provider"

    def render_request(self, suite: EvalSuite, payload: dict[str, Any]) -> dict[str, Any]:
        from .engine import render_request

        return render_request(suite, payload)

    def validate(self, suite: EvalSuite, payload: dict[str, Any],
                 verdicts_raw: dict[str, Any]) -> list[str]:
        from .engine import validate_verdicts

        return validate_verdicts(suite, payload, verdicts_raw)

    def compute(self, suite: EvalSuite, payload: dict[str, Any]) -> EvalReport:
        raise NotImplementedError(
            "HttpJudgeConnector is a provider-API seam and is not wired in this "
            "change; use the honest AgentJudgeConnector (agent:cli)")
