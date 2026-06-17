---
title: Voice & Quality Gates
type: concept
tags: [engine, spec, voice, quality]
created: 2026-06-11
updated: 2026-06-11
supersedes: [concepts/standalone-quality-test.md, concepts/copywriting-guidelines.md, concepts/content-types.md, concepts/viral-tweet-anatomy.md]
confidence: high
status: living — engine-canonical
sources: [content/sessions/2026-06-06-corpus-analysis.md, content/sessions/2026-06-07-content-system-build.md]
---

# Voice & Quality Gates

How a post reads (voice), what shape it takes (types), and what rules it must pass (gates).

**Engine priority tier:** 4 (Output formatting & gating). Lowest priority. Overridden by all higher tiers on conflict.

---

## Public Positioning

**Category:** Session-as-Content Infrastructure (Build-to-Public Pipeline)

> You should never "go create content." Your work should already contain it.

**One line:** The Spiel Engine turns a founder's actual build sessions into publishable content, so they don't need to stop working to create posts.

---

## Voice (9 Markers) — LLM Guidance Only

> **These are NOT mechanically enforced by gates.py.**
> `rules.yaml` defines the *objective* gates (char count, em-dashes, banned openers, etc.).
> These 9 markers are *artistic guidance* for the LLM during drafting.
> Apply them naturally based on the post's archetype, platform, and the voice-corpus example closest to your draft.
> Vary your openings — not every post needs to start with "I/We".

Read 2-3 examples from [[voice-corpus]] matching the archetype you're drafting, BEFORE drafting. Quote the opening line of one example in your head before you write the hook.

1. **Lowercase "i" in bodies** — "i built this" not "I built this". Capital "I" reads formal. Lowercase "i" is the voice signature. On X, paragraphs can start lowercase (X auto-capitalizes). On LinkedIn, sentences start capital but "i" stays lowercase.

2. **→ arrow** as aha pivot — "→ That's the whole difference." / "→ The new reality."

3. **`absolutely` intensifier** — Optional. 1x max. Do not overuse.

4. **Self-deprecation** — "I made all kinds of mistakes...", "I built this for myself first" — adds warmth.

5. **`Note:` closing** — Strongly preferred but not mandatory. A meta-thought, not a CTA. Vary the closer based on the post's tone.

6. **Casual close** — "i be happy to answer questions if you have any 🤝" OR a question CTA. Avoid using the same close twice in a row.

7. **Rhythm from spacing** — single line breaks between nearly EVERY sentence. Double breaks between major sections. The spacing IS the rhythm.

8. **Broken grammar is a feature** — "All of us has one." "The experiment absolutely worth it." Not "All of us have one." Broken grammar says "this is me, not a press release."

9. **Numbers lean dramatic** — exaggerate for gravity. "Browser bookmarks from 2015" (not 2022). "8 years of bookmarks" (not 3). Specificity that feels real, not a stat.

**The rhythm rule:** Nearly every sentence gets its own line. A thought is 1-3 short lines. A new thought = new paragraph (double break). The → lands the aha.

**Banned:**
- Em dashes — use →, colons, or commas instead
- "excited to share", "Hey friends", "I'm thrilled"
- Engagement bait ("Like if you agree")
- Corporate buzzwords (utilize, leverage, optimize, facilitate)
- Hash flag blocks
- Word 3+ times per post
- LinkedIn listicle formats (Archetypes A, B) — use story, perception-shift, or metaphor instead

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

## Content Types

A *content type* is a structural pattern for a post. Different platforms favor different types. The type is chosen by the *decision tree* — run when `/post` reads a session log.

### Cross-Platform Types (3)

- **Story:** A specific moment with dialogue, stakes, and a lesson. Lesson is the last line, not the first.
- **Take:** A contrarian opinion, argued. Reader should feel friction before they agree.
- **Question:** A genuine question framed with enough context to be answerable. Goal is comments, not impressions.

### X-Only Types (14)

| Type | Structure | When |
|------|-----------|------|
| Ship | Verb + what shipped | Feature launch |
| Stack-brag | Tools + price (sparingly, see AP-14) | Capability flex |
| Dev-log | Fact from the build | Concrete insight |
| Decision | Chose X over Y + tradeoff | Trade-off reveal |
| Lesson | Thing learned, abstracted | Teaching |
| Vision | Future-tense direction | Direction setting |
| Numbers | Specific anchored number | Hard data |
| Hook | Single line opening a thread | Thread starter |
| **Ship-log** | Day N + what shipped | BiP build log, daily/weekly |
| **Product** | "We just shipped X" + why it took N months | Launch / changelog |
| **Milestone** | Specific number + what it means | 1k users, $X MRR, N customers |
| **Feature** | "Added Y" + the one metric that moved | Small change with big impact |
| **Behind** | "What's in my stack" | Tool/process reveal |
| **Case-study** | "Client X went from Y to Z" | Before/after proof |

### LinkedIn-Only Types (6 active)

| Type | Length | When |
|------|--------|------|
| Story | 1300-2500 chars | Confessional opener, specific moment, lesson |
| Perception-shift | 1300-2500 chars | Break an old belief, install new one |
| Single-metaphor | 1500-2500 chars | One load-bearing image carries the post |
| Opening-statement / system | 1500-3000 chars | Show the car (problem + whole system) before the motor |
| Casual-update / day-in-the-life | 600-1200 chars | What + why, soft engagement |
| **Case-study** | 1500-3000 chars | Client result with permission, before/after |

**LinkedIn format priority:**
1. Story — confessional opener, specific moment, lesson
2. Perception-shift — break an old belief, install new one
3. Single-metaphor — one load-bearing image
4. Case-study — client result with permission
5. Opening-statement — framework explained end-to-end
6. Casual update — default fallback

### Blog-Only Types (5)

| Type | Word Count | When |
|------|-----------|------|
| Pillar (system) | 1500-2500 | System explained end-to-end |
| Pillar (story) | 1500-2500 | Turning point, correction, meaningful failure |
| Pillar (teardown) | 1500-2500 | Real artifact analyzed |
| **Product launch** | 1500-2500 | Changelog as content, v2 / beta |
| **Behind-the-build** | 1500-2500 | Stack, system, process deep-dive |

### The Type Decision Tree

When `/post` is invoked, the tree runs in this order:

1. **System, turning point, story, correction, or teaching?** → pillar blog + 3 LinkedIn + 5-10 X
2. **Specific moment worth telling as story?** → story-mode LI + story X thread/single
3. **Contrarian or non-obvious take?** → argument-mode LI + take X post
4. **Genuine question for audience?** → ask-mode LI + question X post
5. **Something shipped?** → ship X post + (optional) dev-log X post
6. **Specific lesson?** → lesson X post
7. **Number worth highlighting?** → numbers X post
8. **None of the above?** → hook X post or skip

The tree always ends with at least one X post (or a skip). Pillar/LinkedIn only fire when the work earns them.

> **Execution order:** This tree runs AFTER Q1-Q4 in [[session-as-content]] §Pipeline Execution Order. The routing result from [[funnel-and-matrix]] is an input to the tree.

---

## The Compiler Sequence

The Content Engine Compiler runs between STRATEGY_LOAD and DRAFTING (state `ICP_WORLD_BUILD`). It inverts the default orientation:

> **ICP world is the subject. Session is evidence.**

### The 8 Steps

1. **LOAD ICP WORLD** — Reconstruct the ICP's mental world (beliefs, frustrations, identity tension, confusion state, language style) independently of the session.
2. **SIMULATE ICP REALITY** — Imagine the ICP living their problem space TODAY, not reading about your session.
3. **LOAD SESSION AS PURE EVIDENCE** — Session is not the subject or story. It is only evidence that something in the ICP world is true or false.
4. **MAP SESSION → ICP WORLD** — What ICP belief does this contradict? What frustration does it expose? What mental model breaks?
5. **EXTRACT 6 MEANINGS** — Generate one sentence per axis: Systemic, Behavioral, Philosophical, Contrarian, Leverage, HUMAN (ψ).
6. **SELECT ONE MEANING** — Choose the axis with the most tension for the ICP, with rationale.
7. **EXTRACT SINGLE CORE INSIGHT** — One sentence describing an ICP world shift, not a system mechanic.
8. **GENERATE CONTENT** — Write for ICP audience only. Use selected meaning axis for tone + framing. Must feel like "this is about my world."

### Output Contract

Written to `.content-brief.json` by the LLM after running Steps 1-8:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `core_insight` | string | yes | One sentence about ICP world shift (Step 7 output) |
| `meanings` | object | yes | All 6 meaning axes from Step 5: systemic, behavioral, philosophical, contrarian, leverage, human |
| `selected_meaning.axis` | string | yes | Which axis was chosen (Step 6) — one of the 6 |
| `selected_meaning.rationale` | string | yes | Why this axis carries the most tension |

**IF** any is missing → DRAFTING is blocked.

### Hard Constraints (Content Body)

Every post produced by the Compiler must pass these:

❌ **Banned mentions:** session structure, schema fields, pipeline, engine, reader_failure_mode, belief/consequence/mapping as labels, system design, build logs, engineering implementation.
❌ **Banned phrases:** "we added", "we changed the system", "we updated the schema", "in this session".
✔ **Required:** ICP world insights, human-level narrative, lived experience framing.

### Quality Test

| Check | Fail If |
|-------|---------|
| No system talk | Reader detects system internals |
| Not engineering notes | Content sounds like a README |
| No session reference | Session is mentioned directly |
| ICP present | ICP feels absent or generic |
| Insight about their world | Insight is about your tool instead of their problem |

### Reader Failure Mode (Upstream Evidence)

The `reader_failure_mode` field in the session log frontmatter feeds Step 4 of the Compiler. It is not the drafting contract — `core_insight` is. The mapping is:

```
reader_failure_mode.belief       → Step 4: "What ICP belief does this contradict?"
reader_failure_mode.consequence  → Step 4: "What ICP frustration does this expose?"
reader_failure_mode.mapping      → Step 4: "What mental model breaks?"
```

---

## Quality Gates

Gate execution order: 4-check standalone (LLM) → 10-gate extended (LLM) → mechanical gates (`gates.py --all`). The mechanical gates read all rules from `rules.yaml` — edit that file to tune behavior. The 9 voice markers are LLM guidance only, not mechanically enforced.

### The Standalone Test (4-Check Baseline)

Would a stranger walk away with one idea from a single read?

1. **5-second test.** A reader skimming the feed can extract 1 idea in 5 seconds.
2. **No-prior-episode test.** The tweet does not require reading earlier posts.
3. **Value-without-me test.** Replacing "I" with a stranger's name still works.
4. **Explain-to-a-friend test.** You could re-tell the tweet in a bar without "you had to be there."

If yes, ship. If no, fix the opener or scrap the post.

### The 10-Gate Extended Checks (Copywriting — LLM-Judged)

Every post must pass ALL 10 before entering queue. These are LLM-judged (not in gates.py):

1. **ICP gate** — a stranger reading this knows in 5 seconds if it is for them
2. **5 questions gate** — who, what problem, why now, what they get, what they do (all answered)
3. **Hook formula gate** — line 1-2 is a hook, not a preamble; line 3 is a promise or setup
4. **No-repetition gate** — no noun 3+ times, no engagement ask repeated within a week
5. **Sentence cap gate** — every sentence capitalized (LinkedIn only; X auto-capitalizes), no paragraph over 2 lines
6. **Mechanical gates passed** — gates.py --all returns pass (checks from rules.yaml)
7. **One-sentence-one-reader gate** — a 15-word sentence that names the reader and the outcome
8. **Source pillar named** in frontmatter (if applicable)
9. **Sensitivity check passed** — no code internals, no internal labels, no credentials
10. **No "$5 stack" closing reflex** — the cost pitch is a 1-in-5 motif, not a closer

### Mechanical Gates (gates.py — rules from rules.yaml)

Enforced by `scripts/gates.py --all`. All rule parameters (safe openers, banned openers, audience triggers, lesson triggers, known names, common words, generic statements, architecture leaks, engagement bank, character limits) are in `rules.yaml`. Edit that file to tune behavior, not this script.

| Gate | Check | Passes When Body... |
|------|-------|---------------------|
| char_count | Surface character limit | Within limit per platform (from rules.yaml) |
| hook_check | Not a preamble opener | Opens with tension (not in banned_openers from rules.yaml) |
| em_dash | No em-dashes | Uses 0 em-dashes |
| word_repeat | No noun repeated 3+ | No significant word ≥3 times (common words from rules.yaml excluded) |
| architecture_leak | No internal labels | Contains no S1..S10, TOFU/MOFU/BOFU, L1..L4, etc. |
| audience_named | Names the reader | Contains an audience trigger from rules.yaml |
| lesson_surfaced | Surfaces a lesson | Contains a lesson trigger from rules.yaml |
| generic_statement | No platitudes | Contains no generic statements from rules.yaml |
| project_as_subject | Opens safely | First word is in safe_openers from rules.yaml (includes reader-first, question, negative, operator — not just "I/We") |
| closing | Has a closing | Last 200 chars have an engagement ask, Note:, question, or emoji |
| frontmatter | Required fields | Has title, created, tags |
| dollar_in_note | No dollar in closer | Note: section has no dollar amount |
| strategy_void | Strategy fields | Has pillar or pattern in frontmatter |
| icp_present | ICP in frontmatter | Has icp field |
| grounded_reference | Context for names | Named person from known_names list has grounding |

### Architecture Leak Gate

Before any draft enters queue, scan for internal architecture leaking into public-facing language:

- **S1–S10 archetype labels** — public content never references session numbers
- **TOFU/MOFU/BOFU** — use Awareness/Consideration/Conversion instead
- **L1–L4 problem layers** — use "surface problem" / "deep problem" if needed
- **Funnel percentages** — say "most" or "some" instead of "40%"
- **Pipeline diagram chains** — never expose procedural flow
- **Gate/check mechanics** — "the engine runs 4 questions" is banned. Say "i ask 3 questions"
- **Compiler internals** — "core_insight", "selected_meaning", "ICF_WORLD_BUILD", "reader_failure_mode" as labels are banned
- **System-change framing** — "we added", "we changed the system", "we updated the schema", "in this session" are banned

**Penalty:** Any draft that triggers the Architecture Leak gate more than once gets killed, not revised.

### The 3-Pass Critique Rule for Pillars

Pillars (blog posts >1000 words) get 3 passes before they ship:

**Pass 1 — Cut.** Delete everything that is not the core insight. History, setup, motivation, and context must be <30% of body.

**Pass 2 — Rhythm.** Read the pillar aloud. Every paragraph that sounds like a document, rewrite. Every sentence longer than 25 words, break.

**Pass 3 — Payoff.** The last paragraph is the one the reader remembers. If it's a summary, delete it and end on a thought.

### Sensitivity Boundary

**Post freely:** What shipped, built, decided, or fixed; systems/workflows (high-level); numbers (time, cost, impact); failures, trade-offs, reversals; the content engine itself (the unique insight); client results (with permission, anonymized).

**Never post:** Internal code, schema, infra topology; API keys, env vars, credentials; client proprietary information; raw/ private identity files; anything that requires 3 posts of backstory.

### Engagement Tracking (Mandatory)

After every published post, record in frontmatter within 24 hours:

```yaml
engagement:
  reactions: N
  comments: N
  reposts: N
  impressions: N
```

This feeds the content performance loop. Without data, the system cannot identify winning patterns.

---

## Viral Post Patterns (Reference, Not Enforced)

12 structural patterns from the viral-tweet-anatomy analysis. Reference only — not enforced. The full list with examples is archived at `_archive/concepts/viral-tweet-anatomy.md`.

Types: counter-intuitive, specific number, cheat code, confessional, prediction, delete-reframe, mythology, specific claim, transformation arc, list promise, negative contrarian, hard data.

---

## See Also

- [[voice-corpus]] — canonical examples to read before drafting
- [[funnel-and-matrix]] — the funnel that tells you which type to write
- [[icp-offer]] — who you're writing for
- [[session-as-content]] — the methodology that produces the sessions
- `templates/x-post.md` — the X post template
- `templates/linkedin-post.md` — the LinkedIn post template
- `templates/blog-post.md` — the blog post template
- `scripts/gates.py` — the 15-check unified mechanical gate
