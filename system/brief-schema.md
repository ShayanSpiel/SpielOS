# Brief Schema

The `.brief.md` is the single handoff file for one `/post` run. Every role reads from it and writes to it. The state machine lives in `## state_history` at the bottom.

A new brief is created when MD enters `IDLE → SESSION_CAPTURE`. It is archived to `content/.brief/YYYY-MM-DD-NNN.md` when MD enters `COMPLETE_POST → IDLE`.

---

## Template

```markdown
---
run_id: 2026-06-22-001
created: 2026-06-22T18:08:00Z
state: GATE_CHECK
source: { kind: session, file: content/sessions/2026-06-22-session-...md }
formats: [x, linkedin, blog]
---

## strategist
core_insight: <one sentence — the ICP world shift>
meanings:
  systemic: <one sentence>
  behavioral: <one sentence>
  philosophical: <one sentence>
  contrarian: <one sentence>
  leverage: <one sentence>
  human: <one sentence>
selected_meaning: { axis: human, rationale: <one sentence> }
template_selection:
  x: [<template-id>, <template-id>, <template-id>]
  linkedin: [<template-id>, <template-id>, <template-id>]
  blog: [<template-id>, <template-id>]

## researcher
classification:
  archetype: <S1..S10>
  funnel: <TOFU|MOFU|BOFU>
  icp_layer: <L1|L2|L3|L4>
  vertical: <vertical-name>
evidence:
  session: <path to session log, or `null` if topic mode>
  topic_text: <the topic, or `null` if session mode>
  key_facts: [<3-7 bullets the Copywriter can quote>]

## copywriter
drafts:
  - file: content/queue/2026-06-22-x-taste-bottleneck.md
    template: x-ship-01
    hook: <first 80 chars>
    archetype: <S1..S10>
    axis: <one of the 6>
    funnel: <TOFU|MOFU|BOFU>
    voice_register: <confessional-teaching|...>
    self_check:
      soft_gates: { icp_gate: pass, hook_formula: pass, ... }
      voice: pass
  - file: content/queue/2026-06-22-linkedin-taste-bottleneck.md
    ...

## editor
gates: { char_count: pass, em_dash: pass, hook_check: pass, ... }  # 15 mechanical
soft: { icp_gate: pass, hook_formula: pass, no_repetition: pass, ... }  # 14 soft
verdict: pass | fail | warn
bounce_round: <1|2|3>  # only if GATE_CHECK → DRAFTING

## designer
banners:
  - draft: content/queue/2026-06-22-x-taste-bottleneck.md
    banner: assets/banners/2026-06-22-x-taste-bottleneck.png
  - draft: content/queue/2026-06-22-linkedin-taste-bottleneck.md
    banner: assets/banners/2026-06-22-linkedin-taste-bottleneck.png

## publisher
posted:
  - draft: content/queue/2026-06-22-x-taste-bottleneck.md
    post_ids: { x: "..." }
    urls: { x: "https://x.com/.../status/..." }
    archive: content/posted/2026-06-22-x-taste-bottleneck.md
held: []
rejected: []
skipped_cadence: []
failed: []

## analyst
engagement:
  - draft: content/posted/2026-06-22-x-taste-bottleneck.md
    views: <n>
    likes: <n>
    replies: <n>
    reposts: <n>
    pulled_at: <iso>
perf_delta: { <template-id>: { score: ±0.05, ... } }
template_rerank: { ... }

## state_history
- 2026-06-22T18:08:00Z IDLE
- 2026-06-22T18:08:05Z SESSION_CAPTURE
- 2026-06-22T18:08:30Z COMPILE
- 2026-06-22T18:09:00Z SELECT
- 2026-06-22T18:09:15Z FORMAT_WIZARD
- 2026-06-22T18:10:00Z DRAFTING
- 2026-06-22T18:14:00Z BANNER
- 2026-06-22T18:14:30Z GATE_CHECK
- ...
```

---

## Field ownership

| Section | Written by | Read by |
|---|---|---|
| frontmatter (`state`, `formats`) | MD | everyone |
| `## strategist` | Strategist | Copywriter, MD |
| `## researcher` | Researcher | Strategist, Copywriter, MD |
| `## copywriter` | Copywriter | Editor, MD |
| `## editor` | Editor | MD (gate verdict) |
| `## designer` | Designer | Publisher, MD |
| `## publisher` | Publisher | Analyst, MD |
| `## analyst` | Analyst | MD, Strategist (next run, template rerank) |
| `## state_history` | MD | MD only |

Each role writes its section **once** per state. A re-run of the same state is idempotent — the role first reads the existing section, computes a diff, and only overwrites the fields it owns.

---

## File location

While running: `content/.brief.md` (the active brief, one at a time).

When `COMPLETE_POST` fires: rename to `content/.brief/YYYY-MM-DD-NNN.md` where NNN is the run number for that day. This keeps the active brief discoverable while preserving history.

`.brief/` is gitignored — briefs are session artifacts, not source of truth.

---

## When sections are missing

If MD dispatches a role and the role's expected input section is missing:

- **Strategist without `## researcher`** → Strategist returns with `error: no researcher section`, MD reverts to SESSION_CAPTURE.
- **Copywriter without `## strategist`** → Copywriter returns with `error: no strategist section`, MD reverts to COMPILE.
- **Editor without `## copywriter`** → Editor returns with `error: no copywriter section`, MD reverts to DRAFTING.
- **Designer without drafts files** → Designer returns with `error: drafts files missing`, MD reverts to DRAFTING.
- **Publisher without `## editor.verdict: pass`** → Publisher returns with `error: editor verdict not pass`, MD reverts to GATE_CHECK.
- **Analyst without `## publisher.posted`** → Analyst returns with `error: no posted drafts`, MD reverts to PUBLISHING.

This is the **only** atomicity guarantee. Roles never silently proceed on missing inputs.
