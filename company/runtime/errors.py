"""Transient failure taxonomy for provider-flaky actions (goal-transient-retry-20260815).

Provider rate limits (HTTP 429), timeouts, upstream 5xx responses, and DNS
resolution failures are transient: they can succeed on a later attempt and
must never be confused with a business or code failure. The loop consults
``is_transient`` when an ACT action raises, and — when the Goal configures a
``retry_policy`` — parks the run retryable instead of marking it FAILED for a
manual retry.

The taxonomy is intentionally closed: ``is_transient`` is True ONLY for the
classes below. Ordinary exceptions (``ValueError``, ``PermissionError``,
``RuntimeError``, builtin ``TimeoutError``, ...) are never transient, so real
bugs still fail the run exactly as before.
"""

from __future__ import annotations


class TransientError(Exception):
    """Base class for provider failures that may succeed on a later attempt."""


class RateLimitError(TransientError):
    """Provider rate limit / quota exhaustion (HTTP 429).

    ``retry_after`` optionally carries the provider's Retry-After value in
    seconds on the exception instance.
    """

    def __init__(self, message: str = "", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class TimeoutError(TransientError):
    """Provider request timed out (connect, read, or hung transport)."""


class UpstreamError(TransientError):
    """HTTP 5xx — the provider is failing on its side."""


class DNSError(TransientError):
    """DNS resolution failure (NXDOMAIN, dead resolver, VPN drop)."""


def is_transient(exc) -> bool:
    """True only for the transient taxonomy; ordinary exceptions are not."""
    return isinstance(exc, TransientError)
