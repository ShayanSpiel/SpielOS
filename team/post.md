---
name: post
description: Parse mode, capture session (if needed), initialize state, invoke @strategist.
vault_root: "{vault_root}"
---

# /post

**The vault for this installation is `{vault_root}`.** All `content/`, `system/`, `tools/`, and `team/` paths in this command body are relative to that root. The `spiel` CLI is installed at `~/.local/bin/spiel` and works from any CWD — it resolves the vault automatically via `~/.config/spielos/config`.

You (the LLM) do these steps in order. No explanations, no preamble, no questions to the user. At the end, dispatch the next agent using whatever subagent / task tool your IDE exposes. Typing `@<role>` as text in your final message does NOT dispatch — invoke via tool.

## 1. Parse mode

- `/post <text>` → **topic** — `input: "<text>"`
- `/post` (no args) → **session** — capture the live conversation
- `/post @file:./path` → **topic** — read the file, use its contents as input
- `/post @file:./a.md @file:./b.md` → **topic** — concat the files

If the conversation has no user/assistant text at all (in session mode), **stop and report** to the user: "No transcript found. Type something in the conversation first, then `/post` again." Do not write a stub. Do not delegate.

## 2. Session mode: capture the conversation

**Only when mode is `session` (no args).** Topic mode skips this step.

You (the LLM) have the live conversation in your context. You must:

1. Strip the conversation into clean user + assistant text. Remove tool calls, tool results, system messages, and any internal markers.
2. Extract the 5 signal fields (one each, short):
   - `decision`: one decision made this session
   - `number`: one measurable outcome
   - `lesson`: one thing learned
   - `pattern`: one recurring signal
   - `ship`: one thing that now exists
3. Extract the 6 body sections (each can be a list of bullets):
   - `patterns`, `decisions`, `what_we_did`, `shipped`, `numbers`, `lesson_section`
4. Build a `summary`: one line.
5. Build a `tags` list: 1-3 short tags.
6. Write a temporary JSON file at `/tmp/spiel-capture.json` with this shape:

```json
{
  "decision": "...",
  "number": "...",
  "lesson": "...",
  "pattern": "...",
  "ship": "...",
  "summary": "...",
  "tags": ["..."],
  "patterns": ["..."],
  "decisions": ["..."],
  "what_we_did": ["..."],
  "shipped": ["..."],
  "numbers": ["..."],
  "lesson_section": ["..."]
}
```

7. Write the clean transcript (from step 1) to `/tmp/spiel-capture.md`.

## 3. Start the run

Use the `spiel post` CLI. It owns run_id generation, state init, handoff write, and advance to strategy. Do not call `tools/advance.py` directly for this — the CLI does it atomically. `tools/post.py` also auto-resets any prior run state at the top of `main()`.

**Topic mode:**

```bash
spiel post "<exact text after /post>"
```

**File mode:**

```bash
spiel post @file:./path.md
```

**Session mode** (after capture-session.py succeeded):

```bash
spiel post --mode session \
  --transcript-file /tmp/spiel-capture.md \
  --structured-json /tmp/spiel-capture.json \
  --title "<short title>" \
  --tags "build,ship"
```

The CLI prints `step: strategy` on success.

## 4. Get the next role

```bash
spiel next
```

It prints `next: @strategist`.

## 5. Delegate

**Invoke @strategist** using your IDE's subagent / task tool. The IDE will load `team/strategist.md` as its system prompt. The strategist will read `content/current.md` and `content/.state.json` and proceed.

If `spiel post` fails, run `spiel doctor` and surface the failing check to the user. Do not silently swallow errors.

## Hard rules

- Use `{vault_root}` paths only. Never cwd. Never `~/`.
- Never write a stub session log. If the transcript is empty, fail.
- Never explain, show thinking, or output preamble to the user. Just run the steps.
- No em-dashes in any file content.
- Never write to `content/drafts/`, `content/ready/`, `content/posted/`, or `content/rejected/`. Those are owned by Writer / Editor / Publisher.
- The LLM is the orchestrator. `spiel` and `tools/` are the hands.
- Do not pre-check whether files exist before running `spiel post`. The CLI is path-independent and works from any CWD.
