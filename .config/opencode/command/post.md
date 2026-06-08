# /post

**State machine:** Content — SESSION → STRATEGY → DRAFT → GATES → QUEUE
**Template:** AGENTS.md

## Usage
```
/post               # Use most recent session log
/post [about topic] # Build session context around topic
```

## States
- SESSION_CAPTURE: read session log or ask user
- STRATEGY_LOAD: read tone-of-voice, content-types, strategy docs
- DRAFTING: apply templates, write drafts
- GATE_CHECK: standalone test + copywriting gates
- REVISING: fix failing gates (max 2 cycles)
- QUEUE: save to content/queue/ with full frontmatter

## Output
- Pillar mode: 1 blog + 3 LinkedIn + 5-10 X
- Casual mode: 1 LinkedIn + 1-3 X
