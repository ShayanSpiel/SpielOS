"""Interactive first-run onboarding for ``spielos init``.

One driver, two renderings:

- a terminal (TTY) run gets an OpenCode-style experience: a quiet banner,
  a braille spinner per materialization phase, green checkmarks as each
  step lands, one confirmation card at the end;
- pipes and CI get the same steps as plain deterministic lines with the
  same exit codes (0 ok / 1 failure / 130 aborted). No prompts, no ANSI.

The scaffold itself lives in ``bootstrap.scaffold``; this module owns only
the human surface: prompts, progress, verification, and next steps.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .bootstrap import available_workgroups, scaffold

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


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
        return self.cyan("◆" if self.unicode else "*")


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
        seconds = f" ({elapsed:.1f}s)" if elapsed >= 2.0 else ""
        if exc_type is None:
            print(f"{self.style.mark_ok()} {self.label}{seconds}", flush=True)
        else:
            print(f"{self.style.mark_fail()} {self.label}", flush=True)


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


def _choose(style: _Style, question: str, options: list[tuple[str, str]],
            default: int = 1) -> int:
    """Numbered choice menu. Returns the 1-based selection."""
    print(f"\n{style.bold(question)}")
    for index, (label, detail) in enumerate(options, start=1):
        marker = style.dim("(default)") if index == default else ""
        print(f"  {style.cyan(str(index))}) {label} {style.dim(detail)} {marker}")
    raw = _prompt(style, "Choose", str(default))
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return int(raw)
    for index, (label, _) in enumerate(options, start=1):
        if raw.lower() == label.lower():
            return index
    print(style.yellow(f"  Didn't catch that — using option {default}."))
    return default


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


def _next_steps(root: Path, hosts: dict[str, bool], minimal: bool,
                workgroups: list[str]) -> tuple[list[str], dict[str, str]]:
    """Hand the fresh home to the Director instead of onboarding in the CLI."""
    steps = [
        ("cd " + str(root), ""),
        ("codex", "call @Director and talk to the SpielOS Director agent"),
        ("opencode", "run /agent, select the Director agent, and talk to it"),
    ]
    notes = {
        "handoff": "Choose Codex or OpenCode; the SpielOS Director handles onboarding in chat.",
    }
    return steps, notes


def _render_success(style: _Style, receipt: dict) -> None:
    root = receipt["root"]
    hosts = receipt.get("hosts") or {}
    if not style.tty:
        print(f"SpielOS harness ready at {root} ({receipt['files_written']} files)"
              + (" · runtime verified" if receipt.get("verified") else ""))
    else:
        import re

        def visible_len(text: str) -> int:
            return len(re.sub(r"\033\[[0-9;]*m", "", text))

        width = 64
        print()
        print(style.cyan("┌" + "─" * (width - 2) + "┐"))
        title = " SpielOS is ready"
        print(style.cyan("│") + style.bold(title.ljust(width - 2))
              + style.cyan("│"))

        def row(label: str, value: str) -> None:
            pad = max(0, width - 4 - visible_len(value))
            line = f" {label.ljust(10)}{value}{' ' * pad}"
            print(style.cyan("│") + line + style.cyan(" │"))

        row("Home", root)
        row("Files", str(receipt["files_written"]))
        row("Mode", receipt.get("mode_label", "harness"))
        if receipt.get("workgroups"):
            row("Workgroups", ", ".join(receipt["workgroups"]))
        verified = (style.green("verified") if receipt.get("verified")
                    else style.red("FAILED"))
        row("Runtime", verified)
        hosts_text = []
        for name in ("opencode", "codex"):
            state = (style.green("✓") if hosts.get(name)
                     else style.dim("—"))
            hosts_text.append(f"{name} {state}")
        row("Hosts", "   ".join(hosts_text))
        print(style.cyan("└" + "─" * (width - 2) + "┘"))
        print()

    steps, notes = _next_steps(Path(root), hosts, receipt.get("minimal", False),
                               receipt.get("workgroups") or [])
    print(style.bold("Next steps"))
    for command, note in steps:
        print(f"  {style.green('$')} {style.bold(command)}")
        if note:
            print(f"    {style.dim(note)}")
    for note in notes.values():
        print(f"  {style.mark_warn()} {note}")
    print()


# ---- the driver -------------------------------------------------------------


def run_init(*, dir: str = ".", force: bool = False, minimal: bool = True,
             workgroups: list[str] | None = None, assume_yes: bool = False,
             as_json: bool = False) -> int:
    """Entry point for ``spielos init``. Returns the process exit code.

    A fresh home ships the spine only — zero Workgroups. Starter
    Workgroups are an explicit opt-in (``--workgroup``, ``--all-workgroups``
    or the interactive picker).
    """
    style = _Style()
    interactive = (style.tty and sys.stdin.isatty()
                   and not assume_yes and not as_json)
    target = Path(dir).expanduser().resolve()

    try:
        if interactive:
            banner(style, target)
            force = force or _confirm_overwrite(style, target)

        receipt = None
        quiet = as_json  # machine mode: keep stdout parseable, no chrome
        if not quiet:
            with _Spinner(style, "Preparing") as spinner:
                receipt = scaffold(target, force=force, minimal=minimal,
                                   workgroups=workgroups,
                                   on_phase=spinner.set_label)
        else:
            receipt = scaffold(target, force=force, minimal=minimal,
                               workgroups=workgroups)

        hosts = _detect_hosts()
        count = len(workgroups or [])
        if not minimal:
            mode_label = "Full harness"
        elif count:
            mode_label = f"Fresh spine + {count} Workgroup(s)"
        else:
            mode_label = "Fresh spine"
        receipt.update({"hosts": hosts, "minimal": minimal,
                        "workgroups": workgroups or [],
                        "mode_label": mode_label})
        # Verification runs in both modes; only the rendering differs.
        if as_json:
            ok, error = _verify_home(target)
            receipt["verified"] = ok
            print(json.dumps(receipt, indent=2))
            return 0 if ok else _fail_json(error)

        with _Spinner(style, "Verifying the new home runs"):
            ok, error = _verify_home(target)
        receipt["verified"] = ok
        if not ok:
            _render_success(style, receipt)  # still show what landed
            return _fail(style, "Verification failed — the home is written "
                         "but its runtime did not answer.",
                         error,
                         hint=f"cd {target} && PYTHONDONTWRITEBYTECODE=1 "
                              "PYTHONPATH=.agents python3 -B -m company status")
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
        known = available_workgroups()
        hint = (f"available Workgroups: {', '.join(known)}"
                if known and "Workgroup" in detail else None)
        if as_json:
            print(json.dumps({"error": detail}, indent=2), file=sys.stderr)
            return 1
        return _fail(style, "Could not scaffold the harness.", detail, hint=hint)
    except OSError as exc:
        if as_json:
            print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
            return 1
        return _fail(style, "Could not write the harness home.", str(exc),
                     hint="check folder permissions and free disk space")


def banner(style: _Style, target: Path) -> None:
    from .config import VERSION

    width = 52
    print()
    print(style.cyan("╭" + "─" * (width - 2) + "╮"))
    title = f" ◆ SpielOS v{VERSION}"
    print(style.cyan("│") + style.bold(style.cyan(title.ljust(width - 2)))
          + style.cyan("│"))
    tagline = " one durable loop for your AI company"
    print(style.cyan("│") + style.dim(tagline.ljust(width - 2))
          + style.cyan("│"))
    target_line = f" setting up: {target}"
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
