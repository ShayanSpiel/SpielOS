"""tests/test_state_machine.py — Verify the state machine table is valid."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_state_table() -> list[dict]:
    """Parse the state table in system/state-machine.md into a list of dicts."""
    text = (ROOT / "system" / "state-machine.md").read_text()
    rows = []
    in_table = False
    for line in text.splitlines():
        line = line.rstrip()
        if not in_table:
            if line.startswith("| #") or line.startswith("| State"):
                in_table = True
                continue
            else:
                continue
        if line.startswith("|---") or line.startswith("| #"):
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 6:
            continue
        rows.append({
            "num": cols[0],
            "state": cols[1],
            "from": cols[2],
            "role": cols[3],
            "output_check": cols[4],
            "next": cols[5],
        })
    return rows


def test_all_states_present():
    expected = {
        "IDLE", "SESSION_CAPTURE", "COMPILE", "SELECT", "FORMAT_WIZARD",
        "DRAFTING", "BANNER", "GATE_CHECK", "PUBLISH_REVIEW", "PUBLISHING",
        "ANALYZING_POST", "COMPLETE_POST",
    }
    rows = parse_state_table()
    states = {r["state"] for r in rows}
    missing = expected - states
    assert not missing, f"missing states: {missing}"


def test_each_state_has_role():
    rows = parse_state_table()
    for r in rows:
        assert r["role"], f"state {r['state']} has no role"


def test_transitions_chain():
    """Each state should have a valid 'from' that appears earlier in the table."""
    rows = parse_state_table()
    state_to_from = {r["state"]: r["from"] for r in rows}
    # IDLE has no from
    for s, f in state_to_from.items():
        if s == "IDLE":
            continue
        assert f in state_to_from, f"state {s} has from='{f}' which is not a known state"


def test_terminal_state():
    """COMPLETE_POST should transition back to IDLE."""
    rows = parse_state_table()
    cp = next(r for r in rows if r["state"] == "COMPLETE_POST")
    assert "IDLE" in cp["next"], f"COMPLETE_POST should transition to IDLE, got {cp['next']}"


if __name__ == "__main__":
    # Allow running without pytest
    funcs = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for f in funcs:
        try:
            f()
            print(f"  ✓ {f.__name__}")
        except AssertionError as e:
            print(f"  ✗ {f.__name__}: {e}")
            failed += 1
    sys.exit(1 if failed else 0)
