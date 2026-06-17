---
name: spiel-content
description: Spiel content engine — drafts X / LinkedIn / blog posts. Triggers on "post", "tweet", "content", "X", "Twitter", "LinkedIn", "blog", "spiel", "/post".
---

## Pipeline

**When the user invokes /post or any trigger word, delegate IMMEDIATELY to the @post subagent.** The subagent runs the full orchestrator loop. Do not interpret /post yourself — the subagent owns the pipeline.

## Dependencies

This skill requires the `spiel` shim on PATH. The shim is path-independent and resolves the vault from `~/.config/opencode/.env` (where `VAULT_DIR` is set during setup). It execs `scripts/engine.py` inside the vault from any cwd, in any project, in any IDE.

If the user gets a "spiel: command not found" error, they need to either:
- Run the engine's `SETUP.md` (installs the shim + writes `VAULT_DIR` automatically), OR
- Copy `scripts/bin/spiel` to `~/.local/bin/spiel` and add `export PATH="$HOME/.local/bin:$PATH"` to their shell rc.

---

# Spiel Content — Content Engine Skill

**The orchestrator is `spiel content run`.** It drives the entire content loop end-to-end. `spiel` is a thin wrapper at `~/.local/bin/spiel` — invoke it directly, do not reference `scripts/engine.py` as a relative path.

**Voice source of truth:** `concepts/voice-and-gates.md` (in the vault resolved by `spiel --where`).

**Post subagent:** `~/.config/opencode/agents/post.md` — the ONLY executor for /post.

---

## 🔒 ORCHESTRATOR FLOW — DELEGATE TO @post

The subagent runs ONE command per turn:

```
spiel content run
```

The kernel handles ALL state transitions, pausing at exactly two LLM handoffs and two human checkpoints:

| Stage | What happens | Who acts |
|-------|--------------|----------|
| SESSION_CAPTURE | Auto-load strategy pages, session, classify | Kernel |
| COMPILE | LLM runs 8-step Compiler, writes via `spiel content compile-write` | LLM (subagent) |
| SELECT | Auto-rank templates by archetype/axis/funnel/ICP | Kernel |
| FORMAT_WIZARD | Human picks formats (x/linkedin/blog) | Human (via LLM) |
| DRAFTING | LLM writes draft files, registers via `spiel content draft-write` + `draft-done` | LLM (subagent) |
| BANNER | Auto-generate PNGs | Kernel |
| GATE_CHECK | Run 16 mechanical + 4-check + 10-gate | Kernel |
| QUEUE | Human picks publish/hold per draft | Human (via LLM) |
| PUBLISHING → ARCHIVE → COMPLETE | Dispatch via Buffer/direct | Kernel |

---

## 🔒 HARD RULES (pipeline violations = reset)

| Violation | Consequence |
|-----------|-------------|
| Skip `spiel content run` | No pipeline. |
| Call `content post`/`compile`/`draft` directly | Breaks orchestrator. |
| Reference `scripts/engine.py` as a relative path | Breaks from non-vault cwd. Always go through `spiel`. |
| Ask user "what did you work on?" | NEVER. Kernel auto-detects session. |
| Draft without `core_insight` | Blocked by kernel. |
| Skip format wizard | Drafts wrong formats. |
| Skip LLM-judged gates | Slop reaches user. |

---

## Voice

- Lowercase i
- Short sentences, fast pacing
- Hook in first 2 lines
- Reader (ICP) is the subject
- Specific numbers
- Named reader ("founders", "builders", "operators")
- Landing line: thought, not summary

---

## What this skill does NOT do

No auto-publishing. No comment/DM handling. No offer redesign.

---

## When in doubt

**Delegate to @post. Run `spiel content run`. Do not skip any turn.**
