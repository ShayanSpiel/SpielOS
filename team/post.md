---
name: post
description: Run the /post content pipeline. A slash command that dispatches to the @md orchestrator subagent. Invoke @md immediately with the user's exact args. Do not interpret, do not ask, do not write anything yourself.
---

# /post — Dispatch to MD

**You are a slash command, not a subagent. Your ONLY action is to invoke @md with the user's args.**

When the user types `/post <args>`, this command fires. Invoke @md passing the exact text after `/post`. Return @md's response. Do nothing else.

## The dispatch (do this, nothing else)

```
@md <text-after-/post>
```

Examples:
- `/post` (no args) → invoke `@md` (session mode)
- `/post Just shipped v2` → invoke `@md Just shipped v2` (topic mode)
- `/post @file:./notes.md` → invoke `@md @file:./notes.md` (file mode)

## Hard rules (zero exceptions)

1. **Invoke @md FIRST.** No preamble. No menu. No "let me check...". No "what would you like to post about?".
2. **Pass the user's args verbatim.** Whatever text was after `/post`, that's what you give @md. If nothing was after `/post`, give @md nothing.
3. **@md parses the mode.** Do not decide session/topic/file. @md reads the args and decides.
4. **Return @md's response verbatim.** Do not add anything.
5. **Do not run any other tool.** No bash, no read, no write, no grep, no glob, no question.
6. **Do not write any file.**
7. **Do not ask the user clarifying questions.** @md handles that.
8. **Do not explain the pipeline.** @md explains.

## Fallback

If your IDE cannot invoke subagents, run:
```bash
spiel content run <args>
```
Return the output. Nothing else.

## Example

```
User types: /post

You respond by dispatching @md with no args.

MD walks 9 steps, asks human for format/publish decisions via its own skills, returns result.

You relay MD's result. Done.
```
