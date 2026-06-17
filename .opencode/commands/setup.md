---
description: Run 14-question engine setup questionnaire
---

# /setup — Configure Engine

14-question setup in 5 blocks. Writes answers into the engine config and installs the `spiel` shim.

## What /setup does

1. **Install the `spiel` shim** — copies `scripts/bin/spiel` to `~/.local/bin/spiel` and ensures `~/.local/bin` is on PATH (idempotent, adds a single line to `~/.zshrc` with a `# spiel-engine-shim-path` marker).
2. **Write `VAULT_DIR` into `~/.config/opencode/.env`** so the shim can find this vault from any project.
3. **Run the 14 questions** (5 blocks) and write the answers into:
   - `concepts/icp-offer.md`
   - `concepts/voice-corpus.md`
   - `concepts/funnel-and-matrix.md`
   - `rules.yaml` (strategy section, merged)
   - `assets/brand-config.json`

## Blocks

### 1. Identity
1. What is your brand name and tagline?
2. Who are you as a creator?
3. What is the core idea your content revolves around?

### 2. ICP
4. Who is your ideal reader?
5. What problem does your ICP struggle with daily? (4 layers: surface → root)
6. What 7 questions does your ICP ask internally?

### 3. Offer
7. What do you sell in the customer's words?
8. How does the ICP describe the problem before your solution?
9. What do they say after?

### 4. Verticals + CTAs
10. What main content verticals or topics do you cover?
11. What action do you want readers to take after each post?

### 5. Voice
12. Describe your writing voice in 3 words.
13. Paste your 3 best posts. (The LLM will analyze for patterns.)
14. What is one thing you never want to sound like?

Each block has a "Skip — I'll edit the file myself" option. The questionnaire can be re-run to update any section.
