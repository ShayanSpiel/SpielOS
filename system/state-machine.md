# State Machine

The single source of truth for the content loop. **MD reads this on every step.**

The state machine is a markdown table. There is no Python orchestrator. MD (the LLM agent in `team/md.md`) reads the table, picks the next state, dispatches the next role, waits for its section to be appended to `.brief.md`, advances the state. The previous role's output is the next role's input. The pipeline is role-chained.

---

## The 12 states

| #  | State              | From              | Role           | Output check                       | Next states                       |
|----|--------------------|-------------------|----------------|------------------------------------|-----------------------------------|
| 0  | IDLE               | (any)             | MD             | new run?                           | SESSION_CAPTURE / PUBLISH_REVIEW  |
| 1  | SESSION_CAPTURE    | IDLE              | Researcher     | `## researcher` populated          | COMPILE / IDLE                    |
| 2  | COMPILE            | SESSION_CAPTURE   | Strategist     | `## strategist.core_insight`       | SELECT / IDLE                     |
| 3  | SELECT             | COMPILE           | Strategist     | `template_selection` ≥ 1           | FORMAT_WIZARD / IDLE              |
| 4  | FORMAT_WIZARD      | SELECT            | MD (human)     | `formats: [x,linkedin,blog]`       | DRAFTING / IDLE                   |
| 5  | DRAFTING           | FORMAT_WIZARD     | Copywriter     | `## copywriter.drafts` ≥ 1         | BANNER / IDLE                     |
| 6  | BANNER             | DRAFTING          | Designer       | each draft has `banner:`           | GATE_CHECK                        |
| 7  | GATE_CHECK         | BANNER            | Editor         | `verdict: pass`                    | PUBLISH_REVIEW / DRAFTING         |
| 8  | PUBLISH_REVIEW     | GATE_CHECK        | MD (human)     | per-draft p/h/r/s decided          | PUBLISHING / IDLE                 |
| 9  | PUBLISHING         | PUBLISH_REVIEW    | Publisher      | `## publisher.posted` ≥ 1          | ANALYZING_POST                    |
| 10 | ANALYZING_POST     | PUBLISHING        | Analyst        | `## analyst.engagement`            | COMPLETE_POST                     |
| 11 | COMPLETE_POST      | ANALYZING_POST    | MD             | `.brief.md` archived               | IDLE                              |

---

## Hand-off discipline

- Each role writes its `## <role>` section, appends the next state to `## state_history`, returns.
- MD reads the last line of `## state_history`, looks up the row above, dispatches the next role.
- 15-minute idle between role calls = state expires → MD reverts to IDLE.
- One state at a time. No parallel roles. No skipping.

## Crash recovery

`## state_history` is append-only. If MD reads a brief and the last entry is `BANNER`, the pipeline is mid-banner — MD asks "continue from BANNER, or restart from IDLE?" before doing anything.

If `## state_history` is empty, MD assumes `IDLE` and starts a new run.

## Human checkpoints

- **FORMAT_WIZARD (state 4)** — MD prints the format picker verbatim, waits for the user's answer. Allowed: `x`, `linkedin`, `blog`, `x linkedin`, `x,blog`, `1`-`7`, `all`, `hold`.
- **PUBLISH_REVIEW (state 8)** — MD prints one panel per draft, waits for the user's `p`/`h`/`r <reason>`/`s` per draft, then a final `y`/`N` confirm.

**MD NEVER auto-picks at checkpoints.** Always prints the banner and waits. The subagent in the IDE relays the banner to the user, pipes the answer back.

---

## Bounce rule

- **GATE_CHECK → DRAFTING** if any draft failed mechanical gates. Editor calls `tools/editor.py` once more after Copywriter's fix. Max 3 bounce rounds; after 3, MD moves to PUBLISH_REVIEW anyway with a `verdict: warn` flag.
- **PUBLISH_REVIEW → IDLE** if user picks `hold` (return to queue for later) or `reject` (move to `content/rejected/`).

## Hold / Reject

- **Hold** = draft stays in `content/queue/`, decision is null. MD re-enters `PUBLISH_REVIEW` next time `/post` is called.
- **Reject** = draft moves to `content/rejected/` with a `rejection_reason:` frontmatter field. Engine learns nothing from this (no LLM-judged adaptation in MVP).

## Idempotency

Re-running the same state is safe:
- **Re-running BANNER** = re-render only the drafts missing `banner:`.
- **Re-running GATE_CHECK** = re-run only drafts with `gates: fail` or no `gates:`.
- **Re-running PUBLISHING** = re-publish only drafts with decision `publish` that aren't already in `content/posted/`.

MD checks the brief's `## state_history` and the draft's frontmatter to decide what to skip.
