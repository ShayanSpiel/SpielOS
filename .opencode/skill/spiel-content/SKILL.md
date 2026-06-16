---
name: spiel-content
description: Spiel content engine — drafts X / LinkedIn / blog posts. Triggers on "post", "tweet", "content", "X", "Twitter", "LinkedIn", "blog", "spiel", "/post".
---

## Pipeline

Run the pipeline steps in strict sequence. Each `bash scripts/pipeline.sh <step>` runs as a separate bash invocation. Do not skip any step — skipping breaks the pipeline state.

## Dependencies

This skill requires `scripts/pipeline.sh`, `scripts/engine.py`, and `scripts/gates.py` in the vault. No bundled scripts.

---

# Spiel Content — Content Engine Skill

**The full spec lives in:** `.opencode/commands/post.md` (canonical pipeline).

**Voice source of truth:** `concepts/voice-and-gates.md`.

This file is the *in-session reference*. If you need the full pipeline with all gates, strategy pages, classification rules, and output format, read `.opencode/commands/post.md`.

---

## 🔒 EXECUTION ORDER — DO NOT DEVIATE

**This is a deterministic state machine. Every step below is a mandatory bash command that transitions the pipeline to the next state. Skipping any step = broken pipeline.**

`engine.py` blocks DRAFTING if `.content-brief.json` lacks `core_insight`, all 6 meanings, and `selected_meaning`. You CANNOT draft without running the Compiler.

### Pre-draft sequence (run IN ORDER before drafting)

**Step 1 — REQUIRED: `bash scripts/pipeline.sh post-compile`**
Run the Content Engine Compiler (8 steps: LOAD ICP WORLD → SIMULATE REALITY → EVIDENCE → MAP → 6 MEANINGS → SELECT → INSIGHT → GENERATE). Write `core_insight` and `selected_meaning` to `.content-brief.json`.

**Step 2 — REQUIRED: Read strategy pages**
`concepts/icp-offer.md`, `concepts/funnel-and-matrix.md`, `concepts/voice-and-gates.md`, `concepts/session-as-content.md`.

**Step 3 — REQUIRED: Read corpus**
Scan `concepts/voice-corpus.md`. Match your archetype to the closest example. Quote the opening line in your head before drafting.

**Step 4 — REQUIRED: Apply the lens**
`core_insight` is the subject. The session is ONLY evidence. Every post must feel like "this is about the ICP's world."

**Step 5 — REQUIRED: Format Decision**
Show the user the `core_insight`. Ask: "Draft for which formats? (x / linkedin / blog / all)". User MUST respond before drafting. Draft ONLY what they chose.

## 🔒 Post-write audit (run BEFORE showing user — skip = slop reaches user)

**Step 1 — REQUIRED: `bash scripts/pipeline.sh post-gate`**
Runs `gates.py --all` (16 mechanical checks). Fix all failures. If any fail → REVISE.

**Step 2 — REQUIRED: Run Quality Test (LLM-judged)**
- 4-check standalone test — does the post pass?
- 10-gate extended — are all boxes checked?
- Composite score: passes / total gates. Must be ≥ 0.85.
- If fail → REVISE (max 2 cycles) or SCRAP.

**Step 3 — REQUIRED: Read aloud**
Does it sound like lecture or checklist? Rewrite.

**Step 4 — REQUIRED: Hard Constraints**
No system talk, no session reference, no engineering notes. ICP present. Reader's world is the subject.

## Voice

- Lowercase i
- Short sentences, fast pacing
- Hook in first 2 lines
- Reader (ICP) is the subject
- Specific numbers
- Named reader ("founders", "builders", "operators")
- Landing line: thought, not summary

## 🔴 Pipeline Violations

| Violation | Consequence |
|-----------|-------------|
| Skip `post-start` | No `.content-brief.json`. Pipeline has no input. |
| Skip `post-compile` | No `core_insight`. Draft will be about "me" not ICP. |
| Skip 8-step Compiler | No ICP inversion. Post reads like a README. |
| Skip format decision | You draft format user didn't ask for. |
| Skip `post-draft` | State machine not updated. Next steps fail. |
| Skip LLM-judged gates | Slop reaches user. No quality floor. |

## What this skill does NOT do

No auto-publishing. No comment/DM handling. No offer redesign.

## When in doubt

**Read the steps in order. Run every bash command. Do not skip any step.**

The pipeline scripts enforce these gates. `engine.py` blocks DRAFTING if the Compiler hasn't run. If you try to draft without `.content-brief.json` having `core_insight`, the transition will fail with a specific error.

Read corpus post. Match voice. Run the gates — they are mandatory.
