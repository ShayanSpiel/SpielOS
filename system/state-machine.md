# State Machine

The single source of truth for the content loop. **MD reads this on every step.**

The state machine is a markdown table. There is no Python orchestrator. MD (the LLM agent in `team/md.md`) reads the table, picks the next state, dispatches the next role, waits for its section to be appended to `.brief.md`, advances the state. The previous role's output is the next role's input. The pipeline is role-chained.

---

## The 10 states

| # | State | From | Role | Output check | Next states |
|---|---|---|---|---|---|
| 0 | IDLE | (any) | MD | new run? | SESSION_CAPTURE |
| 1 | SESSION_CAPTURE | IDLE | Researcher | `## researcher` populated | COMPILE / IDLE |
| 2 | COMPILE | SESSION_CAPTURE | Strategist | `## strategist.core_insight` | SELECT / IDLE |
| 3 | SELECT | COMPILE | Strategist | `template_selection` ≥ 1 | DRAFTING / IDLE |
| 4 | DRAFTING | SELECT | Copywriter | `## copywriter.drafts` ≥ 1 | BANNER / IDLE |
| 5 | BANNER | DRAFTING | Designer | each draft has `banner:` | GATE_CHECK |
| 6 | GATE_CHECK | BANNER | Editor | `verdict: pass` | PUBLISHING / DRAFTING |
| 7 | PUBLISHING | GATE_CHECK | Publisher | `## publisher` populated | ANALYZING_POST / IDLE |
| 8 | ANALYZING_POST | PUBLISHING | Analyst | `## analyst.engagement` | COMPLETE_POST |
| 9 | COMPLETE_POST | ANALYZING_POST | MD | `.brief.md` archived | IDLE |

Human checkpoints are no longer separate states. Each role owns its own user interaction:

- **Copywriter (DRAFTING)** — asks user which formats to write (x, linkedin, blog)
- **Publisher (PUBLISHING)** — asks user per-draft publish/hold/reject

Roles use the IDE's `question` tool to ask. The question propagates up to the user automatically. MD never handles human interrupts.

---

## Hand-off discipline

- Each subagent writes its `## <role>` section, then returns.
- MD reads the last line of `## state_history`, looks up the row above, dispatches the next role.
- 15-minute idle between role calls = state expires → MD reverts to IDLE.
- One state at a time. No parallel roles. No skipping.

## Crash recovery

`## state_history` is append-only. If MD reads a brief and the last entry is `BANNER`, the pipeline is mid-banner — MD asks "continue from BANNER, or restart from IDLE?" before doing anything.

If `## state_history` is empty, MD assumes `IDLE` and starts a new run.

## Human interaction (embedded in roles)

Two roles interact with the user via the `question` tool:

| Role | State | What it asks | Input shape |
|---|---|---|---|
| Copywriter | DRAFTING | Which platforms? | `x`, `linkedin`, `blog`, `x linkedin`, `all`, `hold` |
| Publisher | PUBLISHING | Per-draft p/h/r? | `p`, `h`, `r <reason>` |
| Publisher | PUBLISHING | Confirm all decisions | `y` / `N` |

If the user says `hold` at format pick, Copywriter returns with no drafts — MD goes to IDLE.
If the user holds/rejects all at publish review, Publisher returns with `posted: []` — MD skips ANALYZING_POST.

## Bounce rule

- **GATE_CHECK → DRAFTING** if any draft failed mechanical gates. Editor calls `tools/editor.py` once more after Copywriter's fix. Max 3 bounce rounds; after 3, MD moves to PUBLISHING anyway with a `verdict: warn` flag.

## Hold / Reject

- **Hold** = draft stays in `content/queue/`, decision is null. Publisher logs it. Next `/post` run enters PUBLISHING for those held drafts.
- **Reject** = draft moves to `content/rejected/` with a `rejection_reason:` frontmatter field. Engine learns nothing from this (no LLM-judged adaptation in MVP).

## Idempotency

Re-running the same state is safe:
- **Re-running BANNER** = re-render only the drafts missing `banner:`.
- **Re-running GATE_CHECK** = re-run only drafts with `gates: fail` or no `gates:`.
- **Re-running PUBLISHING** = re-publish only drafts with decision `publish` that aren't already in `content/posted/`.

MD checks the brief's `## state_history` and the draft's frontmatter to decide what to skip.
