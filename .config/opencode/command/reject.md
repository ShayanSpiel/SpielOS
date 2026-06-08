# /reject

**State machine:** Content — ARCHIVING (with AP append)
**Template:** AGENTS.md

## Usage
```
/reject [id] [reason]   # Reject draft + learn
```

## Action
- Read draft from content/queue/
- Move to content/rejected/
- Update frontmatter with rejected_at + reason
- Append anti-pattern entry to content/rejected/README.md
  - Pattern: what was tried
  - Why it failed: the reason
  - Lesson: what to do instead
