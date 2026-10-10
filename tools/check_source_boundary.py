#!/usr/bin/env python3
"""Audit product ownership without reading credential values or changing files."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROHIBITED = (".agents", ".codex", ".opencode", ".claude", ".spielos",
              "opencode.json", "bundles", "outbound", "data", "public")
SKIP = {".git", "__pycache__", "node_modules", ".pytest_cache", "build", "dist"}
failures = []
role = json.loads((ROOT / ".spielos-boundary.json").read_text()).get("role")
if role != "source":
    failures.append("repository role must be source")
for name in PROHIBITED:
    if os.path.lexists(ROOT / name):
        failures.append(f"installed owner path exists: {name}")
for directory, folders, files in os.walk(ROOT, followlinks=False):
    folders[:] = [name for name in folders if name not in SKIP]
    for name in folders + files:
        path = Path(directory) / name
        if path.is_symlink() and not path.resolve().is_relative_to(ROOT):
            failures.append(f"external filesystem link: {path.relative_to(ROOT)}")
# Only the explicitly authorized publishing token may live in local .env.
# Report names only; never print values or publish this ignored file.
env = ROOT / ".env"
if env.is_file():
    keys = {line.split("=", 1)[0].strip() for line in env.read_text().splitlines()
            if "=" in line and not line.lstrip().startswith("#")}
    if keys - {"NPM_TOKEN"}:
        failures.append("local publishing .env contains non-publishing variable names")
    if subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        failures.append("publishing .env must never be tracked")
# Synthetic fixtures may exercise core interfaces but must not carry owner copy.
fixture_root = ROOT / "company/tests/fixtures/departments"
for path in fixture_root.glob("*/department.py"):
    text = path.read_text()
    if "Synthetic" not in text or "production_ready = False" not in text:
        failures.append(f"fixture is not explicitly synthetic: {path.relative_to(ROOT)}")
    for token in ("Onda", "spielos.xyz", "SpielOS Film System", "/Users/", "Snappfood"):
        if token in text:
            failures.append(f"owner production copy in fixture: {path.relative_to(ROOT)}")
# Every executable module in a shipped runtime must mirror reusable source.
for path in (ROOT / "company/init_templates/agents/company").rglob("*.py"):
    source = ROOT / "company" / path.relative_to(ROOT / "company/init_templates/agents/company")
    if not source.is_file() or source.read_bytes() != path.read_bytes():
        failures.append(f"runtime template drift: {source.relative_to(ROOT)}")
if failures:
    print("Source boundary audit failed:")
    for failure in failures:
        print(f"- {failure}")
    raise SystemExit(1)
print("Source boundary is clean: reusable code/templates and synthetic fixtures only.")
if env.exists():
    print("Explicit owner exception: ignored local NPM_TOKEN publishing credential; values not inspected or changed.")
