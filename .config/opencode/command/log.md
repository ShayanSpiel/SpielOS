# /log

**State machine:** System
**Template:** AGENTS.md

## Usage
```
/log                # Show last 10 log entries
/log 20             # Show last N entries
```

## Output
- Reads log.md from wiki root
- Shows the N most recent entries
- Each entry follows: `## [YYYY-MM-DD] action | subject`
