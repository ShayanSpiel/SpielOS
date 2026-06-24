# Blog Post Template

Reference shape for the @writer. Copy to `content/drafts/YYYY-MM-DD-blog.md` and fill in. The draft must pass `tools/editor.py` (4 gates: em_dash, banned_phrases, required_frontmatter, char_count). Blog uses word count (≤ 2500).

## Frontmatter (8 fields)

```yaml
---
title: H1 — the post title
created: 2026-06-25
platform: blog
status: draft
source: content/current.md
reader: who this is for
point: the one thing they should believe
angle: the frame for the post
---
```

## Body

```markdown
# <H1>

## Intro (3-5 sentences, the hook)

<state the problem in 2-3 sentences. do not preamble. no "in this article, I will...".>

## <H2 Section 1>

<1 idea. 200-300 words.>

## <H2 Section 2>

<1 idea. 200-300 words.>

## <H2 Section 3>

<1 idea. 200-300 words.>

## <H2 Section 4 (optional)>

<1 idea. 200-300 words.>

## Conclusion (1 paragraph)

<the one-line takeaway. the landing.>
```

## Notes

- ≤ 2500 words total.
- No em-dashes. Use →, colons, or commas.
- Sound like a builder, not a marketer.
- Match the rhythm in `strategy/examples.md`.
