---
key: wizards
title: Wizard banners + subagent entry modes
audience: subagent (post subagent in IDE)
status: canonical
---

# Wizard banners + subagent entry modes

These strings are printed by `engine/wizard.py` at human checkpoints. The post subagent must read them, copy them to the user, and WAIT for the user's exact answer.

## Format wizard (FORMAT_WIZARD)

Engine prints at session/topic mode after the compiler handoff:

```
FORMAT WIZARD — Pick platforms. Subagent MUST ask the user.

╔════════════════════════════════════════════════════════════╗
║  HUMAN CHECKPOINT — DO NOT AUTO-PICK                      ║
║  Subagent: relay this prompt to the user and WAIT.        ║
║  Parent / non-TTY mode: pipe the user's exact answer.    ║
╚════════════════════════════════════════════════════════════╝

CORE INSIGHT
"<one-sentence summary of what the draft will deliver>"

  [x] X (280 chars, high volume)
  [ ] LinkedIn (3000 chars, medium volume)
  [ ] Blog (2500 words, low volume)

Commands: [x/X] Toggle X   [l] Toggle LinkedIn   [b] Toggle Blog
          [a] Select all/none   [h] Hold   [Enter] Confirm
```

Subagent must:
1. Copy the prompt to the user verbatim.
2. WAIT for the user's exact answer.
3. Pipe the answer via `echo "<answer>" | spiel content wizard`.

Allowed answer forms: `x`, `linkedin`, `blog`, `x linkedin`, `x,blog`, `1-7`, `all`, `hold`.

On empty answer (parent / non-TTY mode):

```
⚠ Empty answer. The wizard is waiting for the USER's reply.
  Subagent: relay this prompt to the user, then pipe their answer.
  Allowed forms: x, linkedin, blog, x linkedin, x,blog, 1-7, all, hold
```

## Publish wizard (PUBLISH_WIZARD)

Engine prints after mechanical gates pass, per draft:

```
PUBLISH WIZARD — Per-draft decision. Subagent MUST ask the user.

╔════════════════════════════════════════════════════════════╗
║  HUMAN CHECKPOINT — DO NOT AUTO-PICK                      ║
║  Subagent: show each draft panel and ask the user per    ║
║  draft. Pipe the user's exact p/h/r/s answers.            ║
╚════════════════════════════════════════════════════════════╝

  3 draft(s) ready

▸ 1. 2026-06-20-x-draft.md   [X]
    Hook: <first 80 chars of body>
    Gates: 28/29 pass (warn: 1 sentence cap)
    Topic kind: announcement

    p / h / r <reason> / s ?
```

Subagent must:
1. Show each panel.
2. Ask the user per-draft: publish / hold / reject (with reason) / skip.
3. WAIT for the user's full answer set.
4. Pipe via `printf "p\nh\nr <reason>\ns\ny\n" | spiel content publish-wizard`.

## Subagent entry modes

### Empty `/post`

```bash
VAULT=$(spiel --where)
python3 "$VAULT/engine/session_from_memory.py" \
    --out "$VAULT/content/sessions/$(date +%Y-%m-%d)-session-$(highest+1).md" \
    --include-subagents \
    --max-chars-per-part 2000
spiel content run --session-file <file>
```

The subagent synthesizes a session file from opencode DB (preferred) or fallback heuristics. Frontmatter required: `title`, `date`, `session_id`, `tags`, `status: complete`. Body sections required: `## Patterns recognized`, `## Decisions made`, `## What we did`, `## Shipped`, `## Numbers`, `## Lesson`.

### `/post <topic>`

```bash
spiel content run "<topic>"
```

Topic IS the source. Do NOT do upfront research. The engine injects voice + templates at DRAFTING.

### `/post @file:<path>`

```bash
spiel content run @file:<path>
```

Same as topic mode but reads topic text from the file.

### `/post --session-file <path>`

```bash
spiel content run --session-file <path>
```

Same as empty `/post` but uses a pre-existing session file (skip synthesis).

## Hard rules for the subagent

- **NEVER** auto-pick. Wizard prompts = stop and ask.
- **NEVER** call `engine/engine.py content post` directly — only `spiel content ...`.
- **NEVER** reference `scripts/engine.py` — that path no longer exists.
- **NEVER** use an existing today/yesterday session for empty `/post` — always create a fresh file.
- **NEVER** mention internal labels in public drafts (no `S1`, `TOFU`, `L1`, etc.).
- If blocked, report the exact command/output and current phase. Do not invent menu options.