# /optimize

**State machine:** Content — GATE_CHECK + REVISING
**Template:** AGENTS.md

## Usage
```
/optimize [id]      # Re-run gates on draft, improve
```

## Action
- Read draft from content/queue/
- Re-run standalone quality test and copywriting gates
- Identify which gates failed
- Regenerate failing sections
- Re-run gates (max 2 cycles)
- Update composite score in frontmatter
