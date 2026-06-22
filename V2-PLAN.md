# SpielOS v2 — Plan

**Status:** Approved direction. Build in progress.
**Architecture:** Subagents + Skills + Tools. No LangGraph, no external LLM, no engine/ folder. The IDE's LLM (Claude / GPT / local — whatever the user is using) IS the orchestrator. The MD agent owns the 8-step procedure.

---

## The 3 problems (v1, shipped)

### P1. Hidden install = invisible drafts
Vault lived at `~/.spiel/`. Drafts hidden from IDE project tree. User couldn't open drafts, edit, or publish from their project. "Open project" in the IDE opened the user's project, not the Spiel vault.

### P2. Slash commands improvise instead of dispatch
`/post` loaded `post.md` (a prompt). The LLM read "delegate to MD" and **made a judgment call**. Most calls were wrong:
- Wrote a draft directly to cwd (user reported)
- Asked clarifying questions
- Skipped states
- Picked formats without the human checkpoint
- Never invoked the deterministic tools (banner.py, gates.py, buffer.py)

The LLM was the orchestrator. The role prompts in `team/*.md` were decoration the LLM read and improvised from. **None of the deterministic tools actually ran.**

### P3. Wizard was ~40% complete
Covers brand, ICP, positioning, offer, funnel, voice, methodology, archetypes. Missing: API token verification, engine knobs, banner template picker, gate strictness, template favorites, platform preferences, voice corpus, time/date format, per-platform CTA style.

---

## The 3 fixes (v2, this plan)

### F1. Subagents + Skills + Tools (the natural primitives)
The IDE's natural primitives map directly to the pipeline:

| Primitive | What it is | In SpielOS |
|---|---|---|
| **Subagent** | LLM with its own system prompt + tools, invokable by name | Each role (md, researcher, strategist, copywriter, editor, designer, publisher, analyst) |
| **Skill** | Reusable prompt bundle the LLM can invoke | icp_simulation, format_wizard, publish_wizard, voice_match, template_picker |
| **Tool** | Atomic Python operation the subagent calls via bash | gates.py, banner.py, publisher/*.py, analyst.py |
| **Orchestrator** | The agent that calls subagents in order | MD agent (its prompt IS the procedure) |

### F2. MD agent owns the strict 8-step procedure
MD's prompt is the pipeline. It walks 8 steps by delegating to subagents. Two human interrupts (types picker at copywriter, p/h/r at publisher). The LLM cannot skip steps, reorder, or add steps.

### F3. Same LLM as the user is already paying for
No external LLM API (no Anthropic API key needed). The IDE's primary LLM is the orchestrator. The role subagents are all the same LLM, just with different system prompts. The user pays for one model, one subscription.

### F4. (From prior discussion) Wizard expansion
Deferred. Wizard stays at 10 steps for v2. Can expand in v3.

---

## The 8 subagents (one per role)

```
team/md.md           → orchestrator. Owns the 8-step procedure.
team/researcher.md   → reads source, writes research notes to brief
team/strategist.md   → picks angle. Calls icp_simulation skill if session mode.
team/copywriter.md   → calls format_wizard skill (HUMAN). Writes drafts to queue/.
team/editor.md       → calls tools/gates.py. Loops back to copywriter on fail.
team/designer.md     → calls tools/banner.py. Writes banner path to frontmatter.
team/publisher.md    → calls publish_wizard skill (HUMAN). Dispatches via tools/publisher/*.
team/analyst.md      → calls tools/analyst.py. Updates perf.json.
```

Installed to `~/.config/opencode/agents/<name>.md` (and equivalents for Cursor, Claude Code).

## The 5 skills (reusable prompt bundles)

```
skills/icp_simulation/SKILL.md      → LLM-as-ICP reacts to a session
skills/format_wizard/SKILL.md       → asks "What types? X, LinkedIn, Blog, All"
skills/publish_wizard/SKILL.md      → asks "publish / hold / reject" per draft
skills/voice_match/SKILL.md         → how to match the user's voice register
skills/template_picker/SKILL.md     → how to score templates from the registry
```

Installed to `~/.config/opencode/skill/<name>/SKILL.md` (and equivalents).

## The 6 tools (deterministic Python, called via bash)

```
tools/gates.py                  → 15 mechanical checks. CLI: check <draft>
tools/banner.py                 → render banner PNG. CLI: render <draft>
tools/publisher/buffer.py       → publish via Buffer. CLI: publish <draft>
tools/publisher/twitter.py      → publish via X. CLI: publish <draft>
tools/publisher/linkedin.py     → publish via LinkedIn. CLI: publish <draft>
tools/analyst.py                → pull engagement. CLI: pull <post-id>
```

These are pure Python. No LLM. The subagent calls them via bash.

---

## The MD agent's prompt (the procedure)

```markdown
# MD — Marketing Director (orchestrator)

You orchestrate the SpielOS content pipeline. For each /post invocation:

## The 8-step procedure

1. **Parse the request** — read user args, decide session/topic/file mode
2. **Delegate to @researcher** — pass source + ICP. Wait for return.
   Verify brief has `## research` section.
3. **Delegate to @strategist** — pass brief.
   If session mode, strategist calls icp_simulation skill first.
   Wait. Verify brief has `## strategy` section.
4. **Delegate to @copywriter** — copywriter calls format_wizard skill
   (HUMAN INTERRUPT: types X/LinkedIn/Blog/All).
   Writes drafts. Wait. Verify drafts exist in content/queue/.
5. **Delegate to @editor** — editor calls tools/gates.py for each draft.
   If any fail, loop to step 4 (max 3 rounds). If all pass, continue.
6. **Delegate to @designer** — designer calls tools/banner.py for each draft.
   Wait. Verify each draft has `banner:` in frontmatter.
7. **Delegate to @publisher** — publisher calls publish_wizard skill
   (HUMAN INTERRUPT: publish/hold/reject per draft).
   For "publish": calls tools/publisher/*. For "reject": moves to rejected/.
   For "hold": leaves in queue.
8. **Delegate to @analyst** — analyst calls tools/analyst.py for each
   published draft. Updates perf.json. Done.

## Subagent map
- @researcher → reads source, writes research
- @strategist → picks angle (uses icp_simulation skill for session mode)
- @copywriter → writes drafts (uses format_wizard skill)
- @editor → runs gates (uses tools/gates.py)
- @designer → renders banner (uses tools/banner.py)
- @publisher → runs p/h/r + dispatch (uses publish_wizard skill + tools/publisher/*)
- @analyst → pulls engagement, updates perf (uses tools/analyst.py)

## Hard rules
- Always delegate. Never do the subagent's work yourself.
- Wait for subagent return before next step.
- Verify each step's output before proceeding.
- Two human interrupts are mandatory: at step 4 (types) and step 7 (p/h/r).
- No step can be skipped.
- If a subagent fails 3 times, escalate to user.
```

---

## The flow for `/post empty` (session mode)

```
1. /post empty in IDE
2. LLM (MD agent) reads post.md command: "delegate to @md"
3. @md runs the 8-step procedure:
   step 1: parse → scenario=session, source=today's session log
   step 2: @researcher
     - reads source, reads strategy/icp.md
     - calls LLM: extract patterns/decisions/shipped/numbers/lesson
     - writes to content/.brief.md under ## research
   step 3: @strategist
     - reads brief, calls icp_simulation skill (LLM-as-ICP reacts)
     - calls LLM: pick angle, template, archetype, funnel
     - writes to brief under ## strategy
   step 4: @copywriter
     - calls format_wizard skill (HUMAN: types picker)
     - user picks "X + LinkedIn"
     - reads brief, corpus, gates
     - picks 2 templates, calls LLM to write each
     - writes drafts to content/queue/2026-06-23-x.md, content/queue/2026-06-23-linkedin.md
   step 5: @editor
     - for each draft: `python3 tools/gates.py check <draft>`
     - if any fail: loop to step 4 (max 3)
     - if all pass: write gates: pass to frontmatter
   step 6: @designer
     - for each draft: `python3 tools/banner.py render <draft>`
     - writes banner: path to frontmatter
   step 7: @publisher
     - calls publish_wizard skill (HUMAN: p/h/r per draft)
     - for "publish": `python3 tools/publisher/buffer.py publish <draft>`
       → move to content/posted/
     - for "reject": move to content/rejected/
     - for "hold": leave in queue
   step 8: @analyst
     - for each published: `python3 tools/analyst.py pull <post-id>`
     - updates system/perf.json
4. MD reports summary to user
```

---

## What the LLM does (3 things, not more)

| Step | LLM call | Subagent |
|---|---|---|
| 2 (researcher) | Extract patterns/decisions/shipped/numbers/lesson from source | @researcher |
| 3 (strategist) | Pick angle, template, archetype, funnel | @strategist |
| 4 (copywriter) | Write N drafts (one per type) | @copywriter |

**Three LLM invocations per /post run.** Everything else is Python (gates, banner, publish) or human (types, p/h/r).

---

## File structure (no engine/ folder)

```
spielos/
├── team/                       # subagent prompts (8 files)
│   ├── README.md
│   ├── md.md                   # ORCHESTRATOR (the procedure)
│   ├── researcher.md
│   ├── strategist.md
│   ├── copywriter.md
│   ├── editor.md
│   ├── designer.md
│   ├── publisher.md
│   ├── analyst.md
│   └── post.md                 # user-facing entry, delegates to @md
│
├── skills/                     # reusable prompt bundles
│   ├── icp_simulation/SKILL.md
│   ├── format_wizard/SKILL.md
│   ├── publish_wizard/SKILL.md
│   ├── voice_match/SKILL.md
│   └── template_picker/SKILL.md
│
├── tools/                      # deterministic Python
│   ├── gates.py
│   ├── banner.py
│   ├── analyst.py
│   ├── researcher.py
│   ├── sync_adapters.py
│   └── publisher/
│       ├── buffer.py
│       ├── twitter.py
│       ├── linkedin.py
│       └── blog.sh
│
├── system/                     # config + state
│   ├── state.json
│   ├── perf.json
│   ├── brand.json
│   ├── rules.yaml
│   └── gates.md
│
├── strategy/                   # user-edited knowledge
│   ├── icp.md, positioning.md, offer.md, funnel.md
│   ├── voice.md, corpus.md, methodology.md, archetypes.md
│
├── content/                    # pipeline output
│   ├── .brief.md
│   ├── .brief/                 # archived
│   └── {sessions, queue, posted, rejected}/
│
├── templates/                  # post templates
│   ├── x-post.md, linkedin-post.md, blog-post.md
│   └── registry/viral-templates.yaml
│
├── assets/                     # banners, icons, fonts
│
├── install/                    # install + wizard
│   ├── install.sh
│   ├── uninstall.sh
│   └── wizard/
│
├── adapters/                   # auto-gen per-IDE
│
├── bin/spiel                   # thin CLI
│
├── tests/
│
├── AGENTS.md
├── README.md
├── V2-PLAN.md (this file)
└── package.json
```

---

## The "no rabbit hole" invariants

1. **LLM is invoked at exactly 3 subagents**: researcher, strategist, copywriter. Each is one LLM call.
2. **LLM never decides state transitions**. The MD agent's prompt defines the order; no improvisation.
3. **LLM never picks formats or publish decisions**. Human does, via skills (format_wizard, publish_wizard).
4. **LLM always writes a string to a file the subagent controls**. The subagent calls a tool to write.
5. **No tool is invoked by the LLM directly**. Subagents call tools via bash. The LLM doesn't run bash on its own initiative.
6. **No step can be skipped**. The MD agent's procedure has 8 fixed steps. No conditional branching except the editor→copywriter loop.

---

## Build order (in progress)

- [x] **A.** Delete my 11 drafts + .venv/ (already done in the cleanup)
- [ ] **B.** Update `team/md.md` to be the strict 8-step orchestrator
- [ ] **C.** Build `skills/` with 5 SKILL.md files
- [ ] **D.** Verify `tools/gates.py`, `tools/banner.py`, `tools/publisher/*`, `tools/analyst.py` work as CLIs
- [ ] **E.** Update `tools/sync_adapters.py` to install team/*.md as subagents + skills/*.md as Agent Skills
- [ ] **F.** Tests: subagent installs, skill installs, gates CLI
- [ ] **G.** Update `AGENTS.md`, `V2-PLAN.md`, `README.md`

---

## Decisions log

| Question | Answer | Why |
|---|---|---|
| LangGraph or subagents? | Subagents | The IDE's natural primitive. No external orchestration layer. |
| External LLM (Anthropic API) or same LLM? | Same LLM | User is paying for one subscription. No separate API key. |
| Where does the procedure live? | team/md.md | The MD agent's prompt IS the procedure. No separate doc. |
| Where do skills live? | skills/<name>/SKILL.md | Standard Agent Skills format. |
| Where do tools live? | tools/<name>.py | Existing. Called via bash from subagents. |
| How does MD delegate? | `@-mention` subagent in opencode / `Agent` tool in Claude Code | Native primitive of each IDE. |
| How does a subagent invoke a skill? | Read the SKILL.md, follow its instructions | Native primitive. |
| How does a subagent invoke a tool? | `python3 tools/<name>.py <args>` via bash | Native primitive. |
| Where does state live? | Files: content/.brief.md, content/queue/*.md, system/perf.json | No database. Atomic per /post run. |
| Wizard expansion (F4)? | Deferred to v3 | v2 ships the pipeline refactor first. |

---

## Open questions

- **Two human interrupts** (types picker + p/h/r) — confirmed by user. Mandatory.
- **Designer is its own node after editor** — confirmed. v1 model.
- **LLM provider** — same as the IDE's. Whatever the user is using.
- **State tracking** — not in v2. Each /post run is atomic.

---

## Session continuation note

**To resume this work in a new session:**

> "Continue the SpielOS v2 plan at `/Users/shayan/Desktop/SpielOS/V2-PLAN.md`.
> Current step: B. Update `team/md.md` to be the strict 8-step orchestrator.
> The current build is at commit `d75272f` (the plan) and the prior commits
> on `cc42f5a` (slash commands fix) and `252249a` (auto-fix broken symlink)."

The next concrete step is **B**: read `team/md.md`, rewrite it as the
strict 8-step orchestrator prompt. Then **C**: create the 5 skills/ folders
with SKILL.md files. Then **D**: verify tools/.py work as CLIs.
