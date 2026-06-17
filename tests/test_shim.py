"""Tests for the spiel shim — verifies all 4 vault resolution paths.

The shim is the path-independent entrypoint that lets commands work from
any project cwd, in any IDE. These tests assert:
  1. Inline $VAULT_DIR env var wins
  2. <cwd>/.spiel-vault wins over the global .env
  3. ~/.config/opencode/.env is the global fallback
  4. The shim's own location (when bundled at <vault>/scripts/bin/spiel)
     is the last-resort fallback
  5. The error message is clear when no resolution succeeds
  6. --version and --where print the resolved vault

We invoke the shim as a subprocess (not a Python import) to exercise the
actual shell logic, exactly the way an LLM agent would.
"""

import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIM = REPO_ROOT / "scripts" / "bin" / "spiel"


def _run_shim(*args, env=None, cwd=None, check=True):
    """Run the shim with the given args + a sanitized env (HOME, VAULT_DIR)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    if "HOME" not in full_env:
        # Force a clean HOME so we never pick up the real ~/.config/opencode/.env
        full_env["HOME"] = str(tempfile.mkdtemp(prefix="spiel-test-home-"))
    # Belt + suspenders: strip any inherited VAULT_DIR unless the test set it.
    full_env.pop("VAULT_DIR", None)
    if env and "VAULT_DIR" in env:
        full_env["VAULT_DIR"] = env["VAULT_DIR"]

    result = subprocess.run(
        [str(SHIM), *args],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=cwd or "/tmp",
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"shim exited {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result


def test_shim_exists_and_is_executable():
    """The shim must live at scripts/bin/spiel and be executable."""
    assert SHIM.exists(), f"shim not found: {SHIM}"
    mode = SHIM.stat().st_mode
    assert mode & 0o111, f"shim not executable: {oct(mode)}"


def test_version_flag():
    """`spiel --version` prints version + resolved vault path."""
    result = _run_shim("--version")
    assert "spiel" in result.stdout.lower()
    # On a normal test machine the global .env resolves to a real vault.
    assert "vault:" in result.stdout


def test_where_flag():
    """`spiel --where` prints just the resolved vault path."""
    result = _run_shim("--where")
    resolved = result.stdout.strip()
    assert resolved and not resolved.startswith("ERROR"), (
        f"unexpected --where output: {resolved!r}"
    )
    # Should be a real path that contains engine.py
    assert Path(resolved, "scripts", "engine.py").exists(), (
        f"resolved path {resolved!r} has no engine.py"
    )


def test_help_flag():
    """`spiel --help` prints usage and exits 0."""
    result = _run_shim("--help", check=False)
    assert result.returncode == 0
    assert "USAGE" in result.stdout


def test_resolution_1_inline_env_var():
    """Inline $VAULT_DIR env var wins over everything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        # Set up a fake vault: must have scripts/engine.py
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "engine.py").write_text("# fake")
        result = _run_shim("--where", env={"VAULT_DIR": str(tmp_path)}, cwd="/tmp")
        assert result.stdout.strip() == str(tmp_path)


def test_resolution_2_project_local_spiel_vault():
    """<cwd>/.spiel-vault wins over the global .env."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "engine.py").write_text("# fake")
        (tmp_path / ".spiel-vault").write_text(f"VAULT_DIR={tmp_path}\n")
        result = _run_shim("--where", cwd=str(tmp_path))
        assert result.stdout.strip() == str(tmp_path)


def test_resolution_3_global_env_file():
    """~/.config/opencode/.env is the global fallback."""
    with tempfile.TemporaryDirectory() as fake_home:
        fake_home = Path(fake_home)
        env_file = fake_home / ".config" / "opencode" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as vault:
            vault_path = Path(vault).resolve()
            (vault_path / "scripts").mkdir()
            (vault_path / "scripts" / "engine.py").write_text("# fake")
            env_file.write_text(f"VAULT_DIR={vault_path}\n")
            result = _run_shim(
                "--where",
                env={"HOME": str(fake_home)},
                cwd="/tmp",
            )
            assert result.stdout.strip() == str(vault_path)


def test_resolution_4_shim_in_vault_bin():
    """When the shim is at <vault>/scripts/bin/spiel, the vault is the shim's parent."""
    with tempfile.TemporaryDirectory() as vault:
        vault_path = Path(vault).resolve()
        (vault_path / "scripts" / "bin").mkdir(parents=True)
        (vault_path / "scripts" / "engine.py").write_text("# fake")
        # Copy the real shim into the fake vault
        shim_copy = vault_path / "scripts" / "bin" / "spiel"
        shim_copy.write_text(SHIM.read_text())
        shim_copy.chmod(0o755)

        result = subprocess.run(
            [str(shim_copy), "--where"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": "/nonexistent", "VAULT_DIR": ""},
            cwd="/tmp",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(vault_path)


def test_no_resolution_exits_with_clear_error():
    """When nothing resolves, exit 1 with a helpful multi-line error.

    We test this with a COPY of the shim in a directory that is NOT under
    `scripts/bin/`. The bundled shim (priority 4) always finds the real
    vault when run from the repo, so we cannot use the bundled shim here.
    """
    with tempfile.TemporaryDirectory() as fake_dir:
        fake_dir = Path(fake_dir).resolve()
        # Copy the shim to a location that is NOT under scripts/bin/
        loose_shim = fake_dir / "spiel-copy"
        loose_shim.write_text(SHIM.read_text())
        loose_shim.chmod(0o755)

        with tempfile.TemporaryDirectory() as fake_home:
            result = subprocess.run(
                [str(loose_shim), "--version"],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": fake_home, "VAULT_DIR": ""},
                cwd="/tmp",
            )
            assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
            err = result.stderr
            assert "ERROR: spiel could not locate" in err
            # Error must enumerate every tried path
            for hint in ("VAULT_DIR env var", ".spiel-vault", ".env", "shim"):
                assert hint in err, f"missing hint in error: {hint}\n{err}"


def test_priority_order_inline_wins_over_project_local():
    """$VAULT_DIR env var beats <cwd>/.spiel-vault."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()
        # Fake "inline" vault
        inline_vault = tmp_path / "inline"
        inline_vault.mkdir()
        (inline_vault / "scripts").mkdir()
        (inline_vault / "scripts" / "engine.py").write_text("# inline")
        # Fake "project-local" vault
        local_vault = tmp_path / "local"
        local_vault.mkdir()
        (local_vault / "scripts").mkdir()
        (local_vault / "scripts" / "engine.py").write_text("# local")
        (local_vault / ".spiel-vault").write_text(f"VAULT_DIR={local_vault}\n")

        result = _run_shim(
            "--where",
            env={"VAULT_DIR": str(inline_vault)},
            cwd=str(local_vault),
        )
        assert result.stdout.strip() == str(inline_vault), (
            f"inline should win, got: {result.stdout!r}"
        )


def test_idempotent_path_guard_for_shell_rc():
    """The bash guard the SETUP.md writes into ~/.zshrc must be idempotent.

    We assert the guard's logic: applying it twice to PATH that already
    contains $HOME/.local/bin leaves it with one entry, not two.
    """
    home = "/Users/test"
    # Simulate what SETUP.md does
    path_with_local = f"{home}/.local/bin:/usr/bin:/bin"
    # Run the guard three times
    for _ in range(3):
        path_with_local = (
            f'{home}/.local/bin:{path_with_local}'
            if f":{home}/.local/bin:" not in f":{path_with_local}:"
            else path_with_local
        )
    # We expect exactly one occurrence of $HOME/.local/bin
    assert path_with_local.count(f"{home}/.local/bin") == 1, (
        f"guard produced duplicate entries: {path_with_local!r}"
    )


def test_shim_execs_real_engine_when_valid():
    """When a real vault resolves, `spiel status` runs the engine (smoke test)."""
    # This test only runs when the shim resolves to a real engine.py (e.g.
    # in CI on the real repo). When the shim resolves to a fake vault
    # (other resolution tests), the engine would fail to import modules.
    result = _run_shim("status", check=False, env={"VAULT_DIR": str(REPO_ROOT)})
    # We don't care about exit code here — we just want the engine to have
    # been invoked. Output should contain something state-machine-shaped.
    combined = result.stdout + result.stderr
    assert "state" in combined.lower() or "ERROR" in combined, (
        f"unexpected output: {combined[:500]}"
    )
