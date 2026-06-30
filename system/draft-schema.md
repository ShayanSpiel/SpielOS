# Draft Schema

Every draft is a markdown file with frontmatter. The schema is enforced by `tools/editor.py` (4 mechanical gates).

```markdown
---
title: "Clear title"
created: 2026-06-29
platform: x | linkedin | blog
status: draft | ready | posted | rejected
source: content/current.md

# 6 brief fields (lifted from ## Strategy in content/current.md)
reader: "One specific ICP, identity-rich"
pain: "Vivid scene: time anchor + action + failure + monologue + wrong attribution"
belief: "The OLD mental model"
point: "The NEW mental model. Contradicts belief."
meaning: "One sentence, first-person, ICP voice, the aha"
proof: ["<fact 1>", "<fact 2>", "<fact 3>"]
---

Body goes here.
```

## Directories

- `content/sessions/`: captured session logs (one per day, written by `tools/capture-session.py`)
- `content/drafts/`: writer output
- `content/ready/`: editor-approved drafts
- `content/posted/`: published archive
- `content/rejected/`: rejected archive

## Frontmatter — 11 required fields

The 4 mechanical gates read `required_frontmatter` from `system/rules.yaml`. Default list (11 fields):

```yaml
required_frontmatter:
  - title
  - created
  - platform
  - status
  - source
  # 6 brief fields (the full brief, in the draft frontmatter)
  - reader
  - pain
  - belief
  - point
  - meaning
  - proof
```

The Writer MUST include all 11 fields in every draft's frontmatter. The brief is the contract — the Writer cannot choose to drop `pain` or `meaning` because they don't fit a particular format. If a field doesn't apply to the format (e.g. `proof` for a 280-char X post), the Writer leaves it as an empty list `[]` for proof, or omits the field's content (frontmatter still has the key). The Editor's `required_frontmatter` gate only checks presence, not content.

## What's gone (from previous schema)

- `angle` — removed. The rhetorical frame is derivable from `belief → point` contrast. No separate field needed.
- `pillar`, `pattern` — removed. The `example_pattern` lives in `## Strategy` (the brief), not in the draft.

## After Editor stamps a draft

`tools/editor.py stamp` adds 3 fields to the frontmatter atomically:

```yaml
gates_verdict: pass | fail
gates_stamped_at: 2026-06-26T05:00:00
gates_report:
  em_dash: {pass: true, message: "OK: No em-dashes"}
  banned_phrases: {pass: true, message: "OK: No banned phrases"}
  required_frontmatter: {pass: true, message: "OK: 11 required frontmatter fields present"}
  char_count: {pass: true, message: "OK (247 chars, X limit 280)"}
```

`gates_verdict: pass` is the green light for the Publisher. `gates_verdict: fail` causes the Publisher to refuse to dispatch (script check, not LLM wish). A missing `gates_verdict` also causes refusal — the Publisher tells the operator to run `editor.py stamp` first.

## The session log (a different schema)

Session logs are NOT drafts. They live in `content/sessions/YYYY-MM-DD-session-current.md` and have their own schema — see `system/session-schema.md`.

## The simulator output (a different file)

The simulator runs in BOTH session and topic mode. Its output is `content/.icp-world.json` and has its own schema — see `system/icp-world-schema.md`. The Editor's `grounding_check` gate (5th gate) validates that the brief in `## Strategy` is grounded in this file. In topic mode, the simulator still runs but with lower volume.

## The brief (a different file)

The Strategist writes `## Strategy` to `content/current.md` before the Writer runs. The brief has:

- **6 content fields** (`reader`, `pain`, `belief`, `point`, `proof`, `meaning`) — lifted from `.icp-world.json`
- **Writer Instructions** (`example_pattern`, `volume`, `formats`)

The Writer reads the brief, renders the 6 fields per the volume config, and writes the draft with all 6 fields in the frontmatter.

The Editor's `grounding_check` (5th gate) validates: the brief's 6 fields are present, the simulator output is complete, `proof` is grounded in ICP language (not build-log), `point` blends offer.md, and `example_pattern` is present in session mode.

## The state machine (a different file)

Run state is NOT a draft. It lives in `content/.state.json` and has its own schema — see `system/run-state.md`. Owned by `tools/advance.py`, not by any role.
