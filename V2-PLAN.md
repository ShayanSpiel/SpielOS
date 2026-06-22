# SpielOS v2 — Plan

**Status:** Approved direction, not yet implemented. Work begins in next session.

**Goal:** Fix three structural problems in v1 and ship v2.

---

## The 3 problems (v1, shipped)

### P1. Hidden install = invisible drafts
Vault lives at `~/.spiel/`. So `content/queue/*.md` is hidden from the user's
IDE project tree. User can't open drafts in Cursor/VS Code/opencode to edit or
publish them. "Open project" in the IDE opens the user's project, not the
Spiel vault. Drafts, banners, and the brief file are out of sight.

### P2. Slash commands improvise instead of dispatch
`/post` loads `post.md` (a prompt). The LLM reads "delegate to MD". It then
makes a judgment call. Most calls are wrong:
- Writes a draft directly to cwd (user reported)
- Asks clarifying questions
- Skips states
- Picks formats without the human checkpoint
- Doesn't invoke the deterministic tools (banner.py, gates.py, buffer.py)

The LLM is the orchestrator. The role prompts (`team/*.md`) are decoration the
LLM reads and improvises from. **None of the deterministic tools run.**

### P3. Wizard is ~40% complete
Covers brand, ICP, positioning, offer, funnel, voice, methodology, archetypes.
Missing:
- API token verification (Buffer, X, LinkedIn, blog) — just stores raw strings
- Engine knobs (post cadence, max_drafts, auto-publish mode, max rev rounds)
- Banner template picker (only `default`, no choice)
- Gate strictness (composite score threshold, hard vs soft)
- Template favorites (3-5 from registry, no way to pre-pick)
- Platform preferences (X vs LinkedIn tone, length, hashtag style)
- Voice corpus (just a starter, no real example posts)
- Time/date format preferences
- Per-platform CTA style

---

## The 3 fixes (v2, this plan)

### F1. Install in user's project directory

```
cd ~/projects/my-startup                # or any project folder
curl -fsSL https://...install.sh | bash
# SpielOS now lives at ~/projects/my-startup/
# Open ~/projects/my-startup in the IDE
# content/queue/, content/posted/, assets/banners/ are visible
# Drafts are real files you can click on, edit, copy
```

**Vault resolution (in priority order):**
1. `$SPIELOS_PROJECT_DIR` env var
2. Walk up from cwd looking for `team/md.md` (find project root marker)
3. `~/.spiel` symlink (legacy fallback)

**Shim:** `bin/spiel` in the project + symlink to `~/.local/bin/spiel` for
global access. Shim uses the resolution above to find the vault.

### F2. Strict slash command prompts

`/post` stays a prompt (not pure bash). The prompt has hard rules:

```markdown
---
description: Run the /post content pipeline.
---

# /post — Content Pipeline Dispatcher

The user is invoking the SpielOS content pipeline. Your only action:

1. Run this exact bash command: `spiel content run $ARGUMENTS`
2. Show the user the output
3. Stop.

Hard rules (zero exceptions):
- Do NOT write any file outside the bash command's output
- Do NOT interpret the request
- Do NOT explain the pipeline
- Do NOT ask clarifying questions
- Do NOT call any other tool
- Do NOT spawn a subagent yourself
- Do NOT improvise

The `spiel` CLI is the deterministic orchestrator. It walks the 12-state
pipeline and invokes the role subagents at the right moments. You are a
dispatcher, not a writer.

If `spiel` is not found: "Run `spiel init` to set up SpielOS."
```

The LLM reads the prompt, runs the bash command, reports the output. The
pipeline runs deterministically. The LLM cannot write a draft to cwd because
the prompt forbids it AND the CLI writes only to `content/queue/`.

### F3. LangGraph as the orchestrator

The state machine is implemented in **LangGraph** (not raw Python). The
reasons:

| Failure mode (v1) | LangGraph solution |
|---|---|
| State file gets corrupted mid-run | built-in checkpointing (SQLite/Postgres) |
| Error in one node crashes the whole run | built-in retry + error nodes |
| Human checkpoint interrupted (Ctrl+C) | `interrupt()` + resume from last checkpoint |
| Race conditions between tool calls | graph execution model is serial |
| Conditional transitions ("if gates fail, go back") | declarative edges in the graph |
| "Where am I in the pipeline?" | graph viz out of the box |
| Pure-Python orchestration broke before | battle-tested for this exact pattern |

**Why not raw Python:** the user has direct experience with raw-Python
orchestration breaking at exactly these failure modes. LangGraph is built for
multi-actor LLM workflows with persistence + retry + human-in-the-loop.

**Why not Rust:** orchestration runs a few times a day for marketing content,
not 10k req/s. Python iteration cost dominates. Wizard, banner, gates, and
publishers all stay in Python. If a single binary is needed later, `pyinstaller`
or `shiv` packages the Python CLI.

---

## The architecture (v2)

```
User types: /post topic
   ↓
opencode loads: post.md (strict prompt)
   ↓
LLM reads: "run `spiel content run $ARGUMENTS`, do nothing else"
   ↓
LLM runs bash: !`spiel content run topic`
   ↓
bin/spiel content run → LangGraph graph.invoke()
   ↓
graph state machine (deterministic, 12 nodes):
   IDLE
     → SESSION_CAPTURE   [python: source session log or topic]
     → COMPILE           [LLM: read team/md.md, write insights to brief]
     → SELECT            [LLM: read team/strategist.md, pick templates]
     → FORMAT_WIZARD     [HUMAN: pick formats, interrupt()]
     → DRAFTING          [LLM: read team/copywriter.md, write drafts]
     → BANNER            [python: tools/banner.py for each draft]
     → GATE_CHECK        [python: tools/gates.py for each draft]
     → PUBLISH_REVIEW    [HUMAN: pick per-draft, interrupt()]
     → PUBLISHING        [python: tools/publisher/buffer.py for each draft]
     → ANALYZING_POST    [python: tools/analyst.py, can be deferred]
     → COMPLETE_POST     [python: archive, return to IDLE]
   ↓
LLM invoked at exactly 3 nodes: COMPILE, SELECT, DRAFTING
Python at: IDLE, SESSION_CAPTURE, BANNER, GATE_CHECK, PUBLISHING, ANALYZING_POST, COMPLETE_POST
HUMAN at: FORMAT_WIZARD, PUBLISH_REVIEW
```

### The graph (sketch)

```python
# engine/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

builder = StateGraph(SpielState)

# LLM nodes (the ONLY places the LLM is invoked)
builder.add_node("compile", make_agent_node("team/md.md", mode="compile"))
builder.add_node("select",  make_agent_node("team/strategist.md", mode="select"))
builder.add_node("draft",   make_agent_node("team/copywriter.md", mode="draft"))

# Python nodes (deterministic, no LLM)
builder.add_node("session_capture", session_capture_node)  # sources session/topic
builder.add_node("banner",          banner_node)            # tools/banner.py
builder.add_node("gates",           gates_node)             # tools/gates.py
builder.add_node("publish",         publish_node)           # tools/publisher/buffer.py
builder.add_node("analyze",         analyze_node)           # tools/analyst.py
builder.add_node("complete",        complete_node)          # archive

# Human-in-the-loop nodes (interrupt)
builder.add_node("format_wizard",   format_wizard_node)     # pick formats
builder.add_node("publish_review",  publish_review_node)    # pick per-draft

# Edges (deterministic transitions, LLM never decides)
builder.add_edge("session_capture", "compile")
builder.add_edge("compile", "select")
builder.add_edge("select", "format_wizard")
builder.add_edge("format_wizard", "draft")      # after human confirms
builder.add_edge("draft", "banner")
builder.add_edge("banner", "gates")

# Conditional edge: gates can loop back to draft (the "rabbit hole" escape)
def gate_check(state):
    if state["gates_passed"]:
        return "publish_review"
    elif state["rev_rounds"] < 3:
        return "draft"             # loop back, retry
    else:
        return "publish_review"    # human decides after 3 revs
builder.add_conditional_edges("gates", gate_check)

builder.add_edge("publish_review", "publish")   # after human confirms
builder.add_edge("publish", "analyze")
builder.add_edge("analyze", "complete")
builder.add_edge("complete", END)
```

### The role prompts

`team/md.md`, `team/strategist.md`, `team/copywriter.md` are **unchanged** as
prompt text. They become LangGraph agent system prompts. The CLI passes the
right prompt + the right input to the LLM at each node. The LLM writes a
string output. The CLI writes the string to a file.

---

## The invariants (the "no rabbit hole" rule, written in code)

```python
# engine/graph.py — top of file
"""
SpielOS state machine — INVARIANTS

1. The LLM is invoked at exactly 3 nodes: compile, select, draft.
   These are the only nodes where the LLM is creative.

2. The LLM never decides:
   - State transitions (graph edges are static)
   - What to publish (human decides at publish_review)
   - What format to use (human decides at format_wizard)
   - File locations outside content/queue/ and content/posted/

3. The LLM always:
   - Receives a system prompt from team/*.md
   - Receives an input (brief, session, template)
   - Produces a string output that the CLI writes to a file
   - Never calls tools that aren't in the LangGraph tool registry

4. Any PR that violates 1-3 gets rejected.
"""
```

This is the rule. The LLM is a tool the graph uses at specific nodes. The
graph is the orchestrator. The human is the decision-maker at checkpoints.

---

## Scope

| ID | Change | LOC | Time | Notes |
|---|---|---|---|---|
| A | Install in project dir | ~150 | 1h | path resolution, vault finder, walk-up logic |
| B | Strict slash command prompts | ~100 | 30m | rewrite post.md; add publish.md, analyze.md, setup.md, health.md |
| C1 | Comprehensive wizard (10 → 16 steps) | ~400 | 1.5h | 6 new steps |
| C2 | LangGraph state machine | ~600 | 2h | engine/graph.py, nodes, edges, persistence |
| C3 | Role prompts as LangGraph agents | ~200 | 1h | wrap team/*.md as agents with tools |
| T  | Tests for graph + shim | ~200 | 30m | unit + E2E |
| D  | Docs (AGENTS.md, README) | ~200 | 30m | update architecture diagram |
| **Total** | | **~1850** | **~7h** | |

**New dependencies:** `langgraph`, `langchain-core`, `langchain-openai` (or
`langchain-anthropic`). ~50MB on disk.

### New wizard steps

| Step | What |
|---|---|
| 11 | API tokens + verification: paste Buffer token, click Verify, see channels. Same for X / LinkedIn / blog. |
| 12 | Engine knobs: post cadence (per week), max drafts in queue, auto-publish mode (manual / always), max rev rounds |
| 13 | Gate strictness: composite score threshold (default 0.85), hard vs soft enforcement |
| 14 | Banner template picker: preview 4 templates, click to pick |
| 15 | Template favorites: pick 3-5 from registry |
| 16 | Voice corpus: paste 2-3 real posts as canonical examples |

---

## Build order

1. **A** (project-dir install) — visible value, low risk
2. **B** (strict prompts) — fixes the broken `/post` immediately
3. **C2** (LangGraph graph) — the real orchestrator
4. **C3** (role agents) — the role prompts become real
5. **C1** (wizard expansion) — config completeness
6. **T** (tests) — lock in the contract
7. **D** (docs) — reflect the new architecture

---

## Acceptance criteria

- [ ] `cd ~/projects/my-startup && curl ... | bash` installs in the project
- [ ] Drafts in `~/projects/my-startup/content/queue/` are visible in the IDE
- [ ] `/post empty` runs the full 12-state pipeline deterministically
- [ ] `/post topic` does NOT write a draft to cwd (forbidden by prompt + CLI)
- [ ] LLM is invoked at exactly 3 nodes: compile, select, draft
- [ ] Human is interrupted at exactly 2 nodes: format_wizard, publish_review
- [ ] Gate-check failure loops back to draft (max 3 rounds)
- [ ] Wizard covers all 16 config areas
- [ ] All tools (banner, gates, publishers) actually run as Python nodes
- [ ] 88/88 smoke + new graph tests pass
- [ ] E2E test: full pipeline from /post to /posted

---

## Decisions

| Question | Answer | Why |
|---|---|---|
| LangGraph vs raw Python? | LangGraph | user has direct experience with raw-Python orchestration breaking |
| Rust vs Python? | Python | iteration cost dominates; orchestration runs a few times a day |
| `/post` prompt vs bash? | Prompt | user explicit: "/post stays a prompt" |
| Hide vault or project-dir? | Project-dir | drafts must be visible in IDE |
| Role prompts change? | No | they become LangGraph agent system prompts, same text |
| LLM in state transitions? | No | only at compile/select/draft; never decides transitions |

---

## Open questions

- Which LLM provider per role? (Anthropic for drafting, OpenAI for compiler?)
- SQLite or Postgres for the checkpointer? (SQLite for v2; Postgres for production)
- Single-user or multi-user from the start? (Single-user for v2)
- Should the wizard be a CLI or stay HTML? (stay HTML, matches v1 UX)

---

## Session continuation note

**To resume this work in a new session:**

> "Continue the SpielOS v2 plan at `/Users/shayan/Desktop/SpielOS/V2-PLAN.md`.
> Start with F1 (project-dir install). Run `cd ~/projects/test-vault && bash
> /Users/shayan/Desktop/SpielOS/install/install.sh` to verify each step."

The first task is **F1.A** (vault resolution: walk up from cwd looking for
`team/md.md`). The second is **F1.B** (default install path = cwd, not
`~/.spiel`). Both are small and verifiable in isolation.
