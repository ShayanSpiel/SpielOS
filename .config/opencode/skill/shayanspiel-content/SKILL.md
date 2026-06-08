# SKILL — SpielEngine Content Engine

Triggers on: `/post`, "post", "tweet", "content", "X", "LinkedIn", "blog".

## Contract

This skill converts session work into platform drafts. It follows the Content Posting state machine in AGENTS.md. Every action has a gate. Every draft must pass quality checks before entering the queue.

## Workflow

### 1. Session Capture
- Read most recent session log from `content/sessions/`
- If none: ask user what they worked on
- Determine if this is a pillar-worthy topic

### 2. Strategy Load
Read these strategy pages from the wiki:
- `concepts/tone-of-voice.md`
- `concepts/content-strategy.md`
- `concepts/content-types.md`
- `concepts/standalone-quality-test.md`
- `concepts/platform-format-specs.md`

### 3. Drafting
- Pillar = blog + 3 LinkedIn + 5-10 X
- Casual = 1 LinkedIn + 1-3 X
- Each draft uses templates from `templates/`
- Apply voice from strategy docs

### 4. Gate Check
Every draft must pass:
- Standalone quality test (no-prior-episode, value-without-me)
- Platform format specs (char limits, structure)
- Voice match against tone guide

### 5. Queue
Save to `content/queue/` with full frontmatter including scores.
