# /post — Start Content Pipeline

Starts the content pipeline. Mode 1 (empty): checks for a today's session log.
Mode 2: `<topic>` creates a brief for that topic.

Usage: /post [topic]

1. Runs `bash scripts/pipeline.sh post-start [topic]`
2. Loads strategy from concepts/
3. Runs 8-step Compiler
4. Writes drafts to content/queue/
5. Runs gates

See concepts/voice-and-gates.md for the methodology.
