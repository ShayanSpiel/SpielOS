# LinkedIn Post Template

Reference shape for the @writer. Copy to `content/drafts/YYYY-MM-DD-linkedin.md` and fill in. The draft must pass `tools/editor.py` (4 gates: em_dash, banned_phrases, required_frontmatter, char_count).

## Frontmatter (8 fields)

```yaml
---
title: Clear title — names pain or payoff, NOT the project name
created: 2026-06-25
platform: linkedin
status: draft
source: content/current.md
reader: who this is for
point: the one thing they should believe
angle: the frame for the post
---
```

## Body

```markdown
## Hook (2 lines, must pass the 5-second test in feed)

<line 1 — counter-intuitive, specific number, named pain, or aha>
<line 2 — the tension, the contradiction, the surprise>

[LINE BREAK — critical for mobile readability]

## Setup

<1-2 short paragraphs. every sentence on its own line. blank line between paragraphs.
line 3 of the post (after the hook) is the promise — what the reader gets if they keep reading.>

## Core

<1-3 paragraphs that carry the argument, the story, or the question.
800-3000 chars total.>

## Lesson (last 1-2 lines)

<the lesson is the *last* line, not the first.>

## Ask (last line)

<one short ask — not "Like if you agree", not engagement bait.>
```

## Notes

- First 2 lines are the hook. They must stop the scroll.
- Every sentence on its own line. Blank line between paragraphs.
- One idea per post.
- No em-dashes. Use →, colons, or commas.
- Sound like a builder, not a marketer.
- Match the rhythm in `strategy/examples.md`.
- char count must be ≤ 3000.
