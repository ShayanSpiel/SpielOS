# Draft Schema

Every draft is a markdown file with frontmatter. The schema is enforced by `tools/editor.py` (4 mechanical gates).

```markdown
---
title: "Clear title"
created: 2026-06-24
platform: x | linkedin | blog
status: draft | ready | posted | rejected
source: content/current.md
reader: "who this is for"
point: "the one thing they should believe"
angle: "the frame"
---

Body goes here.
```

## Directories

- `content/inbox/`: source notes
- `content/drafts/`: writer output
- `content/ready/`: editor-approved drafts
- `content/posted/`: published archive
- `content/rejected/`: rejected archive

## After Editor stamps a draft

`tools/editor.py stamp` adds 3 fields to the frontmatter atomically:

```yaml
gates_verdict: pass | fail
gates_stamped_at: 2026-06-26T05:00:00
gates_report:
  em_dash: {pass: true, message: "OK: No em-dashes"}
  banned_phrases: {pass: true, message: "OK: No banned phrases"}
  required_frontmatter: {pass: true, message: "OK: 8 required frontmatter fields present"}
  char_count: {pass: true, message: "OK (247 chars, X limit 280)"}
```

`gates_verdict: pass` is the green light for the Publisher. `gates_verdict: fail` causes the Publisher to refuse to dispatch (script check, not LLM wish). A missing `gates_verdict` also causes refusal — the Publisher tells the operator to run `editor.py stamp` first.

## The session log (a different schema)

Session logs are NOT drafts. They live in `content/sessions/YYYY-MM-DD-session-current.md` and have their own schema — see `system/session-schema.md`.

## The state machine (a different file)

Run state is NOT a draft. It lives in `content/.state.json` and has its own schema — see `system/run-state.md`. Owned by `tools/advance.py`, not by any role.
