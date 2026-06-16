"""Tests for scripts/state_machine.py + engine.py"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from state_machine import (
    StateMachine,
    WIKI_TRANSITIONS,
    CONTENT_TRANSITIONS,
    WIKI_STATES,
    CONTENT_STATES,
    ALL_STATES,
    read_wiki_state,
    write_wiki_state,
)
from engine import print_next, WIKI_NEXT, CONTENT_NEXT


class TestStateMachine:
    def test_wiki_full_pipeline(self):
        """Test the full wiki pipeline transition sequence."""
        sm = StateMachine("WIKI")
        pipeline = ["IDLE", "INGESTING", "ANALYZING", "RECONCILING", "INDEXING", "VALIDATING", "COMPLETE", "IDLE"]
        for i in range(len(pipeline) - 1):
            valid, _ = sm.validate_transition(pipeline[i], pipeline[i + 1])
            assert valid, f"Failed: {pipeline[i]} -> {pipeline[i + 1]}"

    def test_content_full_pipeline(self):
        """Test the full content pipeline transition sequence."""
        sm = StateMachine("CONTENT")
        pipeline = [
            "IDLE", "SESSION_CAPTURE", "STRATEGY_LOAD", "ICP_WORLD_BUILD",
            "DRAFTING", "GATE_CHECK", "QUEUE", "PUBLISHING", "ARCHIVING",
            "ANALYZING_POST", "COMPLETE_POST", "IDLE"
        ]
        for i in range(len(pipeline) - 1):
            valid, _ = sm.validate_transition(pipeline[i], pipeline[i + 1])
            assert valid, f"Failed: {pipeline[i]} -> {pipeline[i + 1]}"

    def test_invalid_transitions(self):
        """Test that invalid transitions are rejected."""
        sm = StateMachine("WIKI")
        invalid_pairs = [
            ("IDLE", "DRAFTING"),
            ("IDLE", "SESSION_CAPTURE"),
            ("ANALYZING", "VALIDATING"),
            ("COMPLETE", "INGESTING"),
            ("INGESTING", "QUEUE"),
        ]
        for current, target in invalid_pairs:
            valid, reason = sm.validate_transition(current, target)
            assert not valid, f"Should have rejected: {current} -> {target}"

    def test_content_to_wiki_isolation(self):
        """Content states should not be valid in wiki loop."""
        sm = StateMachine("WIKI")
        for content_state in ["SESSION_CAPTURE", "DRAFTING", "QUEUE"]:
            valid, _ = sm.validate_transition("IDLE", content_state)
            assert not valid, f"Content state {content_state} should be invalid in wiki loop"

    def test_all_states_in_transition_table(self):
        """Every state should appear in at least one transition entry."""
        states_in_transitions = set(WIKI_TRANSITIONS.keys()) | set(CONTENT_TRANSITIONS.keys())
        for s in ALL_STATES:
            assert s in states_in_transitions, f"State {s} not in any transition table"

    def test_transitions_are_valid_states(self):
        """Every transition target should be a valid state."""
        all_transitions = {}
        for s, nexts in WIKI_TRANSITIONS.items():
            all_transitions.setdefault(s, []).extend(nexts)
        for s, nexts in CONTENT_TRANSITIONS.items():
            all_transitions.setdefault(s, []).extend(nexts)
        for current, targets in all_transitions.items():
            assert current in ALL_STATES, f"Current state {current} not in ALL_STATES"
            for t in targets:
                assert t in ALL_STATES, f"Target {t} (from {current}) not in ALL_STATES"

    def test_no_dead_ends(self):
        """Every non-terminal state should have at least one transition out."""
        terminal_states = {"IDLE", "COMPLETE", "COMPLETE_POST"}
        for state in WIKI_STATES:
            if state not in terminal_states:
                assert WIKI_TRANSITIONS.get(state), f"Wiki state {state} has no outgoing transitions"
        for state in CONTENT_STATES:
            if state not in terminal_states:
                assert CONTENT_TRANSITIONS.get(state), f"Content state {state} has no outgoing transitions"


class TestWikiStateFile:
    def test_read_state_default(self):
        """read_wiki_state should return defaults for missing file."""
        state = read_wiki_state()
        assert "current_state" in state
        assert "loop" in state
        assert "validation_results" in state

    def test_default_state_is_idle(self):
        """Default state should be IDLE."""
        state = read_wiki_state()
        assert state["current_state"] == "IDLE"

    def test_validation_results_structure(self):
        """validation_results should have expected keys."""
        state = read_wiki_state()
        v = state.get("validation_results", {})
        assert "orphans" in v
        assert "broken_links" in v
        assert "stale" in v
        assert "warnings" in v


class TestPrintNext:
    def test_wiki_next_has_all_states(self):
        """Every non-terminal wiki state should have an entry in WIKI_NEXT."""
        terminal = {"IDLE", "COMPLETE"}
        for state in WIKI_STATES:
            if state in terminal:
                continue
            assert state in WIKI_NEXT, f"WIKI_NEXT missing: {state}"
            assert len(WIKI_NEXT[state]) > 0, f"WIKI_NEXT[{state}] has no commands"

    def test_content_next_has_all_states(self):
        """Every non-terminal content state should have an entry in CONTENT_NEXT."""
        terminal = {"IDLE", "COMPLETE_POST"}
        for state in CONTENT_STATES:
            if state in terminal:
                continue
            assert state in CONTENT_NEXT, f"CONTENT_NEXT missing: {state}"
            assert len(CONTENT_NEXT[state]) > 0, f"CONTENT_NEXT[{state}] has no commands"

    def test_wiki_next_entry_format(self):
        """Each WIKI_NEXT entry should be (cmd, label) pairs."""
        for state, entries in WIKI_NEXT.items():
            for entry in entries:
                assert len(entry) == 2, f"WIKI_NEXT[{state}] entry has wrong length: {entry}"
                cmd, label = entry
                assert isinstance(cmd, str) and len(cmd) > 0, f"WIKI_NEXT[{state}] bad cmd: {cmd}"
                assert isinstance(label, str) and len(label) > 0, f"WIKI_NEXT[{state}] bad label: {label}"

    def test_content_next_entry_format(self):
        """Each CONTENT_NEXT entry should be (cmd, label) pairs."""
        for state, entries in CONTENT_NEXT.items():
            for entry in entries:
                assert len(entry) == 2, f"CONTENT_NEXT[{state}] entry has wrong length: {entry}"
                cmd, label = entry
                assert isinstance(cmd, str) and len(cmd) > 0, f"CONTENT_NEXT[{state}] bad cmd: {cmd}"
                assert isinstance(label, str) and len(label) > 0, f"CONTENT_NEXT[{state}] bad label: {label}"

    def test_print_next_idle_prints_nothing(self, capsys):
        """IDLE state should produce no output."""
        print_next({"loop": "WIKI", "current_state": "IDLE"})
        captured = capsys.readouterr()
        assert captured.out == ""

        print_next({"loop": "CONTENT", "current_state": "IDLE"})
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_next_wiki_ingesting(self, capsys):
        """INGESTING state should print a NEXT banner with wiki-analyze."""
        print_next({"loop": "WIKI", "current_state": "INGESTING"})
        captured = capsys.readouterr()
        assert "bash scripts/pipeline.sh wiki-analyze" in captured.out
        assert "NEXT" in captured.out
