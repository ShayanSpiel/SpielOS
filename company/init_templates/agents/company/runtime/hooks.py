"""Generic post-transition hook — the website-decoupling seam.

The runtime used to hardcode this repository's website deploy pipeline
(regenerate ``src/data/live-goals.json``, git add/commit/push) directly into
its goal-transition hot path. That coupling is gone: after every persisted
transition the loop calls :func:`run_transition_hook`, which is a no-op unless
the ``SPIELOS_TRANSITION_HOOK`` environment variable (with a fallback read of
``.spielos/.env``, mirroring the retired live-push gate) names a shell command
template.

Template substitution (plain string replace):

* ``{event}`` — the event name, shell-quoted (currently ``goal_transition``).
* ``{payload_json}`` — the JSON payload, shell-quoted.

Contract:

* Disabled by default (env var unset/empty -> immediate no-op).
* Best-effort: any failure (missing binary, non-zero exit, timeout, bad
  JSON) is logged as a warning and never propagates into the loop.
* Hard-bounded: a hanging hook is killed after ``DEFAULT_TIMEOUT_S`` seconds,
  so a wedged network or filesystem can never block a goal transition.
* Debounce/fingerprint/marker semantics live in the hook script (see
  ``scripts/spielos-transition-hook.sh``), never in the runtime.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger("company.runtime.hooks")

HOOK_ENV = "SPIELOS_TRANSITION_HOOK"
# Fallback dotenv file beside the runtime state, matching the old live-push
# gate semantics: environment variable wins; the file is only consulted when
# the variable is unset. Empty/unset everywhere => hook disabled by default.
HOOK_ENV_FILE = Path(".spielos/.env")
DEFAULT_TIMEOUT_S = 20.0


def _hook_template() -> str:
    raw = os.environ.get(HOOK_ENV)
    if raw is None:
        try:
            lines = HOOK_ENV_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            if name.strip() == HOOK_ENV:
                return value.strip()
        return ""
    return raw.strip()


def run_transition_hook(event: str, payload: dict, *,
                        timeout: float | None = None) -> dict | None:
    """Run the configured transition hook once; return its result or None.

    Returns None when the hook is disabled or failed; otherwise a small dict
    with ``returncode``. Never raises.
    """
    template = _hook_template()
    if not template:
        return None
    limit = DEFAULT_TIMEOUT_S if timeout is None else timeout
    command = template.replace(
        "{event}", shlex.quote(event)).replace(
        "{payload_json}", shlex.quote(json.dumps(payload, default=str)))
    try:
        completed = subprocess.run(command, shell=True, capture_output=True,
                                   text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        logger.warning("transition hook skipped (timed out after %ss)", limit)
        return None
    except Exception as exc:  # best-effort; never breaks a goal transition
        logger.warning("transition hook skipped (non-fatal): %s", exc)
        return None
    if completed.returncode != 0:
        logger.warning("transition hook exited %s (non-fatal): %s",
                       completed.returncode, (completed.stderr or "").strip())
    return {"returncode": completed.returncode}
