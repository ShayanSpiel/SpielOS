"""Interactive first-run onboarding for ``spielos init``.

One driver, two renderings:

- a terminal (TTY) run gets an animated experience: a boxed banner, one
  braille spinner line per materialization phase (with per-phase timings),
  a confirmation card, and host-specific next steps;
- pipes and CI get the same steps as plain deterministic lines with the
  same exit codes (0 ok / 1 failure / 130 aborted). No prompts, no ANSI.

The scaffold itself lives in ``bootstrap.scaffold``; this module owns only
the human surface.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .bootstrap import scaffold

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

LOGO = [
    "██╗ ██╗███████╗██╗",
    "██║ ██║██╔════╝██║",
    "███████║██████╗ ██║",
    "██╔══██║╚═══██║██║",
    "██║  ██║██████╔╝███████╗",
    "╚═╝  ╚═╝╚═════╝ ╚══════╝",
]


# ---- rendering primitives --------------------------------------------------


class _Style:
    """ANSI styling that silently degrades to plain text."""

    def __init__(self) -> None:
        stream = sys.stdout
        tty = bool(stream.isatty()) and os.environ.get("TERM") != "dumb"
        no_color = bool(os.environ.get("NO_COLOR", "").strip())
        self.enabled = tty and not no_color
        self.tty = tty
        encoding = (getattr(stream, "encoding", "") or "").lower()
        self.unicode = "utf" in encoding or sys.platform == "darwin"

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def mark_ok(self) -> str:
        return self.green("✓" if self.unicode else "[ok]")

    def mark_fail(self) -> str:
        return self.red("✗" if self.unicode else "[FAILED]")

    def mark_warn(self) -> str:
        return self.yellow("•" if self.unicode else "[!]")

    def mark_info(self) -> str:
        return self.cyan("›" if self.unicode else ">")


class _Spinner:
    """Braille spinner on one line; the label updates live as phases land."""

    def __init__(self, style: _Style, label: str) -> None:
        self.style = style
        self.label = label
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._started_at = 0.0

    def set_label(self, label: str) -> None:
        """Progress hook: called between materialization phases."""
        with self._lock:
            self.label = label

    def __enter__(self) -> "_Spinner":
        self._started_at = time.monotonic()
        if not self.style.tty or not self.style.unicode:
            # Plain environments stay quiet here; __exit__ writes one line.
            return self
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def _animate(self) -> None:
        frames = SPINNER_FRAMES
        index = 0
        while not self._stop.wait(0.08):
            with self._lock:
                label = self.label
            frame = self.style.cyan(frames[index % len(frames)])
            sys.stdout.write(f"\r\033[K{frame} {self.style.dim(label)}")
            sys.stdout.flush()
            index += 1

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.monotonic() - self._started_at
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if self.style.tty and self.style.unicode:
            sys.stdout.write("\r\033[K")
        seconds = f" ({elapsed:.1f}s)" if elapsed >= 1.0 else ""
        if exc_type is None:
            print(f"{self.style.mark_ok()} {self.label}{seconds}", flush=True)
        else:
            print(f"{self.style.mark_fail()} {self.label}", flush=True)


def _scaffold_with_progress(target: Path, force: bool, style: _Style):
    """Run the scaffold on a worker thread; animate one spinner per phase.

    Returns (receipt, error). Exactly one of them is None.
    """
    phases: "queue.Queue[str | None]" = queue.Queue()
    outcome: dict = {}

    def worker() -> None:
        try:
            outcome["receipt"] = scaffold(target, force=force,
                                           on_phase=phases.put)
        except BaseException as error:  # surfaced to the caller below
            outcome["error"] = error
        finally:
            phases.put(None)

    threading.Thread(target=worker, daemon=True).start()
    label = phases.get()
    while label is not None:
        with _Spinner(style, label):
            label = phases.get()
    receipt, error = outcome.get("receipt"), outcome.get("error")
    return receipt, error


# ---- failure helpers -------------------------------------------------------


def _fail_json(error: str) -> int:
    print(json.dumps({"error": error, "verified": False}, indent=2),
          file=sys.stderr)
    return 1


def _fail(style: _Style, title: str, detail: str, hint: str | None = None) -> int:
    lines = [f"{style.mark_fail()} {style.bold(title)}", "", f"  {detail}"]
    if hint:
        lines += ["", f"  {style.dim('Try:')} {hint}"]
    print("\n".join(lines), file=sys.stderr)
    return 1


def _prompt(style: _Style, question: str, default: str = "") -> str:
    suffix = f" {style.dim(f'[{default}]')}" if default else ""
    try:
        answer = input(f"{style.mark_info()} {style.bold(question)}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


# ---- host detection and verification ---------------------------------------


def _detect_hosts() -> dict[str, bool]:
    return {"opencode": shutil.which("opencode") is not None,
            "codex": shutil.which("codex") is not None}


def _verify_home(root: Path) -> tuple[bool, str]:
    """Prove the vendored home runs without creating operational state."""
    env = dict(os.environ,
               PYTHONPATH=str(root / ".agents"),
               PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "company", "catalog"],
            cwd=root, env=env, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "verification timed out after 120s"
    except OSError as exc:
        return False, f"could not launch python: {exc}"
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, tail[-1] if tail else f"exit code {result.returncode}"
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "catalog did not return valid JSON"
    return True, ""


def _department_count(root: Path) -> int:
    departments = root / ".agents" / "company" / "departments"
    if not departments.is_dir():
        return 0
    return sum(1 for _ in departments.glob("*/department.py"))


# ---- success rendering ------------------------------------------------------


def _next_steps(root: Path, hosts: dict[str, bool]) -> tuple[list[tuple[str, str]], list[str]]:
    """Hand the fresh home to the Director instead of onboarding in the CLI."""
    steps = [("cd " + str(root), "your SpielOS home")]
    if hosts.get("opencode"):
        steps.append(("opencode",
                      "run /agents, select the Director agent, and talk to it — "
                      "it already sees your company state"))
    if hosts.get("codex"):
        steps.append(("codex",
                      "talk to the Director agent (@director) — it already "
                      "sees your company state"))
    notes = [
        "Choose OpenCode or Codex; the Director handles everything else in chat.",
        "Set credentials in .spielos/.env (see .spielos/.env.example).",
    ]
    return steps, notes


def _render_success(style: _Style, receipt: dict) -> None:
    from .config import VERSION

    root = receipt["root"]
    hosts = receipt.get("hosts") or {}
    if not style.tty:
        print(f"SpielOS {VERSION} ready at {root} ({receipt['files_written']} files)"
              + (" · runtime verified" if receipt.get("verified") else ""))
        steps, _ = _next_steps(Path(root), hosts)
        for command, _note in steps:
            print(f"  $ {command}")
        return

    import re

    def visible_len(text: str) -> int:
        return len(re.sub(r"\033\[[0-9;]*m", "", text))

    width = 64
    content = width - 2  # printable columns between the two border chars
    label_column = 12    # 11 for the label + one trailing space

    def row(label: str, value: str) -> None:
        room = content - 1 - label_column
        if visible_len(value) > room:
            value = (value[:room - 2] + "…" if style.unicode
                     else value[:room - 3] + "...")
        pad = max(1, room - visible_len(value))
        print(style.cyan("│")
              + f" {label.ljust(label_column)}{value}{' ' * pad}"
              + style.cyan("│"))

    print()
    print(style.cyan("┌" + "─" * (width - 2) + "┐"))
    row("", style.bold(f"SpielOS {VERSION} is ready"))
    print(style.cyan("├" + "─" * (width - 2) + "┤"))
    row("Home", str(root))
    row("Files", str(receipt["files_written"]))
    row("Departments", str(receipt.get("department_count", 0)))
    row("Runtime", style.green("verified ✓") if receipt.get("verified")
        else style.red("FAILED"))
    hosts_text = "  ".join(
        f"{name} {(style.green('✓') if hosts.get(name) else style.dim('—'))}"
        for name in ("opencode", "codex"))
    row("Hosts", hosts_text)
    print(style.cyan("└" + "─" * (width - 2) + "┘"))
    print()

    steps, notes = _next_steps(Path(root), hosts)
    print(style.bold("Next steps"))
    for command, note in steps:
        print(f"  {style.green('$')} {style.bold(command)}")
        if note:
            print(f"    {style.dim(note)}")
    for note in notes:
        print(f"  {style.mark_warn()} {note}")
    print()


# ---- the drivers -------------------------------------------------------------


def run_init(*, dir: str = ".", force: bool = False, assume_yes: bool = False,
             as_json: bool = False) -> int:
    """Entry point for ``spielos init``. Returns the process exit code.

    A fresh home ships the clean spine only, with zero Departments.
    """
    from .config import VERSION

    style = _Style()
    interactive = (style.tty and sys.stdin.isatty()
                   and not assume_yes and not as_json)
    target = Path(dir).expanduser().resolve()

    try:
        if interactive:
            _banner(style, target, VERSION)
            force = force or _confirm_overwrite(style, target)

        quiet = as_json  # machine mode: keep stdout parseable, no chrome
        if quiet:
            receipt = scaffold(target, force=force)
        else:
            receipt, error = _scaffold_with_progress(target, force, style)
            if error is not None:
                raise error
            print(f"{style.mark_ok()} Company runtime installed", flush=True)

        hosts = _detect_hosts()
        receipt.update({"hosts": hosts, "mode_label": "Fresh clean spine",
                        "department_count": _department_count(target)})
        # Verification runs in both modes; only the rendering differs.
        if as_json:
            ok, error = _verify_home(target)
            receipt["verified"] = ok
            print(json.dumps(receipt, indent=2))
            return 0 if ok else _fail_json(error)

        ok, error = _verify_home(target)
        receipt["verified"] = ok
        if not ok:
            _render_success(style, receipt)  # still show what landed
            return _fail(style, "Verification failed — the home is written "
                         "but its runtime did not answer.",
                         error,
                         hint=f"cd {target} && PYTHONDONTWRITEBYTECODE=1 "
                              "PYTHONPATH=.agents python3 -B -m company status")
        print(f"{style.mark_ok()} Runtime verified", flush=True)
        _render_success(style, receipt)
        return 0
    except KeyboardInterrupt:
        print(file=sys.stderr)
        print("Aborted — nothing else was written.", file=sys.stderr)
        return 130
    except FileExistsError as exc:
        if as_json:
            print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
            return 1
        return _fail(style, "This folder already has a SpielOS home.", str(exc),
                     hint="spielos init --force   # overwrite vendored files\n"
                          "           (your .spielos/ state is never touched)")
    except ValueError as exc:
        detail = str(exc)
        if as_json:
            print(json.dumps({"error": detail}, indent=2), file=sys.stderr)
            return 1
        return _fail(style, "Could not scaffold the harness.", detail)
    except OSError as exc:
        if as_json:
            print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
            return 1
        return _fail(style, "Could not write the harness home.", str(exc),
                     hint="check folder permissions and free disk space")


def run_update(*, dir: str = ".", as_json: bool = False) -> int:
    """Entry point for ``spielos update``. Returns the process exit code.

    Refreshes the vendored spine in an existing home from the templates of
    the distribution that is running. Private ``.spielos/`` state and the
    user Department/Agent layers are always preserved; a missing home is an
    error (use ``init``).
    """
    from .config import VERSION

    from .paths import validate_home_destination

    style = _Style()
    target = validate_home_destination(Path(dir).expanduser().resolve())
    if not (target / ".agents" / "company" / "runtime").is_dir():
        message = f"no SpielOS home in {target}; run `spielos init --dir {target}` first"
        if as_json:
            print(json.dumps({"error": message, "updated": False}, indent=2),
                  file=sys.stderr)
            return 1
        print(f"{style.mark_fail()} {style.bold(message)}", file=sys.stderr)
        return 1
    try:
        if as_json:
            receipt = scaffold(target, force=True)
        else:
            print(style.bold(f"SpielOS {VERSION} — refreshing {target}"))
            receipt, error = _scaffold_with_progress(target, True, style)
            if error is not None:
                raise error
    except (OSError, ValueError) as error:
        if as_json:
            print(json.dumps({"error": str(error), "updated": False}, indent=2),
                  file=sys.stderr)
            return 1
        return _fail(style, "Could not refresh the home.", str(error))
    ok, error_text = _verify_home(target)
    receipt.update({"updated": ok, "verified": ok, "mode_label": "Refreshed clean spine",
                    "department_count": _department_count(target)})
    if not ok:
        if as_json:
            print(json.dumps({**receipt, "error": error_text}, indent=2),
                  file=sys.stderr)
            return 1
        return _fail(style, "Verification failed — the home was written "
                     "but its runtime did not answer.", error_text)
    if as_json:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"{style.mark_ok()} SpielOS home refreshed at {target} "
              f"({receipt['files_written']} files · state preserved)")
    return 0


def run_first_use(root: Path) -> int:
    """Bare ``spielos`` with no home in this folder: invite the owner in."""
    style = _Style()
    from .config import VERSION

    if not (style.tty and sys.stdin.isatty()):
        print("No SpielOS home in this folder.", file=sys.stderr)
        print("Create one:  spielos init", file=sys.stderr)
        print("Home elsewhere:  spielos --db /path/to/.spielos/state/company.sqlite status",
              file=sys.stderr)
        return 1
    _banner(style, root, VERSION)
    answer = _prompt(style, "Create your SpielOS home in this folder?", "Y")
    if answer.strip().lower() in {"n", "no"}:
        print(style.yellow("  Nothing was written. Run `spielos init --dir <folder>` "
                          "when you are ready."))
        return 0
    return run_init(dir=str(root))


def _banner(style: _Style, target: Path, version: str) -> None:
    width = 34
    print()
    print(style.cyan("╭" + "─" * (width - 2) + "╮"))
    if style.unicode:
        for line in LOGO:
            pad = width - 2 - len(line)
            print(style.cyan("│") + " " + style.bold(style.cyan(line))
                  + " " * max(1, pad) + style.cyan("│"))
        print(style.cyan("├" + "─" * (width - 2) + "┤"))
    else:
        title = " SpielOS"
        print(style.cyan("│") + style.bold(title.ljust(width - 2))
              + style.cyan("│"))
    tagline = f" company operating system · v{version}"
    print(style.cyan("│") + style.dim(tagline.ljust(width - 2)[:width - 2])
          + style.cyan("│"))
    target_line = f" home: {target}"
    if len(target_line) > width - 4:
        target_line = target_line[:width - 7] + "..."
    print(style.cyan("│") + style.dim(target_line.ljust(width - 2))
          + style.cyan("│"))
    print(style.cyan("╰" + "─" * (width - 2) + "╯"))
    print()


def _confirm_overwrite(style: _Style, target: Path) -> bool:
    if not (target / ".agents" / "company").is_dir():
        return False
    answer = _prompt(style, "A SpielOS home already exists here. Overwrite "
                     "vendored files? (state is kept)", "N")
    if answer.strip().lower() in {"y", "yes"}:
        return True
    print(style.yellow("  Keeping the existing home — nothing was changed."))
    raise SystemExit(0)
