"""Analytics Department.

Read-only PostHog warehouse reads and funnel consumption live in `posthog.py`;
the Department package (`department.py`) remains the declarative Lego surface.
"""

from .posthog import (
    BATCH_JOIN_KEYS,
    FUNNEL_EVENTS,
    PostHogClient,
    PostHogError,
    consume_batch_evidence,
    posthog_token,
)

__all__ = [
    "BATCH_JOIN_KEYS",
    "FUNNEL_EVENTS",
    "PostHogClient",
    "PostHogError",
    "consume_batch_evidence",
    "posthog_token",
]