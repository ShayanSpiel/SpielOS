# X Post Template

Reference shape for the @writer. Copy to `content/drafts/YYYY-MM-DD-x.md` and fill in. The draft must pass `tools/editor.py` (4 gates: em_dash, banned_phrases, required_frontmatter, char_count).

## Frontmatter (8 fields)

```yaml
---
title: Clear title — names pain or payoff, NOT the project name
created: 2026-06-25
platform: x
status: draft
source: content/current.md
reader: who this is for
point: the one thing they should believe
angle: the frame for the post
---
```

## Body

```markdown
<one block: hook → tension → body. blank lines between every sentence.>

<one line: ask or punchline>
```

(char count: <number>, must be ≤ 280)

## Notes

- First line is the hook. It must be specific, not generic.
- Every line on its own. Blank line between paragraphs.
- One idea per post.
- No em-dashes. Use →, colons, or commas.
- Sound like a builder, not a marketer.
- Match the rhythm in `strategy/examples.md`.
