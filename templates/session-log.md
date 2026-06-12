---
title: Session Log Template
type: template
tags: [content-strategy, template, operational-pattern]
created: 2026-06-06
updated: 2026-06-06
sources: [concepts/content-strategy.md, templates/pillar-outline.md]
confidence: high
---

# Session Log Template

Use this template for every work session. The session log is the *input* to the [[funnel-and-matrix|pillar method]] — the system reads the log, runs the [[voice-and-gates|type decision tree]], and outputs draft posts.

Copy to `content/sessions/YYYY-MM-DD-session-NN.md` and fill in.

## Frontmatter

```yaml
---
title: <short title of the session>
date: YYYY-MM-DD
session_id: <NN>
tags: [<relevant tags>]
produces_pillar: <yes | no>
pillar_outline: <path to the pillar outline, or "none">
drafts:
  - <paths to the drafts this session produced>
status: complete | in-progress
reader_failure_mode:
  belief: <what the reader wrongly believes — their incorrect assumption>
  consequence: <what breaks because of that belief — the cost of being wrong>
  mapping: <how this session proves the belief is wrong — use specific session evidence>
---
```

## What we did (3-7 bullets)

- <the concrete things done in this session. each bullet is a fact, not a story.>
- <if a fact, it is reusable in a post. if it is a feeling, it is not.>
- <the wiki is the source. the post is the sample.>
- <specifics only. "I rebuilt the X" not "I worked on the X".>

## Decisions made

- <the choices made in this session, with the tradeoff explained>
- <"I picked A over B because C" is a decision. "I picked A" is a fact.>

## Lessons learned

- <the abstractions — what was learned, not what was done>
- <"frontmatter is a contract" is a lesson. "I wrote frontmatter" is a fact.>

## Surprises / failures

- <the things that did not work, the things that surprised>
- <a failure is more shareable than a success — see [[voice-and-gates]] confessional pattern>

## Numbers

- <any specific number from the session — $5, 30 pages, 4 files, 12-second load time>
- <numbers are the most save-worthy parts of a post>

## Pillar decision

- [ ] **Pillar? yes** — work is a system, a turning point, a story, a correction, or a teaching
- [ ] **Pillar? no** — work is a small ship, a quick opinion, a daily dev log, or an announcement

If yes, create a [[blog-post]] in `content/queue/YYYY-MM-DD-pillar-outline.md` and start drafting the pillar.

If no, run the [[voice-and-gates|type decision tree]] to identify 1-3 quick post drafts.

## Post candidates (filled in by /post)

(after `/post` runs, this section is populated with the candidate drafts and their types/patterns)

- [ ] <post title> — <type> — <pattern> — <path>
- [ ] <post title> — <type> — <pattern> — <path>

## Check before saving

- [ ] 3-7 bullets in "what we did"
- [ ] At least 1 "decisions made" or "lessons learned" (these are the post seeds)
- [ ] Specific numbers recorded
- [ ] Pillar decision is yes/no with reason
- [ ] If pillar: pillar outline is started
- [ ] If no pillar: post candidates are listed

## Related

- [[funnel-and-matrix]] — the operating context
- [[funnel-and-matrix]] — the strategy and atomization workflow
- [[voice-and-gates|content types]] — the type decision tree
- [[blog-post]] — the pillar planning template
