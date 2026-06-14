---
title: Session-as-Content Methodology
type: concept
tags: [engine, methodology]
---
# Session as Content

Turning work sessions into platform-native posts.

## Core Principle
The session is NOT the subject. The ICP's world is the subject.
The session is evidence that something in the ICP's world is true or false.

## Session Schema

### Required frontmatter
```yaml
title:
date:
session_id:
tags:
produces_pillar: yes | no
pillar_outline: path | none
drafts:
status: complete | in-progress
reader_failure_mode:
  belief:
  consequence:
  mapping:
```

### Required sections
1. **What we did** (3-7 bullets)
2. **Decisions made** (trade-offs explained)
3. **Lessons learned** (abstractions, not facts)
4. **Surprises / failures**
5. **Numbers** (specific data points)
6. **Pillar decision**

## Pipeline
1. Session captured → content/sessions/
2. Strategy loaded (archetype, vertical, funnel stage, ICP layer)
3. Content Engine Compiler runs (8 steps)
4. Drafts written → content/queue/
5. Gates passed
6. Published → content/posted/

## Anti-patterns
- Session as subject
- Tool-centric writing
- Architecture leaks
- Generic platitudes
- Missing reader grounding
