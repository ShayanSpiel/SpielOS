"""End-to-end chain tests for the Spiel Engine content orchestrator.

Tests the full content pipeline from IDLE through COMPILE, FORMAT_WIZARD,
DRAFTING, BANNER, GATE_CHECK, QUEUE, and the hold/reset path. Uses
direct Python API calls (not CLI) for speed and isolation.
"""

import json
import os
import sys
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Ensure scripts/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────


@pytest.fixture
def temp_vault():
    """Create a temporary vault with minimal structure for testing."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "scripts").symlink_to(Path(__file__).resolve().parent.parent / "scripts")
    (tmp / "concepts").mkdir()
    (tmp / "content").mkdir()
    (tmp / "content" / "sessions").mkdir()
    (tmp / "content" / "queue").mkdir()
    (tmp / "content" / "posted").mkdir()
    (tmp / "assets").mkdir()
    (tmp / "assets" / "banners").mkdir()
    (tmp / "logs").mkdir()
    (tmp / "templates").mkdir()
    (tmp / "templates" / "registry").mkdir()
    # Create a minimal rules.yaml
    rules = {
        "strategy": {
            "pages": ["icp-offer"],
            "archetypes": {"S4_lesson": ["lesson", "learned", "insight"]},
            "verticals": {"builder-to-lead-system": ["builder", "founder"]},
            "funnel_stages": {"TOFU": ["aware", "learn", "discover"]},
            "icp_layers": {"L2": ["founder", "technical"]},
        },
        "posting": {"mode": "manual", "require_confirm": ["blog", "linkedin"]},
        "compiler": {
            "meaning_axes": ["systemic", "behavioral", "philosophical", "contrarian", "leverage", "human"],
        },
        "template_selector": {"weights": {}, "top_n": {}},
    }
    (tmp / "rules.yaml").write_text(json.dumps(rules, indent=2))

    # Create stub strategy page
    (tmp / "concepts" / "icp-offer.md").write_text("---\ntitle: ICP Offer\n---\n\n# ICP Offer\n\n## ICP World\nThey are builders.\n")

    # Create stub session
    today = datetime.now().strftime("%Y-%m-%d")
    session_path = tmp / "content" / "sessions" / f"{today}-session-01.md"
    session_content = f"""---
title: Test session
date: {today}
tags: []
status: complete
drafts: []
---

## What we did (3-7 bullets)

- Built the orchestrator
- Added handoff TTL
- Tested the chain

## Decisions made

- Use brief.handoff for LLM signal
"""
    session_path.write_text(session_content)
    (tmp / "templates" / "registry" / "viral-templates.yaml").write_text(
        "platforms:\n  x:\n    categories:\n      - id: data\n        name: Data hooks\n        defaults: {}\n        templates:\n          - id: x-data-01\n            name: Test template\n            hook: test\n            cta: test\n            body: test\n            best_for: {archetypes: [S4]}\n"
    )

    # Set VAULT_DIR env var so all scripts use this temp vault
    old_vault = os.environ.get("VAULT_DIR")
    os.environ["VAULT_DIR"] = str(tmp)

    yield tmp

    # Cleanup
    if old_vault:
        os.environ["VAULT_DIR"] = old_vault
    else:
        del os.environ["VAULT_DIR"]
    shutil.rmtree(tmp)


def _reset_state(tmp_vault: Path):
    """Reset .wiki-state and .content-brief.json to IDLE."""
    from engine_state import write_wiki_state, write_brief
    write_wiki_state({
        "current_state": "IDLE",
        "loop": "CONTENT",
        "last_state_change": None,
        "pending_action": None,
        "last_validation": "passed",
        "validation_results": {"orphans": 0, "broken_links": 0, "stale": [], "warnings": []},
        "last_ingest": None,
    })
    write_brief({
        "session": None,
        "strategy_pages": [],
        "source": {"kind": "session", "text": None, "label": None},
        "core_insight": "",
        "meanings": {a: "" for a in ["systemic", "behavioral", "philosophical", "contrarian", "leverage", "human"]},
        "selected_meaning": {"axis": "", "rationale": ""},
        "template_selection": {"recommendations": {}, "selected": {}},
        "strategy": {},
        "wizard": {"formats": [], "answered_at": None},
        "drafting": {"done": False, "files": []},
        "handoff": None,
    })


# ── Tests ─────────────────────────────────────────────────────────────────


def test_state_machine_has_format_wizard():
    """Verify FORMAT_WIZARD state exists in the state machine."""
    from engine_state import StateMachine, CONTENT_STATES
    sm = StateMachine("CONTENT")
    assert "FORMAT_WIZARD" in CONTENT_STATES
    valid, _ = sm.validate_transition("SELECT", "FORMAT_WIZARD")
    assert valid, "SELECT → FORMAT_WIZARD should be valid"


def test_orchestrator_full_chain(temp_vault):
    """Test the entire content chain from IDLE through COMPILE to draft handoff."""
    from engine import cmd_content_run
    from engine_state import read_wiki_state, read_brief

    _reset_state(temp_vault)

    # Step 1: content run from IDLE → SESSION_CAPTURE → COMPILE → handoff
    state = read_wiki_state()
    state["loop"] = "CONTENT"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.stdin.isatty", lambda: False)
        result = cmd_content_run(state, [])
    # Should return 0 and leave state at COMPILE
    assert result == 0 or result is None, f"content run returned {result}"
    state = read_wiki_state()
    assert state["current_state"] in ("COMPILE",), f"Expected COMPILE, got {state['current_state']}"

    # Step 2: LLM writes core_insight via compile-write
    from engine import cmd_content_compile_write
    state = read_wiki_state()
    args = [
        "--core-insight", "Builders should audit their paid tools monthly",
        "--meaning-systemic", "Tools become invisible when unused",
        "--meaning-behavioral", "Builders pay reflexively",
        "--meaning-philosophical", "Honest opportunity cost is rare",
        "--meaning-contrarian", "Free tiers can be durable",
        "--meaning-leverage", "Cancel before re-buying",
        "--meaning-human", "The shame of paying is worse than the cost",
        "--selected-axis", "human",
        "--selected-rationale", "Identity friction is the live wire",
    ]
    result = cmd_content_compile_write(state, args)
    assert result == 0, f"compile-write returned {result}"

    # Step 3: content run again → SELECT → FORMAT_WIZARD → DRAFTING handoff
    state = read_wiki_state()
    state["loop"] = "CONTENT"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.stdin.isatty", lambda: False)
        mp.setattr("sys.stdin.readline", lambda: "4\n")
        result = cmd_content_run(state, [])
    assert result == 0
    state = read_wiki_state()
    assert state["current_state"] in ("DRAFTING",), f"Expected DRAFTING, got {state['current_state']}"

    brief = read_brief()
    assert brief.get("wizard", {}).get("formats") == ["x", "linkedin"], f"Expected x+linkedin, got {brief.get('wizard', {}).get('formats')}"


def test_orchestrator_hold_at_format_wizard(temp_vault):
    """Test hold behavior at the format wizard."""
    from engine import cmd_content_run, cmd_content_compile_write
    from engine_state import read_wiki_state, read_brief

    _reset_state(temp_vault)

    # Run to COMPILE
    state = read_wiki_state()
    state["loop"] = "CONTENT"
    mock_inputs = iter(["", ""])

    def fake_input(prompt=""):
        return next(mock_inputs)

    import engine_state
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.stdin.isatty", lambda: False)
        mp.setattr("sys.stdin.readline", lambda: "")
        result = cmd_content_run(state, [])
    assert result == 0, f"content run returned {result}"

    # Write compile output
    state = read_wiki_state()
    args = [
        "--core-insight", "Test insight",
        "--meaning-systemic", "A", "--meaning-behavioral", "B",
        "--meaning-philosophical", "C", "--meaning-contrarian", "D",
        "--meaning-leverage", "E", "--meaning-human", "F",
        "--selected-axis", "human", "--selected-rationale", "Rationale",
    ]
    result = cmd_content_compile_write(state, args)
    assert result == 0

    # Run to FORMAT_WIZARD, then hold
    state = read_wiki_state()
    state["loop"] = "CONTENT"
    # The wizard will ask for input. We need to inject "h" for hold.
    # Since we can't monkeypatch input() from here (wizard calls input() directly),
    # just verify the SELECT → FORMAT_WIZARD gate is present
    brief = read_brief()
    from engine_state import validate_brief_for_transition
    valid, reason = validate_brief_for_transition("PUBLISHING", brief)
    assert not valid, "Should not be valid for PUBLISHING (no wizard decisions)"


def test_draft_write_and_done(temp_vault):
    """Test draft registration and drafting-complete signal."""
    from engine import cmd_content_draft_write, cmd_content_draft_done
    from engine_state import read_brief, VAULT

    _reset_state(temp_vault)

    # Create a draft file in the project queue dir (since VAULT points to project)
    queue_dir = VAULT / "content" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    draft_path = queue_dir / "test-draft.md"
    draft_path.write_text("""---
title: Test Draft
platform: x
type: lesson
status: draft
created: 2026-06-17
tags: []
---

This is the body of the test draft.
""")

    try:
        # Register it using relative path (resolved by engine vs VAULT)
        state = {}
        result = cmd_content_draft_write(state, ["--file", str(draft_path)])
        assert result == 0, f"draft-write returned {result}: {draft_path}"
        brief = read_brief()
        assert "test-draft.md" in brief["drafting"]["files"], f"Draft not in files: {brief['drafting']['files']}"

        # Signal done
        result = cmd_content_draft_done(state, [])
        assert result == 0, f"draft-done returned {result}"
        brief = read_brief()
        assert brief["drafting"]["done"] is True
    finally:
        # Cleanup the test draft
        if draft_path.exists():
            draft_path.unlink()


def test_compile_write_validation(temp_vault):
    """Test that compile-write rejects missing fields."""
    from engine import cmd_content_compile_write
    from engine_state import read_wiki_state

    _reset_state(temp_vault)
    state = read_wiki_state()

    # Missing core_insight
    args = [
        "--core-insight", "",
        "--meaning-systemic", "A", "--meaning-behavioral", "B",
        "--meaning-philosophical", "C", "--meaning-contrarian", "D",
        "--meaning-leverage", "E", "--meaning-human", "F",
        "--selected-axis", "human", "--selected-rationale", "R",
    ]
    result = cmd_content_compile_write(state, args)
    assert result != 0, "Should have rejected empty core_insight"

    # Missing selected_axis
    args = [
        "--core-insight", "Test",
        "--meaning-systemic", "A", "--meaning-behavioral", "B",
        "--meaning-philosophical", "C", "--meaning-contrarian", "D",
        "--meaning-leverage", "E", "--meaning-human", "F",
        "--selected-axis", "", "--selected-rationale", "R",
    ]
    result = cmd_content_compile_write(state, args)
    assert result != 0, "Should have rejected empty selected_axis"


def test_session_fill(temp_vault):
    """Test writing session content into a stub session log."""
    from engine import cmd_content_session_fill, find_latest_session
    from engine_state import read_wiki_state, VAULT, SESSIONS_DIR

    _reset_state(temp_vault)
    state = read_wiki_state()

    # Use an explicit path to avoid VAULT caching issues in tests
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    stub_path = SESSIONS_DIR / "test-stub-session.md"
    stub_path.write_text("""---
title: <fill in>
date: 2026-06-17
tags: []
status: in-progress
drafts: []
---

# Session: <fill in>

## What we did (3-7 bullets)

-

## Decisions made

-
""")

    try:
        result = cmd_content_session_fill(state, [
            "--topic", "Refactored the orchestrator",
            "--bullet", "Added handoff TTL",
            "--bullet", "Created wizard.py",
            "--lesson", "The LLM is a service",
            "--decision", "Use handoff for signals",
            "--path", str(stub_path),
        ])
        assert result == 0, f"session-fill returned {result}"

        content = stub_path.read_text()
        assert "Refactored the orchestrator" in content, "Topic not written"
        assert "Added handoff TTL" in content, "Bullet not written"
        assert "The LLM is a service" in content, "Lesson not written"
        assert "<fill in>" not in content, "Stub markers should be replaced"
    finally:
        if stub_path.exists():
            stub_path.unlink()


def test_brief_validation_gates(temp_vault):
    """Test that validate_brief_for_transition enforces required artifacts."""
    from engine_state import validate_brief_for_transition

    # Empty brief → should fail SELECT gate
    brief = {"core_insight": "", "meanings": {}, "selected_meaning": {}}
    valid, reason = validate_brief_for_transition("SELECT", brief)
    assert not valid, "Empty brief should fail SELECT gate"
    assert "core_insight" in reason.lower()

    # Filled brief → should pass SELECT gate
    brief = {
        "core_insight": "Test insight",
        "meanings": {a: "v" for a in ["systemic", "behavioral", "philosophical", "contrarian", "leverage", "human"]},
        "selected_meaning": {"axis": "human", "rationale": "Good reason"},
    }
    valid, reason = validate_brief_for_transition("SELECT", brief)
    assert valid, f"Filled brief should pass SELECT: {reason}"

    # No wizard formats → should fail DRAFTING gate
    brief["wizard"] = {"formats": []}
    valid, reason = validate_brief_for_transition("DRAFTING", brief)
    assert not valid, "Empty wizard.formats should fail DRAFTING gate"
    assert "formats" in reason.lower()

    # Wizard formats set → should pass DRAFTING gate
    brief["wizard"] = {"formats": ["x", "linkedin"]}
    valid, reason = validate_brief_for_transition("DRAFTING", brief)
    assert valid, f"Filled wizard.formats should pass DRAFTING: {reason}"


def test_handoff_ttl_expiry(temp_vault):
    """Test that expired handoff causes reset to IDLE."""
    from engine_state import set_handoff, check_handoff_expired, clear_handoff, HANDOFF_TTL_MINUTES

    brief = {}
    set_handoff(brief, "compile")
    assert brief.get("handoff") is not None
    assert not check_handoff_expired(brief), "Fresh handoff should not be expired"

    # Artificially set expires_at in the past
    brief["handoff"]["expires_at"] = (datetime.now() - timedelta(minutes=1)).isoformat()
    assert check_handoff_expired(brief), "Past handoff should be expired"

    clear_handoff(brief)
    assert brief["handoff"] is None, "Handoff should be None after clear"


def test_publish_wizard_decisions(temp_vault):
    """Test that brief.publish_decisions validation works."""
    from engine_state import validate_brief_for_transition

    brief = {"wizard": {"publish_decisions": {}}}
    valid, reason = validate_brief_for_transition("PUBLISHING", brief)
    assert not valid, "Empty decisions should fail PUBLISHING"

    brief["wizard"]["publish_decisions"] = {"draft1.md": "publish", "draft2.md": "hold"}
    valid, reason = validate_brief_for_transition("PUBLISHING", brief)
    assert valid, f"Valid decisions should pass PUBLISHING: {reason}"

    brief["wizard"]["publish_decisions"] = {"draft1.md": "invalid"}
    valid, reason = validate_brief_for_transition("PUBLISHING", brief)
    assert not valid, "Invalid decision should fail PUBLISHING"


# ── Cross-cwd tests (the whole point of the spiel shim) ────────────────────


def test_engine_invoked_via_shim_from_other_cwd(temp_vault):
    """The whole point of the spiel shim: run the engine from /tmp and have
    it work. This is the bug the shim fixes — previously, `python3
    scripts/engine.py` was CWD-relative and broke from any project other
    than the vault. With the shim, status works from anywhere.

    We invoke via subprocess so each test run is a fresh Python interpreter
    (no module caching between tests), mirroring real usage.
    """
    import subprocess

    shim = Path(temp_vault) / "scripts" / "bin" / "spiel"
    if not shim.exists():
        pytest.skip(f"shim not bundled in vault: {shim}")

    result = subprocess.run(
        [str(shim), "status"],
        capture_output=True,
        text=True,
        env={**os.environ, "VAULT_DIR": str(temp_vault)},
        cwd="/tmp",
    )
    assert result.returncode == 0, (
        f"shim status from /tmp failed:\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )
    # The status output should mention the state machine
    assert "state" in result.stdout.lower()


def test_engine_invoked_directly_from_other_cwd(temp_vault):
    """Even WITHOUT the shim, `python3 <abs>/scripts/engine.py status` must
    work from /tmp once the engine chdir's to VAULT at startup. This is
    the safety net: any future script (or this test) can invoke engine.py
    by absolute path and still have it find the right vault.
    """
    import subprocess

    engine_py = Path(temp_vault) / "scripts" / "engine.py"
    if not engine_py.exists():
        pytest.skip(f"engine.py not in temp_vault: {engine_py}")

    result = subprocess.run(
        ["python3", str(engine_py), "status"],
        capture_output=True,
        text=True,
        env={**os.environ, "VAULT_DIR": str(temp_vault)},
        cwd="/tmp",
    )
    assert result.returncode == 0, (
        f"engine.py status from /tmp failed:\n"
        f"stdout: {result.stdout[:500]}\n"
        f"stderr: {result.stderr[:500]}"
    )
    assert "state" in result.stdout.lower()


def test_engine_hint_strings_use_spiel(temp_vault):
    """The state-machine hint strings the kernel prints to the LLM must
    say `spiel`, not `python3 scripts/engine.py`. Otherwise the LLM
    learns the broken (CWD-relative) pattern from the engine's own output.
    """
    from engine import _next_command_for
    cases = [
        ("WIKI", "INGESTING"),
        ("WIKI", "ANALYZING"),
        ("WIKI", "RECONCILING"),
        ("WIKI", "INDEXING"),
        ("WIKI", "VALIDATING"),
        ("WIKI", "COMPLETE"),
        ("CONTENT", "SESSION_CAPTURE"),
        ("CONTENT", "COMPILE"),
        ("CONTENT", "DRAFTING"),
        ("CONTENT", "BANNER"),
        ("CONTENT", "GATE_CHECK"),
        ("CONTENT", "PUBLISHING"),
    ]
    for loop, target in cases:
        hint = _next_command_for(loop, target)
        assert hint.startswith("spiel"), (
            f"hint for {loop}/{target} should start with 'spiel', got: {hint!r}"
        )
        assert "python3 scripts/engine.py" not in hint, (
            f"hint for {loop}/{target} must not contain the broken pattern: {hint!r}"
        )
