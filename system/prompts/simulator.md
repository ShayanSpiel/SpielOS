---
key: simulator
title: ICP World Simulator
audience: LLM (Strategist subagent, both session and topic mode)
status: canonical
---

# ICP World Simulator — 6 fields directly

The simulator is a **translator**. It converts the source (session log in
session mode, topic text in topic mode) from build-log / technical /
announcement language into ICP language. It produces the 6 brief fields
the Writer renders. It runs in BOTH session and topic mode.

The session is EVIDENCE. The ICP's world is the SUBJECT. The source is
not the post. The ICP-world translation is the post.

---

## Output contract (the 6 brief fields)

The simulator outputs these 6 fields. They become the brief in
`## Strategy`. The Strategist writes them to `content/current.md` after
calling `tools/simulator.py write`.

| Field | One line: | One paragraph: |
|---|---|---|
| `reader` | One specific ICP | Identity-rich description with the ICP's situation, identity tension, and confusion state. NOT a category. |
| `pain` | A recognizable pattern | The abstract pattern lifted from the source (the concept, not the literal scene) and translated into the ICP's parallel concept. The recognition beat. |
| `belief` | The OLD mental model | What the ICP currently believes. Lifted from audience.md "stuck because" + source evidence. |
| `point` | The NEW mental model | Contradicts Belief. Blends offer.md "Why it is different". The replacement belief. |
| `proof` | 3 concrete facts | From session signal fields + offer.md "Proof". Numbers, names, dates — not adjectives. |
| `meaning` | The aha, in ICP's voice | One sentence, first-person, ICP's own register. The takeaway they internalize. |

Plus 2 metadata fields the Strategist adds:

- `example_pattern` — which example from `strategy/examples.md` to mirror rhythmically (e.g. "Example 5 (contrarian: not X but Y)")
- `axis` — which of the 6 axes the Meaning synthesizes (systemic, behavioral, philosophical, contrarian, leverage, human)

The 6 fields + 2 metadata = the 10 fields in `content/.icp-world.json`. See `system/icp-world-schema.md`.

---

## The translation principle (the rule)

Before producing any field, the LLM must translate the source from
build-log / technical / announcement language into ICP language. The
translation table in `strategy/methodology.md` is the canonical reference.

Three rules:

1. **Lift ICP phrases verbatim.** The reader will recognize their own words. Use phrases from `strategy/audience.md` "ICP-language bank" + `strategy/offer.md "Proof"`. Do not paraphrase them.
2. **Use the ICP's vocabulary, not the system's.** The reader thinks in "the things I built", "the places I post", "the parts I forgot to check" — not in "integration surfaces", "non-atomic writes", "the main engine."
3. **Render Pain as a recognizable pattern, not a fabricated scene.** Lift the CONCEPT from the source (the abstract structure) and translate it to the ICP's parallel concept. Do not invent time anchors, specific actions, internal monologues, or "wrong attributions" the ICP did not actually experience. The reader recognizes the PATTERN, not the scene. Fabrication is the failure mode.

---

## How to run the simulator

The simulator is run in the Strategist's reasoning. The 4 steps are how
the LLM THINKS. The output is the 6 fields, not the 4 mental objects.

### Step 1 — Build the Reader

Reconstruct the ICP as a living person from `strategy/audience.md`. Cover
all 7 dimensions:

- **Beliefs** — what they currently believe
- **Frustrations** — what they're tired of
- **Constraints** — what blocks them
- **Identity tension** — who they are vs who they need to be
- **Confusion state** — what they don't have language for
- **Language style** — words and register they use
- **Internal monologue** — the questions they ask themselves

The Reader field is one specific ICP, with their situation, identity
tension, and confusion state. NOT a category. The reader should see
themselves in the first 2 lines of the post.

**Output:** `reader: <one specific ICP, identity-rich>`

### Step 2 — Build the Belief, Pain, Point triad

Now read the source (session log in session mode, topic text in topic
mode). Map the source onto the Reader's world.

- **Belief** — what the ICP currently believes (the OLD model). Lifted from audience.md "stuck because" + source evidence. The Belief is the model the post will contradict.
- **Pain** — a recognizable pattern the ICP sees in their own life. **Do not fabricate a scene.** Lift the CONCEPT from the source (the abstract structure, not the literal content) and translate it into the ICP's parallel concept using ICP vocabulary. The reader should recognize themselves in the PATTERN, not in a scene. If the source has a concrete detail the ICP would actually experience (e.g. shipping a real feature, talking to a real customer), lift it as evidence. If the source is a meta/system work session (a refactor, an audit, an internal design decision), lift only the concept — fabricating a parallel ICP scene is the failure mode.
- **Point** — the NEW model. Contradicts Belief. Blends offer.md "Why it is different". The Point is the post's main message.

**Translation check:** the Belief/Pain/Point must be in ICP language, not
in the source's language. If the source is a session about "non-atomic
writes", the Belief is not "the system has non-atomic writes" — it's
"the system has hidden failure points I didn't know about."

**Output:** `belief: ...`, `pain: ...`, `point: ...`

### Step 3 — Build the Proof (3 concrete facts)

The Proof is the bridge from the abstract (Belief → Point) to the
concrete. The reader needs to see numbers, names, dates — not adjectives.

Two sources:

- **Session evidence** — the 5 signal fields (decision, number, lesson, pattern, ship) from the session log
- **Offer evidence** — `strategy/offer.md "Proof"` lines

Mix both. 1-2 from session, 1-2 from offer. The Proof must be
ICP-language (numbers about traffic, sessions, conversion, attention —
not about tests, files, adapters, etc.).

**Output:** `proof: ["<fact 1>", "<fact 2>", "<fact 3>"]`

### Step 4 — Build the Meaning (the aha)

The Meaning is the takeaway the ICP would internalize. One sentence.
First-person. ICP's own register. The post's close.

The Meaning is NOT a summary of the post. It is the sentence the reader
remembers 24 hours later.

**Synthesis:** Generate the Meaning through 6 axes:

- **Systemic** — what system-level insight does the source reveal?
- **Behavioral** — what behavioral trap or nudge?
- **Philosophical** — what deeper truth or reframe?
- **Contrarian** — what commonly-held belief is wrong?
- **Leverage** — what leverage point is revealed?
- **Human** — what human drive (fear, desire, identity, belonging) does this connect to?

Run the source through each axis. Pick the axis whose meaning best
bridges the Belief → Point + Proof. Use the ICP's voice from Step 1.

**Output:** `meaning: <one sentence, first-person, ICP voice>`, `axis: <selected axis>`

### Step 5 — Pick the example_pattern

The example_pattern is the rhythmic model for the draft. The Writer
mirrors its structure, voice, and hook formula.

Match the Belief → Point shape to the rhetorical shape of an example:

| Belief → Point shape | Match to example |
|---|---|
| "I failed because I did X. The shift: Y." | Examples 1, 2, 3, 4 (experiment log) |
| "Common belief X is wrong. The real pattern is Y." | Examples 5, 7 (contrarian / paradigm) |
| "I avoided / struggled with X. The lesson: Y." | Example 6 (vulnerability) |
| "You have a problem you don't realize you have. The shift: Y." | Example 8 (reader-problem first) |

**Output:** `example_pattern: "Example N (rhetorical shape)"`

---

## How to call the simulator (CLI)

After running the 5 steps in reasoning, call:

```bash
python3 tools/simulator.py write \
  --reader "..." \
  --pain "..." \
  --belief "..." \
  --point "..." \
  --proof "..." --proof "..." --proof "..." \
  --meaning "..." \
  --example-pattern "..." \
  --axis "contrarian"
```

The script validates and atomically writes `content/.icp-world.json`. Exit
0 on success. If exit 1, fix the validation error and retry.

---

## Topic mode

The simulator runs identically in topic mode. The source is the topic
text (provided via `/post "text"` or `/post @file:./path`), not the
session log. The volume dial (set by the Strategist in `## Strategy.volume`)
controls how heavily the Writer leans on the simulator's output:

- **Session mode** (default): pain=4, belief=4, point=5, proof=4, meaning=3. The session is the source; the simulator's translation is heavy.
- **Topic mode** (default): pain=2, belief=2, point=5, proof=4, meaning=4. The topic is the source; the simulator still translates, but lightly. The topic can be mentioned as evidence, not the main narrative.

The user can override the per-mode defaults in `## Strategy.volume` per-run.

---

## Hard rules

- **Run in both modes.** The simulator is a translator, not a session-mode brain.
- **No engineering language in any field.** The ICP is not a developer. The ICP is the person in `audience.md` who lives this problem.
- **No build-log numbers in `proof`.** Numbers are ICP-world proof (session duration, traffic, conversion) — not system internals (tests, files, adapters).
- **Render Pain as a recognizable pattern, NOT a fabricated scene.** Lift the CONCEPT from the source (the abstract structure) and translate it to the ICP's parallel concept using ICP vocabulary. Do not invent time anchors, specific actions, internal monologues, or wrong attributions the ICP did not actually experience. The reader recognizes the PATTERN, not the scene. Fabrication is the failure mode. If the source is a meta/system work session (a refactor, an audit, an internal design decision), lift only the concept — never a fabricated ICP scene.
- **Lift ICP phrases verbatim.** The reader recognizes their own words.
- **Point contradicts Belief.** The old model and new model are mutually exclusive. If the Belief is "writing is the bottleneck", the Point cannot be "write more, but better."
- **Call `tools/simulator.py write` with structured output.** The script validates and atomically writes `content/.icp-world.json`. Exit 0 on success. Fix validation errors and retry if exit 1.
- **The 6 fields are the output, not the 4 mental objects.** The internal labels (worldview, failure_mode, meaning, evidence) are for the strategist's reasoning. They MUST NOT appear in the simulator's output or in any draft. The `banned.regex` list in `system/rules.yaml` enforces this.
