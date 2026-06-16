---
description: Start content pipeline — session or topic mode. Runs capture, compile, draft, gate, queue, publish.
---

# /post — Start Content Pipeline

## Pipeline

Run the pipeline steps in strict sequence. Each `bash scripts/pipeline.sh <step>` runs as a separate bash invocation. Do not skip any step — skipping breaks the pipeline state.

## Pipeline

Starts and runs the content pipeline. Mode 1 (empty): session from today's log. Mode 2 (topic): creates a brief for that topic.

The full 13-step pipeline spec is in `.opencode/skill/spiel-content/SKILL.md`.

Usage: /post [topic]
