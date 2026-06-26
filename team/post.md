---
name: post
description: Dispatch a /post request. Parse mode, capture session, initialize state, invoke @director.
---

# /post

The /post slash command is the only entry point. The LLM (you) does these steps in order, then invokes @director. No explanations, no preamble, no questions.

## 1. Parse mode

- `/post <text>` → **topic** — `input: "<text>"`
- `/post` (no args) → **session** — capture the live conversation
- `/post @file:./path` → **topic** — read the file, use its contents as input
- `/post @file:./a.md @file:./b.md` → **topic** — concat the files

## 2. Generate run_id

```bash
VAULT=$(python3 tools/advance.py --show --quiet 2>/dev/null && echo "<resolved vault>" || true)
# Use the {vault_root} placeholder; the IDE substitutes the absolute path.
```

Compute the run_id from `content/.run-counter` (JSON `{date, n}`):
- If `date == today's date` → `n+1`
- Else → `n=1`
- Write back atomically. `run_id = "{date}-{n:03d}"`

If `.run-counter` does not exist, create it: `{"date": "<today>", "n": 1}` then `run_id = "<today>-001"`.

## 3. Session mode: capture the conversation

**Only when mode is `session` (no args).** Topic mode skips this step.

You (the LLM) must:
1. Strip the entire conversation into clean user + assistant text. Remove tool calls, tool results, system messages, and any `## state_history`/internal markers.
2. Extract the 5 signal fields (one each, short):
   - `decision`: one decision made this session
   - `number`: one measurable outcome
   - `lesson`: one thing learned
   - `pattern`: one recurring signal
   - `ship`: one thing that now exists
3. Extract the 6 body sections (each can be a list of bullets):
   - `patterns`, `decisions`, `what_we_did`, `shipped`, `numbers`, `lesson`
4. Build a `summary`: one line.
5. Build a `tags` list: 1-3 short tags.
6. Write a temporary JSON file at `/tmp/.spiel-capture-{run_id}.json` with this shape:

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

7. Call the capture tool with the clean transcript on stdin and the structured JSON:

```bash
python3 tools/capture-session.py \
  --vault {vault_root} \
  --transcript-stdin \
  --structured-json /tmp/.spiel-capture-{run_id}.json \
  --title "<one-line title>" \
  --status complete \
  --tags "comma,separated" 2>&1
```

8. The tool prints JSON to stdout with the path. The session log path is `content/sessions/YYYY-MM-DD-session-current.md` (relative to vault).

If the transcript is empty (no user/assistant text at all), **stop and report an error to the user**: "No transcript found. Type something in the conversation first, then `/post` again." Do not write a stub. Do not delegate.

## 4. Write content/current.md

The handoff file the rest of the pipeline reads. Always this shape:

**Session mode:**
```yaml
---
mode: session
session: content/sessions/YYYY-MM-DD-session-current.md
status: routing
run_id: <from step 2>
created_at: <ISO 8601>
source: <absolute path to session log, for the Director to read>
---
```

**Topic mode:**
```yaml
---
mode: topic
input: "<exact text after /post, or file contents>"
status: routing
run_id: <from step 2>
created_at: <ISO 8601>
source: <absolute path, or null if pure text>
---
```

Body is empty. The Strategist will fill `## Strategy`.

## 5. Initialize the state machine

```bash
python3 tools/advance.py \
  --init \
  --run-id <run_id> \
  --mode <session|topic> \
  --session "content/sessions/..."  # only in session mode
  --vault {vault_root} 2>&1
```

This writes `content/.state.json` atomically. If the file already exists from a previous run, it is overwritten (a fresh run always wins).

## 6. Advance from idle to director

```bash
# After capture in session mode:
python3 tools/advance.py --to director --by post --vault {vault_root} 2>&1

# In topic mode (skip capture):
python3 tools/advance.py --to capture --by post --vault {vault_root} 2>&1
python3 tools/advance.py --to director --by post --vault {vault_root} 2>&1
```

The state machine in `system/run-state.md` defines the allowed transitions.

## 7. Delegate

Invoke @director. No explanation. No preamble. The Director will read `content/current.md` and `content/.state.json` and proceed.

## Hard rules

- Use `{vault_root}` paths only. Never cwd. Never `~/`.
- Never write a stub session log. If the transcript is empty, fail.
- Never auto-pick at human checkpoints. The Director/Strategist/Writer/Editor/Publisher all use the `question` tool.
- Never explain, show thinking, or output preamble to the user.
- No em-dashes in any file content.
- If `content/.state.json` exists from a previous crashed run, the new `--init` overwrites it. The run starts fresh.
- If `content/.state.json` exists AND `status` is `active` or `paused` (a previous run is still in progress), ask the user: "Previous run is at step <step>. Continue or restart?" Use the `question` tool.
