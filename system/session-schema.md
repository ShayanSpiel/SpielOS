# Session Schema

A session is a single work session. The session log is the canonical input for `/post` (no args). One file per day, overwritten on the next `/post`.

**Path:** `content/sessions/YYYY-MM-DD-session-current.md`

**Writer:** `tools/capture-session.py` (atomic write, vault-resolved).

## Frontmatter (machine-parseable)

```yaml
---
session_id: current
date: 2026-06-26
decision: <one decision made this session>
number: <one measurable outcome>
lesson: <one thing learned>
pattern: <one recurring signal observed>
ship: <one thing that now exists that did not before>
status: complete | in-progress
captured_by: capture-session.py
captured_at: 2026-06-26T12:00:00
message_count: <n>
tags: [build, ship]
---
```

The 5 signal fields (`decision`, `number`, `lesson`, `pattern`, `ship`) are the strategist's quick-read. They are the evidence the Strategist maps to the 6 brief fields (reader, pain, point, proof, angle, formats). At least 1 of the 5 must be non-empty; if all 5 are empty, the Strategist should ask the user to add evidence or stop.

## Body (human-readable, Strategist reads this)

```markdown
# Current Session

## Patterns recognized
- <recurring signal>

## Decisions made
- <decision>

## What we did
- <action>

## Shipped
- <artifact that now exists>

## Numbers
- <measurable>

## Lesson
- <thing learned>

## Transcript

\`\`\`
<raw user/assistant text, tool noise stripped>
\`\`\`
```

The Transcript section is the appendix. The 6 body sections above it are the structured summary the LLM extracts and passes to capture-session.py via `--structured-json`.

## Capture flow

`/post` (no args) follows this sequence:

1. The LLM (running as the Director subagent) collects clean user + assistant text from the live conversation. Strips tool calls, tool results, system messages.
2. The LLM extracts the 5 signal fields and the 6 body sections from the conversation.
3. The LLM writes a temporary `--structured-json` file with the 5 fields.
4. The LLM runs:

```bash
python3 tools/capture-session.py \
  --vault <resolved_vault> \
  --transcript-stdin \
  --structured-json <tmpfile> \
  --status complete \
  --title "<one-line>" \
  --tags "<comma,separated>"
```

5. The tool writes `content/sessions/YYYY-MM-DD-session-current.md` atomically.
6. The LLM writes `content/current.md` pointing to that path, and writes `content/.state.json` with `step: capture`.
7. The LLM calls `tools/advance.py --to director` to mark capture complete.
8. The Director takes over.

## Topic mode

`/post "text"` or `/post @file:./path` skips session capture. The input text is the source. `mode: topic` in `content/current.md`. `content/sessions/current.md` is not touched.

## Acceptance criteria (session capture is working when...)

1. `/post` (no args) always creates or overwrites today's current session log.
2. The path is always under the resolved vault, never cwd.
3. `content/current.md` points to the captured session path.
4. A user can run `/post` from another project and it still writes into the SpielOS vault.
5. The captured file has clean user/assistant text, no tool noise.
6. The transcript is preserved as an appendix.
7. The 6 body sections are filled enough for the Strategist to use.
8. If no transcript can be captured, `/post` fails with a clear message instead of silently drafting generic content.
