# Session as Content — methodology

## The rule

**ICP world is the subject. Session is evidence.**

The session log (or topic text) is raw material, not content. The Strategist must translate the session into ICP language before writing the brief. The translation is a 1:1 substitution, not a paraphrase.

The session can mention concrete details from the work (numbers, time anchors, specific actions) — but those details serve the ICP's narrative, not the system's.

## Why this rule exists

Without the translation, the post describes the literal session: "I stress-tested my distribution system. 11 bugs. 8 tools." The reader doesn't care about the builder's system. They care about their own situation.

With the translation, the post describes the ICP's situation: "Tuesday morning, 9:47am. You check the analytics. Traffic is flat. You said to yourself: 'Maybe my hooks are wrong.'" The reader goes: "DAMN! This happened to me yesterday."

The translation is the bridge. The simulator exists to do this translation deterministically.

## The 4 failure modes that cause build-log content

### 1. "I just describe the session"

The post literally narrates what the builder did. "I ran an audit. I found 10 issues. I fixed the wizard." This is build-log. The reader doesn't know what an audit is in this context, and doesn't care.

**Fix:** Translate every action into an ICP-world equivalent. "I ran an audit" → "I checked the system for hidden failure points." The post becomes about the hidden failure points, not the audit.

### 2. "I use the system's vocabulary"

The post uses the system's terms as if they were the reader's. "The integration surfaces are where it breaks." "The main engine held." "Non-atomic writes recur." The reader thinks in different vocabulary.

**Fix:** Lift the ICP's vocabulary from `strategy/audience.md` "ICP-language bank". The reader thinks in "the things I built", "the places I post", "the parts I forgot to check" — not in "integration surfaces" and "non-atomic writes."

### 3. "I fabricate a scene the ICP didn't live"

The post invents a parallel ICP scene: "Thursday 11:14pm. Post #10. 2 visitors, one was me." The ICP reads it and thinks: "this didn't happen to me" — because it didn't. The source session was a meta/system work session (a refactor, an audit, an internal design). The Strategist invented concrete details to fill a "vivid scene" template.

**Fix:** Render the Pain field as a **recognizable pattern**, not a fabricated scene. Lift the CONCEPT from the source (the abstract structure) and translate it to the ICP's parallel concept using ICP vocabulary. The reader recognizes the PATTERN, not the scene. If the source is a meta/system work session, lift only the concept — fabrication is the failure mode.

### 4. "I make the session the subject"

The post tells the story of the session. "Last week I noticed something. I ran a test. Here's what I found." The reader is reading a journal entry, not a post about their own world.

**Fix:** Use the session as EVIDENCE for an ICP-world claim. The session is the footnote, not the headline. The headline is the ICP's situation.

## The translation table — worked example

Session evidence (DO NOT USE) → ICP language (USE THIS)

| Session evidence | ICP language |
|---|---|
| "10 critical issues across 4 subsystems" | "Most builders hit the same wall in 3 places" |
| "Non-atomic writes recur across wizard, install, and publisher" | "Every system breaks at the seams, not the core" |
| "Vault resolution ignores $VAULT_DIR" | "Your distribution system has hidden seams" |
| "Codex hook silent exit when spiel not on PATH" | "Your automation has silent failure modes" |
| "Move machine-state JSONs to system/state/" | "Move the runtime state to where users can't touch it" |
| "11 bugs. 8 tools. 5 environments. All silent." | "The bugs you don't see are the ones that cost you" |
| "Engagement collapsed" | "The numbers stopped moving" |
| "Posted 3 things this week, none moved the needle" | "Tuesday morning, 9:47am. You open the analytics. Traffic is flat." |

## The Pain field — recognizable pattern, not fabricated scene

When the simulator renders the Pain field, the goal is **pattern recognition**, not scene narration. The reader should think "yes, this is what I do" — not "yes, this happened to me at 11:14pm Thursday" — because the parallel is conceptual, not literal.

**The pattern, not the scene.** A good Pain is a 2-4 sentence statement of the ICP's recognizable pattern. It does NOT need time anchors, specific actions, internal monologues, or "wrong attributions" the ICP did not actually experience.

### When to lift a concrete detail (and when not to)

- **Lift a concrete detail** if the source has one the ICP would actually experience — e.g. shipping a real feature, talking to a real customer, hitting a real deadline, getting a real customer email. The detail is real and the ICP recognizes it.
- **Lift only the concept** if the source is a meta/system work session — a refactor, an audit, an internal design decision, a tooling change. The ICP doesn't sit at home doing reliability audits on content engines. They do something parallel, not the same thing. The pattern is what resonates, not the fictional scene.

### The wrong-attribution bridge (still allowed, only when real)

The "wrong attribution" pattern (ICP thinks the problem is X, the Point corrects it to Y) is still useful — but only when the source actually contains a real ICP-world attribution. If the source is a meta session, don't invent the wrong attribution. State the pattern plainly, and let the Point do the reframing.

## The Meaning field — first-person ICP voice

The Meaning field is NOT a summary of the post. It is the takeaway the ICP would internalize, in their own words, first-person.

❌ "Distribution is a placement problem." (third-person, abstract)

✅ "I was not failing at writing. I was failing at placing." (first-person, concrete, the aha)

The Meaning is the close of the post. It is the sentence the reader remembers 24 hours later.

## The Reader field — identity-rich

The Reader field is NOT a category ("founders and indie builders"). It is a specific ICP, named with their situation and their identity tension.

❌ "Founders, indie builders, and marketing operators." (category)

✅ "A technical founder who shipped 3 things last quarter but can't tell which one moved the needle. They open the analytics before standup every Tuesday." (specific, with identity)

The Reader is the post's address. The reader should see themselves in the first 2 lines of the post.

## The Belief → Point contract

The Belief field is the OLD mental model. The Point field is the NEW mental model that replaces it. They MUST contradict.

❌ Belief: "I should write better content." Point: "I should write better content, more often." (no contradiction)

✅ Belief: "If I write better content, attention will come." Point: "Distribution is a placement problem, not a content problem. Same post, different placement, the numbers change." (clear contradiction)

The Pain is the cost of the Belief. The Proof backs the Point. The Meaning is the close.

## The 6-field brief — a worked example (the source here is a real shipping session)

This example is for a source session where the builder actually shipped a feature and got real numbers back. The Pain lifts a real concrete detail the ICP would recognize.

```yaml
reader: |
  A technical founder who shipped 3 things last quarter but can't tell
  which one moved the needle. They open the analytics before standup
  every Tuesday.

pain: |
  Tuesday morning, 9:47am. You check the analytics. Traffic is flat
  again. Three posts went out last week, all 200 words, all hooks
  tested. None of them moved the needle. You said to yourself: "Maybe
  my hooks are wrong." But the open rate was fine. People just didn't
  show up. You were failing at placing, not at writing. You didn't
  know it yet.

belief: |
  If I write better content, attention will come.

point: |
  Distribution is a placement problem, not a content problem. Same post,
  different placement, the numbers change.

proof:
  - "6-7 min average session duration when content was placed inside active attention cycles"
  - "~300 visitors from a single post, organic social, 6m 58s avg duration"
  - "Real-time iteration on placement mechanics, not content volume"

meaning: |
  I was not failing at writing. I was failing at placing.
```

## The 6-field brief — when the source is a meta/system session

When the source is a refactor, an audit, an internal design decision (not something the ICP would experience as a literal scene), the Pain lifts only the **concept** and translates it to the ICP's parallel concept. No fabricated time anchors, no invented actions, no fabricated internal monologues.

```yaml
pain: |
  You publish. The post reads well. The metrics stay flat. You refine
  the visible parts. The bottleneck moves. You never quite catch it.
```

The reader recognizes the pattern. They do not need to have lived a specific scene to recognize it.

This brief is the post, in seed form. The Writer renders it for each platform.
