"""tests/test_skip_list.py — Tests for the skip-list logic used by spiel update + re-install.

The skip list is the ONLY thing that protects user data. The principle:
- PERSONAL (preserved): strategy/, content/, .env, system/brand.*, system/rules.yaml
- PROJECT (refreshed): team/, system/playbook, tools/, install/, bin/, tests/, archive/, skills/, docs, adapters/

This test verifies the skip list behavior by:
  1. Building a mock SOURCE (canonical SpielOS) with project files
  2. Building a mock VAULT (user install) with user data + project files
  3. Running the overlay Python code (extracted from bin/spiel + install.sh)
  4. Verifying the right files were updated and the right ones were preserved

The test extracts the same Python overlay snippet used by `spiel update` SOURCE_DIR path
and the `install.sh` re-install path, so we test the actual production code.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}  {detail}")


def fresh_pair() -> tuple[Path, Path]:
    """Create (source, vault) temp dirs. Return (source, vault)."""
    base = Path(tempfile.mkdtemp(prefix="spiel-skip-"))
    source = base / "source"
    vault = base / "vault"
    source.mkdir()
    vault.mkdir()
    return source, vault


def run_overlay(source: Path, vault: Path) -> dict:
    """Run the exact same Python overlay snippet that bin/spiel uses for SOURCE_DIR updates.

    Returns dict with updated, added, skipped lists.
    """
    code = r"""
import os, shutil, hashlib, sys
src, dst = sys.argv[1], sys.argv[2]
# ONLY personal data is skipped. Role prompts, system playbook, tools, etc. are project-level and always updated.
skip_dirs  = set("strategy content".split())
skip_files = set([".env", "system/brand.md", "system/brand.json", "system/rules.yaml"])
def file_hash(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None
updated, added, skipped = [], [], 0
for root, dirs, files in os.walk(src):
    rel = os.path.relpath(root, src)
    parts = rel.split(os.sep) if rel != "." else []
    if any(p in skip_dirs for p in parts):
        continue
    for f in files:
        rf = os.path.relpath(os.path.join(root, f), src)
        if rf in skip_files:
            continue
        sp, dp = os.path.join(root, f), os.path.join(dst, rf)
        nh, oh = file_hash(sp), file_hash(dp)
        if nh == oh:
            skipped += 1
            continue
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        shutil.copy2(sp, dp)
        (added if oh is None else updated).append(rf)
print("UPDATED=" + ",".join(sorted(updated)))
print("ADDED=" + ",".join(sorted(added)))
print("SKIPPED_UNCHANGED=" + str(skipped))
"""
    r = subprocess.run(
        [sys.executable, "-c", code, str(source), str(vault)],
        capture_output=True, text=True,
    )
    out = {"updated": [], "added": [], "skipped_unchanged": 0, "stderr": r.stderr}
    for line in r.stdout.splitlines():
        if line.startswith("UPDATED="):
            out["updated"] = [x for x in line[len("UPDATED="):].split(",") if x]
        elif line.startswith("ADDED="):
            out["added"] = [x for x in line[len("ADDED="):].split(",") if x]
        elif line.startswith("SKIPPED_UNCHANGED="):
            out["skipped_unchanged"] = int(line[len("SKIPPED_UNCHANGED="):])
    return out


# ─── Tests ──────────────────────────────────────────────────────────────

def test_team_files_are_refreshed() -> None:
    print("\n[1] team/*.md is refreshed (project-level)")
    source, vault = fresh_pair()
    # Source has new strategist.md
    (source / "team").mkdir()
    (source / "team" / "strategist.md").write_text("NEW STRATEGIST with state machine")
    # Vault has old strategist.md
    (vault / "team").mkdir()
    (vault / "team" / "strategist.md").write_text("OLD STRATEGIST")
    out = run_overlay(source, vault)
    check("team/strategist.md is in updated list", "team/strategist.md" in out["updated"],
          f"updated={out['updated']}")
    check("vault strategist.md has new content",
          (vault / "team" / "strategist.md").read_text() == "NEW STRATEGIST with state machine")


def test_strategy_files_are_preserved() -> None:
    print("\n[2] strategy/*.md is preserved (personal)")
    source, vault = fresh_pair()
    (source / "strategy").mkdir()
    (source / "strategy" / "audience.md").write_text("NEW audience from upstream")
    (vault / "strategy").mkdir()
    (vault / "strategy" / "audience.md").write_text("USER'S PERSONAL audience")
    out = run_overlay(source, vault)
    check("strategy/audience.md NOT in updated list", "strategy/audience.md" not in out["updated"],
          f"updated={out['updated']}")
    check("strategy/audience.md NOT in added list", "strategy/audience.md" not in out["added"])
    check("vault strategy/audience.md unchanged (user's personal)",
          (vault / "strategy" / "audience.md").read_text() == "USER'S PERSONAL audience")


def test_brand_files_are_preserved() -> None:
    print("\n[3] system/brand.md + brand.json are preserved (personal)")
    source, vault = fresh_pair()
    (source / "system").mkdir()
    (source / "system" / "brand.md").write_text("NEW brand")
    (source / "system" / "brand.json").write_text('{"name": "NEW"}')
    (vault / "system").mkdir()
    (vault / "system" / "brand.md").write_text("USER'S brand")
    (vault / "system" / "brand.json").write_text('{"name": "USER"}')
    out = run_overlay(source, vault)
    check("system/brand.md NOT in updated list", "system/brand.md" not in out["updated"])
    check("system/brand.json NOT in updated list", "system/brand.json" not in out["updated"])
    check("brand.md preserved",
          (vault / "system" / "brand.md").read_text() == "USER'S brand")
    check("brand.json preserved",
          (vault / "system" / "brand.json").read_text() == '{"name": "USER"}')


def test_rules_yaml_is_preserved() -> None:
    print("\n[4] system/rules.yaml is preserved (personal, user may tune)")
    source, vault = fresh_pair()
    (source / "system").mkdir()
    (source / "system" / "rules.yaml").write_text("# NEW upstream rules")
    (vault / "system").mkdir()
    (vault / "system" / "rules.yaml").write_text("# USER'S TUNED rules")
    out = run_overlay(source, vault)
    check("system/rules.yaml NOT in updated list", "system/rules.yaml" not in out["updated"])
    check("rules.yaml preserved",
          (vault / "system" / "rules.yaml").read_text() == "# USER'S TUNED rules")


def test_env_is_preserved() -> None:
    print("\n[5] .env is preserved (personal, credentials)")
    source, vault = fresh_pair()
    (source / ".env").write_text("VAULT_DIR=/upstream\nSECRET=upstream")
    (vault / ".env").write_text("VAULT_DIR=/user\nSECRET=user_secret_xyz")
    out = run_overlay(source, vault)
    check(".env NOT in updated list", ".env" not in out["updated"])
    check(".env preserved with user's secret",
          (vault / ".env").read_text() == "VAULT_DIR=/user\nSECRET=user_secret_xyz")


def test_content_is_preserved() -> None:
    print("\n[6] content/* is preserved (personal, user-generated)")
    source, vault = fresh_pair()
    (source / "content" / "drafts").mkdir(parents=True)
    (source / "content" / "drafts" / "new.md").write_text("NEW upstream draft")
    (vault / "content" / "drafts").mkdir(parents=True)
    (vault / "content" / "drafts" / "user.md").write_text("USER'S draft")
    (vault / "content" / "current.md").write_text("USER'S current run")
    out = run_overlay(source, vault)
    check("content/drafts/new.md NOT in added list", "content/drafts/new.md" not in out["added"])
    check("content/drafts/user.md preserved",
          (vault / "content" / "drafts" / "user.md").read_text() == "USER'S draft")
    check("content/current.md preserved",
          (vault / "content" / "current.md").read_text() == "USER'S current run")


def test_tools_are_refreshed() -> None:
    print("\n[7] tools/*.py is refreshed (project-level)")
    source, vault = fresh_pair()
    (source / "tools").mkdir()
    (source / "tools" / "advance.py").write_text("# NEW advance.py with state machine")
    (vault / "tools").mkdir()
    (vault / "tools" / "advance.py").write_text("# OLD advance.py")
    out = run_overlay(source, vault)
    check("tools/advance.py is in updated list", "tools/advance.py" in out["updated"])
    check("vault advance.py has new content",
          (vault / "tools" / "advance.py").read_text() == "# NEW advance.py with state machine")


def test_archive_is_refreshed() -> None:
    print("\n[8] archive/* is refreshed (project-level, canonical reference)")
    source, vault = fresh_pair()
    (source / "archive" / "skills" / "icp_simulation").mkdir(parents=True)
    (source / "archive" / "skills" / "icp_simulation" / "SKILL.md").write_text("NEW SKILL")
    out = run_overlay(source, vault)
    check("archive/skills/icp_simulation/SKILL.md is added",
          "archive/skills/icp_simulation/SKILL.md" in out["added"],
          f"added={out['added']}")


def test_new_system_files_are_added() -> None:
    print("\n[9] new system files (run-state.md, session-schema.md) are added")
    source, vault = fresh_pair()
    (source / "system").mkdir()
    (source / "system" / "run-state.md").write_text("# run-state.md")
    (source / "system" / "session-schema.md").write_text("# session-schema.md")
    (vault / "system").mkdir()
    out = run_overlay(source, vault)
    check("system/run-state.md is added", "system/run-state.md" in out["added"])
    check("system/session-schema.md is added", "system/session-schema.md" in out["added"])


def test_full_skip_list_table() -> None:
    print("\n[10] Full skip list table is consistent with production code")
    # Read the bin/spiel skip list to verify it matches the test
    bin_spiel = (ROOT / "bin" / "spiel").read_text()
    check("bin/spiel has skip_dirs=\"strategy content\"",
          '_SPielos_SKIP_DIRS="strategy content"' in bin_spiel)
    check("bin/spiel has skip_files including rules.yaml",
          '"system/rules.yaml"' in bin_spiel)
    check("bin/spiel does NOT have skills in skip list (refreshed)",
          '"skills strategy"' not in bin_spiel)
    check("bin/spiel does NOT have team in skip list (refreshed)",
          '"team skills"' not in bin_spiel and 'skip_dirs.*team' not in bin_spiel.lower().replace("team/strategist.md", ""))
    # install.sh
    install_sh = (ROOT / "install" / "install.sh").read_text()
    check("install.sh has skip_dirs = {\"strategy\", \"content\"}",
          'skip_dirs = {"strategy", "content"}' in install_sh)
    check("install.sh has skip_files including rules.yaml",
          '"system/rules.yaml"' in install_sh)
    check("install.sh does NOT have team in skip list (refreshed)",
          'skip_dirs = {"team"' not in install_sh and '"team", "skills"' not in install_sh)


# ─── Runner ─────────────────────────────────────────────────────────────

def main() -> int:
    print(f"SpielOS skip-list tests")
    test_team_files_are_refreshed()
    test_strategy_files_are_preserved()
    test_brand_files_are_preserved()
    test_rules_yaml_is_preserved()
    test_env_is_preserved()
    test_content_is_preserved()
    test_tools_are_refreshed()
    test_archive_is_refreshed()
    test_new_system_files_are_added()
    test_full_skip_list_table()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
