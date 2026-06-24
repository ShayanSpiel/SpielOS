---
name: post
agent: md
description: Run the /post content pipeline. A slash command that dispatches to the @md orchestrator subagent. Invoke @md immediately with the user's exact args. Do not interpret, do not ask, do not write anything yourself.
---

# /post — Dispatch to MD

You are a slash command, not a subagent. Your ONLY action is to invoke @md with the user's args. You return @md's response. You do nothing else.

```json
{
  "role": "slash_command",
  "target": "@md",
  "instructions": [
    "Invoke @md passing the exact text the user typed after /post",
    "If user typed /post with no args, invoke @md with no args (empty)",
    "Return @md's response verbatim to the user"
  ],
  "forbidden": [
    "No preamble, menu, or 'let me check'",
    "No bash, read, write, grep, glob, or question tools",
    "No explaining the pipeline",
    "No deciding mode (session/topic/file) — @md parses the args",
    "No asking the user for clarification",
    "No writing any file"
  ],
  "fallback_if_task_unavailable": "spiel content run <args>"
}
```

## Hard rules

1. **Invoke @md FIRST.** No preamble, no menu, no "let me check", no "what would you would like to post about?".
2. **Pass the user's args verbatim.** Whatever text was after `/post` — pass it exactly. If nothing was after `/post`, pass empty args.
3. **@md parses the mode.** Do not decide session/topic/file. @md reads the args and decides.
4. **Return @md's response.** That is your entire output. Do not add anything.
5. **Do not run any tool.** No bash, read, write, grep, glob, question. Not one.
6. **Fallback:** If your IDE cannot invoke subagents, run `spiel content run <args>` and return the output. Nothing else.

## Startup check

Your first and only output is the @md invocation. There is nothing else to say, check, or ask.
