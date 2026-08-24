"""Acceptance tests for goal-transient-retry-20260815 (change_kind=repair).

Problem statement (the spec): "Provider rate limits, timeouts, 5xx, DNS
failures mark runs FAILED requiring manual retry; no transient classification,
no retry_policy config, no watcher auto-retry."

Intended API contract (implementer must make every test pass by editing ONLY
`company/runtime/models.py`, `company/runtime/errors.py`,
`company/runtime/loop.py`,
`company/departments/outbound/execution.py`):

1. Transient classification — `company.runtime.errors` (NEW module):
   - `class TransientError(Exception)`                — base for all transient failures.
   - `class RateLimitError(TransientError)`           — provider rate limits / HTTP 429.
   - `class TimeoutError(TransientError)`             — provider timeouts.
   - `class UpstreamError(TransientError)`            — HTTP 5xx.
   - `class DNSError(TransientError)`                 — DNS resolution failures.
   - `is_transient(exc) -> bool`                      — True only for the transient
                                                       taxonomy above; False for
                                                       ordinary exceptions such as
                                                       ValueError / PermissionError.
   - optional `retry_after(exc) -> float | None`      — seconds to wait (429).

2. `retry_policy` goal config — `goal.config["retry_policy"]`:
     {"max_retries": int, "backoff_seconds": float}
   `max_retries` = retries AFTER the first failure (total attempts = max_retries+1).
   `backoff_seconds` = delay before each retry. Unknown transient failures with
   no retry_policy keep today's behavior: the run goes FAILED (manual retry).

3. Loop behavior — when an ACT action raises a transient error:
   - with retry_policy configured, the run NEVER jumps straight to FAILED.
     It parks retryable (run_status "waiting", resume_at = now + backoff, or a
     retryable FAILED that `Runtime.once`/runner automatically retries), so the
     next automatic Runner tick retries the action without a manual
     `company retry` (watcher auto-retry). Backoff is SCHEDULED (resume_at),
     never slept through in-process.
   - attempts count against max_retries; when exhausted the run goes FAILED.
   - non-transient errors are never retried, with or without retry_policy.

Tests marked `# passes now` pin existing behavior. Tests marked
`# expected after implementation` fail until the implementation lands;
tests that need the new `company.runtime.errors` module report a SKIP (never
an import error) until that module exists.
"""

import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from company.runtime.loop import Runtime  # noqa: E402
from company.runtime.models import (  # noqa: E402
    GoalHandler, GoalStatus, RunStatus, Stage, StageResult,
)
from company.runtime.runner import Runner  # noqa: E402


def _errors_module():
    """Return company.runtime.errors or raise unittest.SkipTest.

    The module is a deliverable of this goal; until it exists these tests
    cannot construct a transient failure, so they skip instead of erroring.
    """
    try:
        from company.runtime import errors
    except ImportError as exc:
        raise unittest.SkipTest(
            "company.runtime.errors does not exist yet: %s" % exc)
    return errors


class TransientHandler(GoalHandler):
    """ACT raises `error_type` on attempts 1..succeed_after; later attempts work."""

    id = "transient_test"

    def __init__(self, error_type=None, succeed_after=None):
        self.attempts = 0
        self.error_type = error_type
        self.succeed_after = succeed_after

    def observe(self, ctx):
        return StageResult("collect", {})

    def decide(self, ctx, observation):
        return StageResult("diagnose", {"action": "provider_call"})

    def act(self, ctx, decision):
        self.attempts += 1
        if self.error_type is not None and (
                self.succeed_after is None or self.attempts <= self.succeed_after):
            raise self.error_type("provider failure on attempt %d" % self.attempts)
        return StageResult("execute", {"ok": True, "attempt": self.attempts})

    def evaluate(self, ctx, action_result):
        validity = (ctx.cycle.get("run") or {}).get("evidence_validity") or "business"
        return StageResult(
            "goal_check", {"done": True}, RunStatus.IDLE,
            goal_status=GoalStatus.ACHIEVED,
            evaluation={"verdict": "goal_met", "goal_met": True,
                        "metrics": {ctx.goal.metric: True}, "validity": validity})


class TransientClassificationTests(unittest.TestCase):
    def test_transient_taxonomy_and_classifier(self):  # expected after implementation
        errors = _errors_module()
        transients = [errors.RateLimitError("429"),
                      errors.TimeoutError("timeout"),
                      errors.UpstreamError("502"),
                      errors.DNSError("NXDOMAIN")]
        for exc in transients:
            self.assertTrue(errors.is_transient(exc),
                            "%r must classify as transient" % type(exc).__name__)
            self.assertIsInstance(exc, errors.TransientError)
        for exc in (ValueError("nope"), PermissionError("denied"),
                    RuntimeError("boom")):
            self.assertFalse(errors.is_transient(exc),
                             "%r must NOT classify as transient" % type(exc).__name__)


class TransientRetryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.errors = _errors_module()  # SkipTest here when module is missing

    def runtime(self, handler=None):
        handler = handler or TransientHandler(
            error_type=self.errors.RateLimitError, succeed_after=1)
        return Runtime(Path(self.temp.name) / "state.sqlite",
                       {"transient_test": handler})

    def goal(self, runtime, retry_policy=None, config_extra=None):
        config = dict(config_extra or {})
        if retry_policy is not None:
            config["retry_policy"] = retry_policy
        return runtime.create_goal(name="Retry", owner_id="transient_test",
                                   metric="done", operator="eq", target=True,
                                   config=config)

    def test_single_transient_failure_auto_retries_to_success(self):  # expected after implementation
        handler = TransientHandler(error_type=self.errors.RateLimitError,
                                   succeed_after=1)
        runtime = self.runtime(handler)
        goal = self.goal(runtime, retry_policy={"max_retries": 2,
                                                "backoff_seconds": 0})
        runtime.once(goal["id"])  # first attempt fails transiently (handled)
        result = Runner(runtime).tick(goal["id"])
        state = runtime.status(goal["id"])
        self.assertEqual(state["goal"]["goal_status"], "achieved",
                         "watcher auto-retry must finish the run without a "
                         "manual `company retry`")
        self.assertNotEqual(state["cycle"]["run_status"], "failed")
        self.assertEqual(handler.attempts, 2,
                         "exactly one retry after the initial failure")

    def test_transient_failure_without_policy_fails_fast(self):  # expected after implementation
        handler = TransientHandler(error_type=self.errors.RateLimitError)
        runtime = self.runtime(handler)
        goal = self.goal(runtime)  # no retry_policy -> legacy manual-retry world
        runtime.once(goal["id"])
        state = runtime.status(goal["id"])
        self.assertEqual(state["cycle"]["run_status"], "failed",
                         "without retry_policy the run stays FAILED for manual retry")
        self.assertEqual(handler.attempts, 1)

    def test_transient_failure_exhausts_max_retries_then_fails(self):  # expected after implementation
        handler = TransientHandler(error_type=self.errors.RateLimitError)
        runtime = self.runtime(handler)
        goal = self.goal(runtime, retry_policy={"max_retries": 1,
                                                "backoff_seconds": 0})
        runtime.once(goal["id"])  # initial failure (retryable)
        Runner(runtime).tick(goal["id"])  # one auto retry -> fails again
        state = runtime.status(goal["id"])
        self.assertEqual(state["cycle"]["run_status"], "failed",
                         "max_retries exhausted must land in FAILED")
        self.assertEqual(handler.attempts, 2,
                         "max_retries=1 means 1 retry after the initial failure")

    def test_backoff_is_scheduled_not_slept(self):  # expected after implementation
        handler = TransientHandler(error_type=self.errors.RateLimitError)
        runtime = self.runtime(handler)
        goal = self.goal(runtime, retry_policy={"max_retries": 3,
                                                "backoff_seconds": 60})
        now = datetime.now(timezone.utc)
        runtime.once(goal["id"])
        cycle = runtime.store.cycle(goal["id"])
        self.assertEqual(cycle["run_status"], "waiting",
                         "the retry delay must park the run in WAITING, not FAILED")
        resume_at = datetime.fromisoformat(cycle["resume_at"])
        self.assertGreaterEqual(resume_at, now + timedelta(seconds=30),
                                "resume_at must reflect the backoff delay")
        # A tick before the delay elapses must NOT retry (no busy-loop).
        Runner(runtime).tick(goal["id"])
        self.assertEqual(handler.attempts, 1)
        self.assertEqual(runtime.store.cycle(goal["id"])["run_status"], "waiting")

    def test_non_transient_error_is_never_retried(self):  # expected after implementation
        handler = TransientHandler(error_type=ValueError, succeed_after=None)
        runtime = self.runtime(handler)
        goal = self.goal(runtime, retry_policy={"max_retries": 5,
                                                "backoff_seconds": 0})
        runtime.once(goal["id"])
        state = runtime.status(goal["id"])
        self.assertEqual(state["cycle"]["run_status"], "failed",
                         "non-transient failures must not be retried")
        self.assertEqual(handler.attempts, 1)

    def test_watcher_auto_retries_without_manual_retry(self):  # expected after implementation
        handler = TransientHandler(error_type=self.errors.RateLimitError,
                                   succeed_after=1)
        runtime = self.runtime(handler)
        goal = self.goal(runtime, retry_policy={"max_retries": 3,
                                                "backoff_seconds": 0})
        runtime.once(goal["id"])  # first attempt fails (retryable)
        watched = []
        with unittest.mock.patch("company.runtime.runner.time.sleep"):
            for item in Runner(runtime).watch(
                    interval_seconds=0.1, goal_id=goal["id"], max_ticks=3):
                watched.append(item)
        state = runtime.status(goal["id"])
        self.assertEqual(state["goal"]["goal_status"], "achieved",
                         "the watcher must recover the run without any manual retry")
        self.assertEqual(handler.attempts, 2)


class RetryPolicyConfigTests(unittest.TestCase):
    def test_retry_policy_key_is_consumed_from_goal_config(self):  # passes now
        """The config key carries through goal creation today; only the loop
        side (transient handling) is delivered by this goal."""
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(Path(directory) / "state.sqlite",
                              {"transient_test": TransientHandler()})
            goal = runtime.create_goal(
                name="Retry", owner_id="transient_test", metric="done",
                operator="eq", target=True,
                config={"retry_policy": {"max_retries": 2, "backoff_seconds": 1}})
            self.assertEqual({"max_retries": 2, "backoff_seconds": 1},
                             runtime.store.goal(goal["id"])["config"]["retry_policy"])


if __name__ == "__main__":
    unittest.main()