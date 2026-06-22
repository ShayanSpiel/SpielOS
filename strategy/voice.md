---
title: Voice
type: concept
tags: [engine, spec, voice]
created: 2026-06-11
updated: 2026-06-21
supersedes: [concepts/shayanspiel-style.md]
confidence: high
status: living — engine-canonical
sources: [content/sessions/2026-06-06-corpus-analysis.md, content/sessions/2026-06-07-content-system-build.md]
aliases: [voice-and-gates]
---

# Voice

How a post reads (voice), what shape it takes (types — see `templates/types.md`), and what rules it must pass (gates — see `system/gates.md`).

**Engine priority tier:** 4 (Output formatting & gating). Lowest priority. Overridden by all higher tiers on conflict.

**The mechanical form of every rule here lives in `system/rules.yaml`. The LLM-facing hard constraints live in `system/prompts/identity.md §hard-constraints`. This file is the voice layer only — the human-readable spec.**

---

## Voice — Mode-Aware

The voice is **not uniform across modes**. Session mode (build-to-public) and topic mode (announce / explain / opinion) read differently and aim at different readers.

- **Session mode** = a peer builder is reading. Casual, lowercase, self-deprecating, voice-corpus examples 1, 2, 5, 6, 8 are the closest match.
- **Topic mode** = a stranger is scrolling. Professional, confident, "stop the scroll" energy, voice-corpus example 3 (counter-intuitive) and the velocity/numbers pattern in 5 are the closest match. Treat it like a product launch, not a journal entry.

### Session Mode Markers (LLM Guidance Only)

> The LLM applies these naturally based on the post's archetype and the closest voice-corpus example. They are not mechanically enforced.

1. **Standard capitalization (all modes)** — "I built this" not "i built this". Capital "I" is the default in both session and topic mode.
2. **→ arrow** as aha pivot — "→ That's the whole difference." / "→ The new reality."
3. **`absolutely` intensifier** — Optional. 1x max. Do not overuse.
4. **Self-deprecation** — "I made all kinds of mistakes...", "I built this for myself first" — adds warmth. Session mode only.
5. **`Note:` closing** — Strongly preferred but not mandatory. A meta-thought, not a CTA.
6. **Casual close** — "I'm happy to answer questions if you have any 🤝" OR a question CTA. Avoid using the same close twice in a row.
7. **Rhythm from spacing** — single line breaks between nearly EVERY sentence. The spacing IS the rhythm.
8. **Broken grammar is a feature** — "All of us has one." "The experiment absolutely worth it." Not "All of us have one." Broken grammar says "this is me, not a press release."
9. **Numbers lean dramatic** — exaggerate for gravity. "Browser bookmarks from 2015" (not 2022).

### Topic Mode Markers (LLM Guidance Only)

> The LLM applies these naturally. They are not mechanically enforced. Topic mode reads like a product launch.

1. **Standard capitalization** — Sentence starts with capital. All first-person pronouns use capital "I".
2. **Stop-the-scroll energy** — first 2 lines are a punch. The reader has 2 seconds before they swipe. Either name the news ("Just shipped 3 things.") or name the value ("One API call. Three platforms.") or name the contrarian ("Most tools are doing this wrong."). No preamble.
3. **Specific, named, energetic** — name the partners, name the numbers, name the file paths. "Built on @buffer. 3 channels. 3,000 calls/month. Free." reads as a launch, not a confession.
4. **→ arrow for aha pivots** — same as session mode.
5. **Confident, not self-deprecating** — "Here's what shipped." not "I almost gave up on..." Self-deprecation is for session mode only. In topic mode, the reader doesn't know you yet. Earn credibility by being clear, not by being humble.
6. **Verb-driven closer** — "Clone it." / "Try the templates." / "Reply with what you'd ship." Closer is the verb, not a question.
7. **No "hate marketing" angle** — that is the *session-mode* framing for builders deep in the funnel. In topic mode, the reader is a stranger. The "hate marketing" framing reads as insecurity to a stranger. Frame the reader as a builder who *has work worth shipping*, not as a builder who is *afraid of marketing*.
8. **No "off-ramps beat raw power"** for announcements — that is session-mode wisdom. Topic mode is the place to *show* the off-ramps (the features), not *frame everything as off-ramps*. The reader wants to know what they get, not what they're missing.
9. **Ends on a thought, not a question** for blog/LinkedIn — "Build the work. Ship the post. Stay a builder." reads stronger than "What would you ship?". For X, the question CTA is fine.

### Always Banned (both modes)

For the LLM-facing narrative form of these rules, see `system/prompts/identity.md §hard-constraints`. The mechanical regex form is in `system/rules.yaml §architecture_leaks`.

- Em dashes — use →, colons, or commas instead
- "excited to share", "Hey friends", "I'm thrilled", engagement bait
- Corporate buzzwords (utilize, leverage, optimize, facilitate)
- Same noun 3+ times in a post
- Hash flag blocks

### Character Limits (Hard Gates — in `rules.yaml §char_limits`)

Limits are defined in `rules.yaml` and enforced by `gates.py`. Drafting must respect:
- LinkedIn casual ≤1500 chars, polished ≤3000
- X single ≤280 chars
- Blog pillar ≤2500 words

### X Post Rules (from Engagement Data)

1. **Tension first, information second.** Every X post must create tension in the first line.
2. **Take a side.** Neutral posts get 0 engagement. Reader must be able to agree OR disagree.
3. **Include a specific personal data point.** Generic claims get ignored.
4. **CTA must invite both agreement and disagreement.** "Agreed?" > "Let me know what you think."
5. **Vulnerability > authority.** "I'm starting to believe it^" drives more engagement.
6. **The caret (^)** is an X-specific voice marker for vulnerable punchlines. Do not use on LinkedIn.

### Link Strategy

- **X posts:** No link in body. "Link in reply" at end.
- **LinkedIn:** Link in first comment. Post delivers full value without the link.
- **Blog promo post:** One dedicated tweet. Link in reply.

---

## See Also

- `templates/types.md` — content types per platform (X / LinkedIn / Blog shapes + decision tree)
- `strategy/corpus.md` — 8 canonical examples to read before drafting
- `strategy/funnel.md` — the funnel that tells you which type to write
- `strategy/icp.md` — who you're writing for
- `strategy/methodology.md` — the methodology that produces the sessions
- `system/gates.md` — the 15 hard + 14 soft quality gates
- `system/prompts/identity.md` — runtime identity + LLM-facing hard constraints
- `system/prompts/compiler.md` — the 8-step + 6-question compiler
- `templates/x-post.md`, `templates/linkedin-post.md`, `templates/blog-post.md` — output shapes
