# /config

**State machine:** System
**Template:** AGENTS.md

## Usage
```
/config                    # Show current config
/config posting.mode auto-threshold  # Set config value
```

## Config Keys
- `posting.mode`: manual | auto-threshold | auto-always
- `posting.quality_threshold`: 0.0-1.0
- `posting.require_confirm`: [blog, linkedin]
- `posting.max_auto_day`: number
