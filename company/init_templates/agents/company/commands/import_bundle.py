"""Department portability as a GitHub-repo import (``company export`` / ``company import``).

A shareable Department ships as a repository folder, not an archive: the
owner clones or downloads the bundle next to (or inside) their home and
imports it from that local folder. ``company export`` is the producer —
it walks a home Department, computes its full dependency closure, and
writes the complete bundle-repository folder. ``company import`` is the
consumer — it validates the manifest, the spine pin, the closure, and
the declaration against the live contracts, then installs ONLY into the
six owner layers under ``.agents/company/``:

    departments/<id>/   skills/<id>/   capabilities/<id>/
    connections/        strategy/      agents/installed/

The vendored spine, the host trees, and every settings file are never
touched. Import is idempotent: re-importing refreshes bundle-owned paths
to bundle bytes; owner files outside the manifest file list are never
overwritten.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import sys
from pathlib import Path

from ..runtime.config import VERSION

#: The six owner layers an import may write (relative to
#: ``.agents/company/``); everything else is the vendored spine.
#: ``departments``, ``skills``, and ``capabilities`` ship FOLDERS
#: (``<layer>/<id>/**``); ``connections`` and ``strategy`` ship FILES;
#: ``agents/installed`` ships ``installed/<id>.json`` declarations.
OWNER_LAYERS = (
    "departments", "skills", "capabilities", "connections", "strategy",
    "agents/installed",
)

#: Layer roots that ship FOLDERS (a bundle owns ``<layer>/<id>/**``;
#: the vendored spine keeps ``<layer>/__init__.py`` and ``<layer>/core.py``).
FOLDER_LAYERS = ("departments", "skills", "capabilities")

#: Layer roots that ship FILES directly (a bundle owns named files;
#: ``__init__.py``/``core.py`` at the root stay vendored spine).
FILE_LAYERS = ("connections", "strategy")

#: Vendored spine files that stay at the root of a user layer.
VENDORED_LAYER_FILES = frozenset({"__init__.py", "core.py"})

#: Folders never copied into a bundle (build noise, host state).
_EXCLUDE_PARTS = {"__pycache__", ".git", "node_modules", ".spielos"}

BUNDLE_MANIFEST = "bundle.json"


def _major_minor(version: str) -> str:
    """The major.minor prefix of a version string ('' when unparseable).

    An import whose pin differs from the running spine in its major or
    minor component cannot be trusted against the live contracts; the
    failure names the repair. Patch drift within one minor is fine.
    """
    return ".".join((version or "").split(".")[:2])


def _home_layers(home: Path) -> Path:
    """``<home>/.agents/company`` — the layer root of one home."""
    return home / ".agents" / "company"


def _relative_files(root: Path) -> list[str]:
    """Every file under ``root`` as posix relative paths, deterministic."""
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _EXCLUDE_PARTS for part in path.parts):
            continue
        if path.suffix == ".pyc":
            continue
        files.append(path.relative_to(root).as_posix())
    return files


# ---------------------------------------------------------------------------
# Closure computation (shared by export and import validation)
# ---------------------------------------------------------------------------


def _load_declaration(home: Path, department_id: str):
    """Import one home Department package against the live contracts.

    Departments are discovered as real packages under
    ``.agents/company/departments/``; the same import runs here so
    export validates exactly what the runtime will load. Returns the
    declaration instance, or raises ValueError naming the failure.
    """
    import company.departments as department_package

    package_root = _home_layers(home) / "departments"
    package = package_root / department_id
    if not (package / "department.py").is_file():
        raise ValueError(
            f"department {department_id!r} has no declaration at "
            f"{package / 'department.py'}")
    overlay = str(package_root.resolve())
    # Rebuild the department package path exactly like discovery does:
    # live layer plus this overlay, so the declaration's relative
    # imports resolve against the real contracts.
    live = list(department_package.__path__)
    department_package.__path__ = [overlay, *live]
    module_name = f"{department_package.__name__}.{department_id}.department"
    cached = sys.modules.pop(module_name, None)
    try:
        module = importlib.import_module(module_name)
        candidates = [value for value in vars(module).values()
                      if isinstance(value, type)
                      and value.__module__ == module.__name__
                      and getattr(value, "department_id", None)]
        if len(candidates) != 1:
            raise ValueError(
                f"{module_name} must export exactly one Department "
                f"(found {len(candidates)})")
        return candidates[0]()
    except (ImportError, AttributeError, SyntaxError) as error:
        raise ValueError(
            f"department {department_id!r} does not import against the "
            f"live contracts: {error}") from error
    finally:
        if cached is not None:
            sys.modules[module_name] = cached
        department_package.__path__ = live


def _closure(declaration) -> dict[str, tuple[str, ...]]:
    """The full dependency closure of one Department declaration.

    Every id the declaration's workflows and its own surface reference:
    skills (per step), connections (per step), capabilities (step
    requirements plus installed-agent declarations), agents (the
    department's own ``agent_ids`` plus every step's agent that is
    installed), and strategy documents (the strategy layer files a home
    references from step instructions). Deterministic and ordered.
    """
    seen: dict[str, set[str]] = {key: set() for key in (
        "skills", "connections", "capabilities", "agents", "strategy")}
    workflows = tuple(getattr(declaration, "workflows", ()) or ())
    for workflow in workflows:
        for step in getattr(workflow, "steps", ()):
            seen["skills"].update(step.skill_ids)
            seen["connections"].update(step.connection_ids)
            seen["capabilities"].update(
                (step.requirements or {}).get("capabilities", ()))
    seen["agents"].update(getattr(declaration, "agent_ids", ()) or ())
    for workflow in workflows:
        seen["agents"].update(step.agent_id
                             for step in getattr(workflow, "steps", ()))
    # Strategy: canonical documents the declaration's instructions name
    # with the strategy/ prefix (strategy/icp.md is the convention).
    text = " ".join(
        step.instruction for workflow in workflows
        for step in getattr(workflow, "steps", ()))
    for name in re.findall(r"strategy/([A-Za-z0-9_./-]+)", text):
        cleaned = name.rstrip(".,;:)")
        seen["strategy"].add(cleaned)
    return {key: tuple(sorted(values)) for key, values in seen.items()}


def _home_has_skill(home: Path, skill_id: str) -> bool:
    return (_home_layers(home) / "skills" / skill_id / "SKILL.md").is_file()


def _home_has_capability(home: Path, capability_id: str) -> bool:
    return (_home_layers(home) / "capabilities" / capability_id).is_dir()


def _home_has_connection(home: Path, connection_id: str) -> bool:
    """A connection is satisfiable by a module or registry entry.

    The connections layer ships client modules and an owner registry;
    a referenced connection id resolves when a module of that name
    exists in the layer.
    """
    layer = _home_layers(home) / "connections"
    return ((layer / f"{connection_id}.py").is_file()
            or (layer / connection_id).is_dir())


def _home_has_agent(home: Path, agent_id: str) -> bool:
    return (_home_layers(home) / "agents" / "installed"
            / f"{agent_id}.json").is_file()


def _home_has_strategy(home: Path, name: str) -> bool:
    return (_home_layers(home) / "strategy" / name).is_file()


_HAS = {"skills": _home_has_skill, "connections": _home_has_connection,
        "capabilities": _home_has_capability, "agents": _home_has_agent,
        "strategy": _home_has_strategy}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _export_missing(home: Path, closure: dict[str, tuple[str, ...]]) -> list[str]:
    """Every missing closure piece, named, one line per item."""
    missing = []
    for key in ("skills", "connections", "capabilities", "agents", "strategy"):
        for item in closure[key]:
            if not _HAS[key](home, item):
                missing.append(f"{key[:-1]}: {item} "
                               f"(expected at {key}/{item})")
    return missing


def _readme(manifest: dict) -> str:
    """The step-by-step bundle onboarding README (generated at export).

    Carries the clone-or-download path, the one import command, and one
    paste-this-prompt block per adopter that tells the Director to import
    the bundle from this folder through the goal loop.
    """
    department = manifest["id"]
    label = manifest.get("name") or department
    version = manifest["version"]
    prompt = (
        f"Please install the {label} into my company from the bundle "
        "repository folder I placed at the path below. Import it through "
        "the goal loop: create one bounded goal for the import, run the "
        "import command against that folder path, and record the import "
        "receipt as evidence before completing the goal. The command to "
        "run is\n"
        "  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m "
        f"company import <ABSOLUTE_PATH_TO_THIS_FOLDER>\n"
        f"(pass the absolute path of the folder holding this README — the "
        f"{department} bundle, version {version}.) After the import, "
        "tell me which workflows the Department declares and what goal I "
        "should create to put it to work.")
    return f"""# {label} — a portable SpielOS Department bundle

This folder is a complete Department bundle for
[SpielOS](https://spielos.xyz): the `{department}` Department (v{version}),
its full dependency closure (skills, capabilities, connections, installed
agents, strategy documents), and this onboarding README. Import it into a
SpielOS home and the Department is immediately live in the Goal loop.

## What is inside

| Path | Contents |
|---|---|
| `bundle.json` | manifest: identity, version, spine pin, closure file list |
| `departments/{department}/` | the Department declaration package |
| `skills/`, `capabilities/`, `connections/`, `strategy/` | the dependency closure |
| `agents/installed/` | installed Agent declarations the closure needs |

Everything installs into the six owner layers of your home
(`.agents/company/departments`, `skills`, `capabilities`, `connections`,
`strategy`, `agents/installed`). Your vendored spine, host adapters, and
settings are never touched, and re-importing only refreshes bundle-owned
files.

## Step 1 — get this folder onto your machine

Clone the repository (recommended), or download and unzip it:

```sh
git clone <this-repository-url> {department}-bundle
```

Any local folder works; the import reads the folder you cloned or
unzipped — nothing is fetched over the network at import time.

## Step 2 — one shell command imports it

From your SpielOS home (the folder that contains `.agents/` and
`.spielos/`), run the import once:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company import /absolute/path/to/this/folder
```

The command validates the manifest, the spine pin, the dependency
closure, and the declaration against your home's live contracts, then
installs the bundle into your owner layers and prints a receipt. It is
idempotent: running it again refreshes bundle-owned files only.

## Step 3 — or just paste this prompt to your Director

No command needed: paste the block for your host and the Director does
the import through the goal loop. The folder path is the only input.

### OpenCode

Run `/agents`, select the **Director** agent, and paste:

```text
{prompt}
```

### Codex

Talk to the **Director** agent and paste the same prompt:

```text
{prompt}
```

### Claude Code

Run `claude --agent director` (or just `claude`) and paste the same
prompt:

```text
{prompt}
```

## After the import

- `company departments` lists `{department}` with its workflows.
- `company catalog` shows the workflows it declares.
- Create a goal on one of its metrics and the loop runs end to end:
  `company goal create --name "..." --owner {department} --metric <declared metric> --target ...`

If the import reports a spine pin mismatch, upgrade your home first
(`spielos update`) and re-import; the message names the exact repair.
"""


def _copy_into_bundle(source: Path, bundle: Path, rel: str) -> list[str]:
    """Copy a file or folder tree into the bundle at ``rel``.

    Returns the bundle-relative paths written (posix, no bundle prefix).
    """
    target = bundle / rel
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return [rel]
    written = []
    for item in _relative_files(source):
        destination = target / item
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / item, destination)
        written.append(f"{rel}/{item}")
    return written


def _department_label(department_id: str) -> str:
    """The bundle title: the id plus its role, one short human label."""
    return f"{department_id} Department"


def export_bundle(home: Path, department_id: str, out: Path) -> dict:
    """``company export <department_id> --out <folder>``.

    Walks the home's ``departments/<id>/`` package, computes the full
    closure, refuses naming every missing piece, and writes the bundle
    repository folder: manifest, department package, closure layers, and
    the step-by-step README. Returns the manifest receipt.
    """
    home = Path(home).resolve()
    out = Path(out).expanduser().resolve()
    layers = _home_layers(home)
    if not layers.is_dir():
        raise ValueError(f"no SpielOS home at {home} (.agents/company)")

    declaration = _load_declaration(home, department_id)
    closure = _closure(declaration)

    missing = _export_missing(home, closure)
    if missing:
        raise ValueError(
            f"cannot export {department_id!r}: the dependency closure is "
            f"incomplete in this home — missing "
            + "; ".join(missing))

    if out.exists() and any(out.iterdir()):
        raise ValueError(
            f"output folder {out} exists and is not empty; choose an "
            "empty or new folder")
    out.mkdir(parents=True, exist_ok=True)

    files: list[str] = []
    files += _copy_into_bundle(layers / "departments" / department_id,
                                out, f"departments/{department_id}")
    for skill_id in closure["skills"]:
        files += _copy_into_bundle(layers / "skills" / skill_id,
                                   out, f"skills/{skill_id}")
    for capability_id in closure["capabilities"]:
        files += _copy_into_bundle(layers / "capabilities" / capability_id,
                                   out, f"capabilities/{capability_id}")
    for connection_id in closure["connections"]:
        source = (layers / "connections" / f"{connection_id}.py")
        if source.is_file():
            files += _copy_into_bundle(
                source, out, f"connections/{connection_id}.py")
        else:
            files += _copy_into_bundle(
                layers / "connections" / connection_id,
                out, f"connections/{connection_id}")
    for agent_id in closure["agents"]:
        source = layers / "agents" / "installed" / f"{agent_id}.json"
        files += _copy_into_bundle(
            source, out, f"agents/installed/{agent_id}.json")
    for name in closure["strategy"]:
        files += _copy_into_bundle(layers / "strategy" / name,
                                   out, f"strategy/{name}")

    manifest = {
        "schema": 1,
        "id": department_id,
        "name": _department_label(department_id),
        "version": getattr(declaration, "version", "0.0.0"),
        "spine_pin": VERSION,
        "files": sorted(files),
        "closure": {key: list(value) for key, value in closure.items()},
    }
    (out / BUNDLE_MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (out / "README.md").write_text(_readme(manifest))

    return {"exported": department_id, "version": manifest["version"],
            "spine_pin": VERSION, "bundle": str(out),
            "files": manifest["files"],
            "closure": manifest["closure"],
            "readme": str(out / "README.md"),
            "next_steps": [
                f"push the folder to a git repository (it is a complete "
                f"bundle repo: git init, commit, push)",
                "adopters clone or download it and run `company import "
                "<folder>` — see the generated README",
            ]}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _validate_pin(pin: str) -> None:
    """The spine pin must be compatible with the running spine.

    A major or minor mismatch cannot be trusted against the live
    contracts; the failure names the repair. Patch drift is fine.
    """
    pin = (pin or "").strip()
    if not pin:
        raise ValueError(
            "bundle.json carries no spine pin; the bundle is incomplete — "
            "re-export it from a working home")
    if _major_minor(pin) != _major_minor(VERSION):
        raise ValueError(
            f"bundle pins spine {pin} but this home runs {VERSION}: the "
            f"declaration may not match the live contracts. Repair: "
            f"upgrade the home to a {pin}-compatible release "
            f"(`spielos update` after `pipx upgrade spielos`) or re-export "
            f"the bundle from a {VERSION} home, then import again. "
            "Nothing was installed.")


def _bundle_files(bundle: Path) -> dict[str, str]:
    """Manifest file list keyed by relative path (posix)."""
    manifest_path = bundle / BUNDLE_MANIFEST
    if not manifest_path.is_file():
        raise ValueError(
            f"no bundle.json in {bundle}; this folder is not a Department "
            "bundle — clone or download the full bundle repository first")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"bundle.json does not parse: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError("bundle.json must be a JSON object")
    for key in ("id", "version", "spine_pin", "files"):
        if not manifest.get(key):
            raise ValueError(f"bundle.json is missing {key!r}")
    files = manifest["files"]
    if not isinstance(files, list) or not all(
            isinstance(item, str) and item for item in files):
        raise ValueError("bundle.json 'files' must be a list of paths")
    return manifest


def _validate_layers(files: list[str]) -> None:
    """Every bundle file must land inside the six owner layers.

    The vendored spine, host trees, and settings are never writable by
    an import; a bundle that claims anything else is refused whole.
    """
    problems = []
    for rel in files:
        parts = Path(rel).parts
        if not parts or parts[0] in ("..", ".") or any(
                part in _EXCLUDE_PARTS or part.startswith(".")
                for part in parts):
            problems.append(f"{rel} (reserved or hidden path)")
            continue
        if parts[0] == "agents":
            if (len(parts) >= 3 and parts[1] == "installed"
                    and parts[2] not in VENDORED_LAYER_FILES):
                continue
            problems.append(
                f"{rel} (the agents layer ships installed/<id>.json only)")
        elif parts[0] in FOLDER_LAYERS or parts[0] in FILE_LAYERS:
            # A folder layer needs <layer>/<id>/<file>; a file layer
            # needs <layer>/<file>. The vendored spine's own root files
            # (__init__.py, core.py) are never bundle-owned.
            needed = 3 if parts[0] in FOLDER_LAYERS else 2
            if len(parts) < needed:
                problems.append(f"{rel} (belongs deeper inside its layer)")
                continue
            if parts[1] in VENDORED_LAYER_FILES:
                problems.append(f"{rel} (vendored spine root file)")
                continue
        else:
            problems.append(f"{rel} (outside the six owner layers: "
                            + ", ".join(OWNER_LAYERS) + ")")
    if problems:
        raise ValueError(
            "bundle claims files outside the installable owner layers — "
            "refusing the whole import: " + "; ".join(problems))


def _import_closure_status(bundle: Path, home: Path,
                           closure: dict[str, tuple[str, ...]]) -> tuple[dict, list[str]]:
    """Which closure pieces the bundle ships vs the home already has."""
    layers = _home_layers(home)
    bundle_has = {
        "skills": lambda item: (bundle / "skills" / item / "SKILL.md").is_file(),
        "connections": lambda item: (
            (bundle / "connections" / f"{item}.py").is_file()
            or (bundle / "connections" / item).is_dir()),
        "capabilities": lambda item: (bundle / "capabilities" / item).is_dir(),
        "agents": lambda item: (
            bundle / "agents" / "installed" / f"{item}.json").is_file(),
        "strategy": lambda item: (bundle / "strategy" / item).is_file(),
    }
    satisfied: dict[str, list[str]] = {key: [] for key in bundle_has}
    missing: list[str] = []
    for key, finder in bundle_has.items():
        for item in closure.get(key, ()):
            if finder(item):
                satisfied[key].append(item)
            elif _HAS[key](home, item):
                satisfied[key].append(item)  # already in the home
            else:
                missing.append(f"{key[:-1]}: {item}")
    return satisfied, missing


def _declaration_imports_cleanly(bundle: Path, home: Path,
                                 department_id: str) -> str:
    """Import the bundle's declaration against the live contracts.

    Runs against a throwaway staging copy of the bundle's department
    package so the home itself stays untouched while validating;
    returns the declaration's version.
    """
    import tempfile

    source = bundle / "departments" / department_id / "department.py"
    if not source.is_file():
        raise ValueError(
            f"bundle ships no declaration for {department_id!r} at "
            f"departments/{department_id}/department.py")
    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging) / "departments" / department_id
        stage.mkdir(parents=True)
        for path in (bundle / "departments" / department_id).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                shutil.copy2(path, stage / path.relative_to(
                    bundle / "departments" / department_id))
        (Path(staging) / "departments" / "__init__.py").write_text("")
        # Stage as an overlay on the home's departments package path so
        # relative imports (from ...workflows import ...) resolve.
        import company.departments as department_package
        original = list(department_package.__path__)
        try:
            department_package.__path__ = [
                str(Path(staging) / "departments"), *original]
            module_name = (f"{department_package.__name__}.{department_id}"
                           ".department")
            sys.modules.pop(module_name, None)
            module = importlib.import_module(module_name)
            candidates = [value for value in vars(module).values()
                          if isinstance(value, type)
                          and value.__module__ == module.__name__
                          and getattr(value, "department_id", None)]
            if len(candidates) != 1:
                raise ValueError(
                    f"bundle declaration for {department_id!r} must export "
                    f"exactly one Department (found {len(candidates)})")
            declaration = candidates[0]()
            if getattr(declaration, "department_id", None) != department_id:
                raise ValueError(
                    f"bundle declares department "
                    f"{declaration.department_id!r} inside the "
                    f"{department_id!r} folder")
            return getattr(declaration, "version", "0.0.0")
        except (ImportError, AttributeError, SyntaxError) as error:
            raise ValueError(
                f"bundle declaration for {department_id!r} does not import "
                f"cleanly against this home's contracts: {error}") from error
        finally:
            department_package.__path__ = original


def import_bundle(home: Path, folder: Path) -> dict:
    """``company import <folder>``.

    Validates the manifest, spine pin, closure completeness, and the
    declaration against the live contracts, then installs ONLY into the
    six owner layers. Idempotent; owner files outside the bundle list
    are never touched; a conflicting non-bundle path is never
    overwritten. Returns the receipt.
    """
    home = Path(home).resolve()
    folder = Path(folder).expanduser().resolve()
    layers = _home_layers(home)
    if not layers.is_dir():
        raise ValueError(f"no SpielOS home at {home} (.agents/company)")
    if not folder.is_dir():
        raise ValueError(f"no bundle folder at {folder}")

    manifest = _bundle_files(folder)
    department_id = manifest["id"]
    _validate_pin(manifest.get("spine_pin"))
    files = list(manifest["files"])
    _validate_layers(files)

    closure = {key: tuple(value or ())
               for key, value in (manifest.get("closure") or {}).items()}
    satisfied, missing = _import_closure_status(folder, home, closure)
    if missing:
        raise ValueError(
            f"bundle {department_id!r} has an incomplete dependency closure "
            "— neither the bundle nor this home provides: "
            + "; ".join(missing)
            + ". Nothing was installed.")

    _declaration_imports_cleanly(folder, home, department_id)

    # Whole-bundle precondition: every manifest path must exist in the
    # bundle BEFORE anything is written, so a broken bundle leaves the
    # home untouched (never a partial install).
    for rel in files:
        if not (folder / rel).is_file():
            raise ValueError(
                f"bundle.json lists {rel} but the bundle folder does not "
                "carry it — the bundle is incomplete; nothing was installed")

    # Install: exactly the manifest file list, into the owner layers
    # only. The destination tree is built from the bundle bytes; a path
    # the bundle owns refreshes to bundle bytes (idempotent), and any
    # other existing path is left alone (never overwritten, never
    # pruned).
    installed: list[str] = []
    for rel in files:
        source = folder / rel
        target = layers / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        installed.append(rel)

    # Receipt: what landed where, with next steps.
    return {
        "imported": department_id,
        "version": manifest.get("version"),
        "spine_pin": manifest.get("spine_pin"),
        "bundle": str(folder),
        "installed": installed,
        "already_satisfied": {key: value for key, value in satisfied.items()
                              if value},
        "files_installed": len(installed),
        "home": str(home),
        "next_steps": [
            "company departments — confirm the Department is live",
            "company catalog — see the workflows it declares",
            "company goal create --name \"...\" --owner "
            f"{department_id} --metric <declared metric> --target ...",
        ],
    }


__all__ = ["export_bundle", "import_bundle", "OWNER_LAYERS"]
