---
key: compiler
title: Content Engine Compiler (Session mode + Topic mode)
audience: LLM
status: canonical
---

# Content Engine Compiler

The Compiler turns source material into a `core_insight` + 6 `meanings` + a `selected_meaning` — the three things every draft needs before the LLM can write it.

There are two modes. The brief's `source.kind` tells you which one to run. **Do not run both.** Run the one that matches the source.

**The runtime identity and LLM-facing hard constraints (always-banned rules) live in `system/prompts/identity.md`. This file is the compiler sequence and the mode-specific guidance only.**

## Mode selector

```
brief.source.kind == "session"  →  SESSION MODE (8 steps, this file § A)
brief.source.kind == "topic"    →  TOPIC MODE (6 questions, this file § B)
```

If `source.kind` is missing, default to session mode. If session mode but no session file is present, the engine should have refused before reaching you — stop and report.

---

## § A — Session mode (8 steps)

Use this when the brief's `source.kind` is `session`. The session log is evidence — the ICP's world is the subject.

### STEP 1: Load ICP world (do not use session yet)

Fully reconstruct the ICP as a living mental world:
- beliefs / frustrations / constraints / identity tension
- current confusion state / language style
- internal monologue questions

This ICP world must exist independently of the session. **See `strategy/icp.md` for the ICP profile (rebuilt at the start of every run).**

### STEP 2: Simulate ICP reality

Imagine the ICP is actively experiencing their world TODAY. They are not reading about your session. They are living their problem space.

### STEP 3: Load session as pure evidence (not topic)

Session is NOT the subject. Session is ONLY evidence that something in the ICP world is true or false.

### STEP 4: Map session → ICP world (not ICP → session)

Ask:
- What ICP belief does this contradict?
- What ICP frustration does it expose?
- What ICP mental model breaks?

For session logs that include `reader_failure_mode` (see `strategy/methodology.md §Session Log Schema`):
- `.belief` → what the ICP currently believes that this session contradicts
- `.consequence` → what painful thing follows from that belief (the frustration this exposes)
- `.mapping` → what new mental model this session supports

### STEP 5: Extract 6 meanings (one sentence per axis)

For each of these 6 axes, write one sentence describing what this session reveals:

| Axis | Question |
|---|---|
| systemic | What system or invariant does this session reveal about how content/publishing/expertise works? |
| behavioral | What builders do and why — the pattern of behavior this session exposes. |
| philosophical | The deeper truth about knowledge, information, or creation. What universal principle does this touch? |
| contrarian | The industry assumption this session inverts. |
| leverage | The highest-leverage action this session points to. |
| human | The psychological/emotional layer — human need, fear, or identity tension. |

### STEP 6: Select one meaning

Choose which axis carries the most tension for the ICP. Write the axis name and a one-sentence rationale.

### STEP 7: Extract single core insight

One sentence only. Must describe an **ICP world shift**, not system mechanics. This is the lens for the post.

### STEP 8: Generate content

Write content for the ICP audience only. Use the selected meaning axis to choose tone + framing. Use `core_insight` as the lens.

### Hard constraints (session mode)

**Always-banned rules (em-dash, engagement bait, internal labels, etc.) live in `system/prompts/identity.md §hard-constraints`. Mirror them in your draft. The additional mode-specific rules below are session-mode only.**

Do not mention:
- session structure, schema fields, pipeline, engine (the LLM-facing labels for these are banned)
- `reader_failure_mode`, `belief/consequence/mapping` as labels in the body
- build logs or engineering implementation
- "we added", "we changed the system", "in this session"
- system internals as labels (S1–S10, TOFU/MOFU/BOFU, L1–L4, ICP as acronym, "the engine")

Required:
- ICP world insights (the ICP's lived experience is the subject)
- Human-level narrative (not engineering notes)
- Lived experience framing

Voice markers (apply to draft body, not the brief):
- Standard capitalization for first-person pronouns ("I built" not "i built").
- Vary your openers — don't always start with "I". Use the reader-problem-first opener at least as often as the confessional opener.
- `Note:` closer — a meta-thought, not a CTA. Strongly preferred.
- The `->` arrow is an aha pivot. Use sparingly.
- `absolutely` as intensifier — 1x max per post.
- Numbers lean dramatic. Specific numbers > round numbers.

---

## § B — Topic mode (6 questions)

Use this when the brief's `source.kind` is `topic`. The topic IS the subject — announce, explain, or defend it.

### Q1: Post type

What kind of post is this? Pick one:

| Type | Definition |
|---|---|
| announcement | we shipped / launched / released X |
| explainer | teach the reader how/why something works |
| opinion | take a side on a debate |
| teardown | dissect a real artifact in public |
| case-study | show a result with permission |
| how-to | step-by-step instructions |

### Q2: Reader outcome

In one sentence, what does the reader walk away knowing? This is the takeaway, not the agenda. Concrete, not abstract.

### Q3: 6 angles (one sentence per axis, reframed for the topic)

| Axis | Reframed for the topic |
|---|---|
| systemic | What system or invariant does this topic reveal? |
| behavioral | What does the reader's behavior or approach change to after reading? |
| philosophical | What principle about building, knowing, or creating does this topic touch? |
| contrarian | What industry assumption does this topic contradict? |
| leverage | What is the highest-leverage action the reader can take after reading? |
| human | What identity shift or emotional beat does this topic carry? |

### Q4: Pick one axis

Default by type:
- announcements: usually `leverage` (what it unlocks) or `contrarian` (what's surprising)
- explainers: usually `systemic` or `behavioral`
- opinions: usually `contrarian` or `philosophical`

### Q5: Core insight (the one sentence the post must deliver)

- For announcements: the value prop. What shipped, why it matters, what the reader gets.
- For explainers: the mechanism. The one thing the reader "gets" that they didn't before.
- For opinions: the take. The position, stated in one sentence.

This is NOT an "ICP world shift" — it's the post's payload.

### Q6: Hook + next-step

- First 2 lines: name the topic. Reader knows in 5 sec what's new.
- Last 1-2 lines: a verb-driven next step (clone, install, try, read, reply, sign up, comment).

### Hard constraints (topic mode)

**Always-banned rules live in `system/prompts/identity.md §hard-constraints`. The mode-specific rules below are topic-mode only.**

Encouraged (topic mode is the place to *show*, not philosophize):
- "we shipped", "we added", "we released", "now available"
- "just shipped", "just released", "this week"
- Naming partners/credits ("thanks to @buffer", "built with Y")
- Verb-driven CTAs ("clone it", "try the templates", "reply with")
- Specific numbers ("3 channels", "3000 calls/month", "v2.1")
- Naming what shipped: feature names, file paths, version numbers
- Stop-the-scroll hooks ("Just shipped 3 things.", "One API call. Three platforms.")
- Confident, professional register — like a product launch, not a journal entry
- Standard capitalization ("I" not "i") — session-mode voice does NOT apply here

Banned in topic mode (in addition to the always-banned list in identity.md):
- "hate marketing" / "hate becoming a content creator" angle (this is session-mode framing for builders deep in the funnel)
- "off-ramps beat raw power" reflex (show the features, don't philosophize)
- Self-deprecation openers (topic mode earns credibility by being clear, not humble)
- Ends on a question (use a verb-driven statement instead)

---

## Topic mode auto-fill behavior (engine behavior note)

When `brief.source.kind == "topic"`, the engine **does not** run the 6-question
compiler sequence above. Instead, `engine.py::_auto_fill_topic_brief` runs at the
end of SESSION_CAPTURE and writes a brief with:

- `core_insight` = first 280 chars of the topic text (truncated silently)
- `meanings` = all 6 axes set to empty strings
- `selected_meaning.axis` = "leverage" (default; topic_kind override table in
  `rules.yaml §compiler.mode_routing.topic.archetype_funnel_override` is NOT
  consulted by the auto-fill — the LLM is expected to revise during drafting
  if needed)
- `selected_meaning.rationale` = "topic mode — topic IS the core insight; default axis selected."
- `_topic_mode` = true
- `template_selection` = cleared (Fix M1)

The rationale: in topic mode the user has already named the topic and chosen
to ship a quick post about it. Forcing a 6-question compiler round-trip would
add 30-90 seconds of latency with no creative value. The LLM still runs the
DRAFTING handoff (LLM handoff #2) where it applies the 8-step thinking implicitly
via the voice corpus and template recommendations.

If you want the LLM to actually run the 6 questions, set `brief._topic_mode`
to false in the brief before calling `content run` again.

---

## Output contract (both modes)

Write to `.content-brief.json`:
1. `core_insight` (string) — one sentence from Step 7 (session) or Q5 (topic)
2. `meanings` (object) — all 6 axes, one sentence per axis
3. `selected_meaning` (object) — `{axis, rationale}`

Then call `spiel content compile-write` with the corresponding CLI flags. The engine will validate the output and advance to SELECT.
