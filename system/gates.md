# Gates — single source of truth

This is the **canonical reference for every gate, rule, threshold, and configuration knob** in the Spiel Engine. If a value affects what gets written, posted, or rejected, it lives here. If it lives here, it is the only place it lives.

A new contributor should be able to read this file in 10 minutes and understand:
1. What the system enforces (hard rules) vs what it merely suggests (soft rules).
2. Where each rule is enforced (which file / function).
3. How to disable a rule (toggles) or change a threshold (parameters).

## Summary

| Bucket | Count | What it does | Where it runs |
|---|---|---|---|
| Hard (mechanical) | 15 | Regex / length / structural checks. Pass/fail is deterministic. | `engine/gates.py` (every function in `ALL_CHECKS`) |
| Soft (LLM-judged) | 14 | Subjective editorial checks the LLM applies at draft time. | `system/prompts/compiler.md` (output contract) + injected at handoff |
| Configuration | 1 set | Thresholds, char limits, cadence, weights. | `system/rules.yaml` → `engine/engine_config.py` |
| Suggestions | 6 docs | Voice, ICP, funnel, archetypes, session method, corpus. LLM reads at handoff. | `strategy/*.md` (injected via `_print_strategy_injection`) |

**Composite score is advisory.** The 14 soft gates (4-check + 10-gate) are not run in code. They appear in this file and in the LLM-facing prompt; they are **not** mechanically scored. The `quality.composite_threshold: 0.85` knob in `rules.yaml` is defined but unused until the soft gates are wired into `gates.py`. Treat it as a reminder, not a gate.

---

## 1. Hard gates (mechanical)

**File:** `engine/gates.py`. Each function signature: `(fm, body, rules) -> (bool, str)`. Pure — no file I/O, no CLI. The orchestrator calls `validate_draft()` (gates.py:277) per draft; the result is written to frontmatter `gates: pass|fail` and `logs/.gates-report.json`.

| # | id | function | checks for | tunable via |
|---|---|---|---|---|
| 1 | `char_count` | `check_char_count` (gates.py:13) | Length fits the surface (X=280 chars / LI=1500-3000 / blog=2500 words / buffer=2200). Threads respect tweet cap. | `rules.yaml §char_limits` |
| 2 | `hook_check` | `check_hook` (gates.py:52) | First line is not a banned opener pattern. | `rules.yaml §banned_openers` |
| 3 | `em_dash` | `check_em_dash` (gates.py:67) | Zero em-dashes in body (use `→`, `:`, or `,`). | (no toggle — always on) |
| 4 | `word_repeat` | `check_word_repeat` (gates.py:74) | No word repeated 3+ (small) / 4+ (medium) / scale (large) times, excluding common words. | `rules.yaml §common_words` + `gate_params.word_repeat_scale_*` |
| 5 | `architecture_leak` | `check_architecture_leak` (gates.py:98) | No internal labels leaked: `S1`–`S10`, `TOFU/MOFU/BOFU`, `L1`–`L4`, `ICP`, `funnel.stage`, etc. | `rules.yaml §architecture_leaks` |
| 6 | `audience_named` | `check_audience_named` (gates.py:110) | Reader is named (you/your/founders/builders/etc.). Strong triggers checked first. | `rules.yaml §audience_triggers` + `gate_params.strong_audience_triggers` |
| 7 | `lesson_surfaced` | `check_lesson_surfaced` (gates.py:130) | At least one lesson marker in body ("I learned", "the takeaway", etc.). | `rules.yaml §lesson_triggers` |
| 8 | `generic_statement` | `check_generic_statement` (gates.py:139) | No platitudes ("content is king", "trust the process", etc.). | `rules.yaml §generic_statements` |
| 9 | `project_as_subject` | `check_project_as_subject` (gates.py:148) | First word is not the project name (must be reader/opinion/question, not "Spiel" or "the engine"). | `rules.yaml §safe_openers` (built-in strong_safe list) |
| 10 | `closing` | `check_closing` (gates.py:179) | Last 200 chars contain an engagement ask, "Note:" closer, `?`, or 🤝/👊. | `rules.yaml §engagement_bank` + `gate_params.close_detect_window` + `close_fallback_phrases` |
| 11 | `frontmatter` | `check_frontmatter` (gates.py:196) | Required frontmatter fields present: `title`, `created`, `tags`, `platform`. | `gate_params.required_frontmatter_fields` |
| 12 | `dollar_in_note` | `check_dollar_in_note` (gates.py:205) | No `$N` in a `Note:` closer (cost pitch belongs in body, not meta-closer). | (no toggle) |
| 13 | `strategy_void` | `check_strategy_void` (gates.py:213) | Frontmatter has `pillar:` or `pattern:`. | (no toggle — gate must pass) |
| 14 | `icp_present` | `check_icp_present` (gates.py:223) | Frontmatter has `icp:`. | (no toggle — gate must pass) |
| 15 | `grounded_reference` | `check_grounded_reference` (gates.py:230) | Named people (Karpathy, Feynman, etc.) have a grounding appositive (", the AI researcher"). | `rules.yaml §known_names` |

### Toggling a hard gate

Set the gate key to `false` in `rules.yaml §gates`. A disabled gate returns `(True, "SKIP: disabled in rules.yaml")` and counts as a pass.

```yaml
# rules.yaml
gates:
  char_count: true
  hook_check: true
  # ...all 15 here...
```

---

## 2. Soft gates (LLM-judged, advisory only)

**File:** these checks appear in the LLM-facing prompt (`system/prompts/compiler.md` and are visible in `system/prompts/wizards.md`). The LLM applies them at drafting time. **They are not mechanically scored** by `gates.py`. Treat them as a checklist the LLM should satisfy; do not expect a numeric score.

### 4-check baseline (standalone test)

> Would a stranger walk away with one idea from a single read?

1. **5-second test.** A reader skimming can extract 1 idea in 5 seconds.
2. **No-prior-episode test.** Does not require reading earlier posts.
3. **Value-without-me test.** Replacing "I" with a stranger's name still works.
4. **Explain-to-a-friend test.** Can be re-told without "you had to be there."

If yes: ship. If no: fix the opener or scrap the post.

### 10-gate extended (LLM-judged)

1. **ICP gate** — a stranger knows in 5 seconds if it's for them.
2. **5-questions gate** — who, what problem, why now, what they get, what they do.
3. **Hook formula gate** — line 1-2 is a hook, line 3 is a promise.
4. **No-repetition gate** — no noun 3+ times, no repeated engagement ask.
5. **Sentence cap gate** — every sentence capitalized (LinkedIn), no paragraph over 2 lines.
6. **Mechanical gates passed** — all 15 checks in `engine/gates.py`.
7. **One-sentence-one-reader gate** — a 15-word sentence naming reader + outcome.
8. **Source pillar named in frontmatter** (if applicable).
9. **Sensitivity check passed** — no code internals, no internal labels, no credentials.
10. **No "$5 stack" closing reflex** — cost pitch is 1-in-5 motif, not closer.

### ICP quality test (supplementary)

- No system talk — does the post mention the engine, pipeline, or build mechanics?
- Not engineering notes — is it a journal entry for the operator, not the reader?
- No session reference — does it leak session log fields?
- ICP present — is the technical founder named or addressed?
- Insight about their world — does it shift how they see their work, not how they see your work?

### Reader failure mode mapping (session mode)

When a session log includes `reader_failure_mode`, the compiler (Step 4) uses it as upstream evidence:

| Field | Maps to Step 4 question |
|---|---|
| `.belief` | What ICP belief does this contradict? |
| `.consequence` | What ICP frustration does this expose? |
| `.mapping` | What new mental model does this session support? |

These labels are **banned in public posts** but **required in session-log frontmatter**.

### Pillar 3-pass rule (blog posts only)

1. **Cut** — remove every sentence that doesn't earn its place.
2. **Rhythm** — vary sentence length. Long, short, long. No 3 long sentences in a row.
3. **Payoff** — the last paragraph delivers the durable insight. Cut any closer that doesn't.

---

## 3. Configuration (rules.yaml)

The single source for tunable values. Read by `engine/engine_config.py` and exposed as typed accessors.

### Posting behavior

```yaml
posting:
  mode: manual              # manual | auto-always
  require_confirm: [blog, linkedin]
  max_auto_day: 3
```

### Pipeline recovery

```yaml
pipeline:
  stale_after_minutes: 5
  strategy_injection_cap_chars: 1500   # voice-corpus.md is exempt
```

### Strategy defaults

```yaml
strategy:
  primary_offer: spiel-engine-dfy
  icp_profile: technical-founder
  funnel_default: TOFU
  content_verticals: [builder-to-lead-system, content-automation-ai-agents, ...]
  pages: [icp, funnel, voice, session, corpus]    # injected at handoff
  archetypes:        { S1_system_build: [...], S2_ship: [...], ... }   # classifier keywords
  verticals:         { ... }
  funnel_stages:     { TOFU: [...], MOFU: [...], BOFU: [...] }
  icp_layers:        { L1_surface: [...], L2_mid: [...], L3_deep: [...], L4_root: [...] }
```

### Character limits (per surface)

```yaml
char_limits:
  linkedin_casual: 1500
  linkedin_polished: 3000
  x_single: 280
  x_thread_max_tweets: 12
  blog_pillar_words: 2500
  buffer: 2200
```

### Gate parameters (tune algorithmic thresholds)

```yaml
gate_params:
  close_detect_window: 200
  close_fallback_phrases: ["note:", "?"]
  word_repeat_scale_small: 500
  word_repeat_scale_medium: 1500
  word_repeat_scale_large_min: 6
  word_repeat_scale_large_max: 12
  required_frontmatter_fields: [title, created, tags, platform]
  strong_audience_triggers: [you , your , you're, you'll, founders, builders, ...]
```

### Posting cadence (rate limits per platform)

```yaml
cadence:
  x:       { per_day: 10, per_week: 70 }
  linkedin: { per_day: 3, per_week: 21 }
  blog:    { per_day: 1, per_week: 7 }
```

### Template selector weights

```yaml
template_selector:
  enabled: true
  weights: { archetype: 0.30, meaning_axis: 0.25, funnel_stage: 0.20, icp_layer: 0.15 }
  ranker_weights: { substance: 0.30, archetype: 0.20, psych_match: 0.20, anti_density: 0.15, engagement: 0.15 }
  top_n: { x: 5, linkedin: 3, blog: 2, pillar: 2 }
  category_priors: { ship_log: { archetypes: [S2, S8, S10], multiplier: 1.3 }, ... }
```

### Compiler config

```yaml
compiler:
  meaning_axes: [systemic, behavioral, philosophical, contrarian, leverage, human]
  mode_routing:
    session: { default_axis: human, default_funnel: TOFU, cta: none }
    topic:   { default_axis: leverage, default_funnel: MOFU, cta: try-it,
               archetype_funnel_override: { S2: MOFU, S8: MOFU } }
```

### Quality threshold (advisory — soft gates not yet scored)

```yaml
quality:
  composite_threshold: 0.85      # not enforced
  gates:
    mechanical: 15
    four_check: 1
    ten_gate: 10
    icp_quality: 3
    total: 29                     # 15 mechanical + 14 LLM-judged
```

### Creds required per platform

```yaml
creds_required:
  buffer:   [BUFFER_ACCESS_TOKEN, BUFFER_CHANNEL_IDS]
  x:        [X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]
  linkedin: [LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN]
```

---

## 4. Trigger word banks (used by hard gates)

These are lookup lists the mechanical checks match against the body. Edit them in `rules.yaml`, not in code.

| Bank | Used by gate | Purpose |
|---|---|---|
| `safe_openers` | `project_as_subject` | First-word whitelist (first-person, reader-address, questions). |
| `banned_openers` | `hook_check` | Regex patterns for "today I want to talk about" / "hey friends" / etc. |
| `lesson_triggers` | `lesson_surfaced` | "I learned", "the takeaway", "here's the thing", etc. |
| `audience_triggers` | `audience_named` | "for ", "to ", "any ", "founders", etc. |
| `strong_audience_triggers` | `audience_named` | Higher-signal subset ("you ", "your ", "you're", "founders", "builders"). |
| `engagement_bank` | `closing` | "what's your take?", "drop a comment", "dm me", etc. |
| `architecture_leaks` | `architecture_leak` | Regex blocklist for internal labels. |
| `generic_statements` | `generic_statement` | Platitude blocklist ("content is king", "trust the process"). |
| `common_words` | `word_repeat` | Words excluded from repetition count. |
| `known_names` | `grounded_reference` | Proper nouns that require a grounding appositive. |

---

## 5. Suggestions (injected at handoff)

These are LLM-guidance docs read at handoff time. The engine inlines them into the LLM prompt via `_print_strategy_injection` (engine.py:844). They are not mechanically enforced.

| Doc | File | Injected at |
|---|---|---|
| ICP World | `strategy/icp.md` | COMPILE handoff |
| Funnel + Matrix | `strategy/funnel.md` | COMPILE handoff |
| Voice + Gates | `strategy/voice.md` | COMPILE + DRAFTING handoff |
| Voice Corpus (8 examples, full) | `strategy/corpus.md` | DRAFTING handoff |
| Session as Content | `strategy/methodology.md` | COMPILE handoff |
| Archetypes | `strategy/archetypes.md` | Indirect (via classifier) |

---

## 6. Where each rule is read

| Source | Read by | When |
|---|---|---|
| `system/gates.md` (this file) | humans, contributors | docs |
| `system/rules.yaml` | `engine/engine_config.py` | every engine startup |
| `engine/gates.py:ALL_CHECKS` | `engine/gates.py:validate_draft` | GATE_CHECK state |
| `system/prompts/compiler.md` | LLM via `engine/prompts_loader` | COMPILE handoff |
| `system/prompts/leak-guard.md` | LLM via `_data_block_banner` | COMPILE handoff (DATA blocks) |
| `system/prompts/wizards.md` | LLM via subagent | FORMAT_WIZARD + PUBLISH_WIZARD |
| `strategy/*.md` | LLM via `_print_strategy_injection` | COMPILE + DRAFTING handoff |
| `templates/registry/viral-templates.yaml` | `engine/selector_keyword.select` | SELECT state |
| `templates/registry/performance.json` | `engine/ranker.score_template` | ANALYZING_POST |

---

## 7. Composite score (advisory)

Formula: `(passes / 31 total gates) = 15 mechanical + 1 (4-check baseline) + 10 (10-gate extended) + 5 (ICP quality)`.

Threshold: `quality.composite_threshold` in `rules.yaml` (default `0.85`).

**Status: not enforced.** The 14 LLM-judged gates are documented but not run in code. The threshold is defined as a placeholder for future wiring. See `gates.py` — the 15 mechanical checks are the only ones actually computed. A draft passes the GATE_CHECK state when all 15 mechanical checks pass; the soft gates are an LLM self-check at drafting time.
