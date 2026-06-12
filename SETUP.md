# Setup Guide

Run `bash scripts/install.sh` to auto-install, or follow manually below.

## Manual Setup

### 1. Copy rules.yaml

```bash
cp rules.yaml.example rules.yaml
```

### 2. Set VAULT_DIR

Create a `.env` file in the vault root:

```bash
echo 'VAULT_DIR=/path/to/TheSpielEngine' >> .env
```

Or export in your shell profile:

```bash
export VAULT_DIR=/path/to/TheSpielEngine
```

### 3. Configure opencode

```bash
cp -r .opencode/* ~/.config/opencode/
```

This copies commands and the content skill.

### 4. Run /setup

In opencode (or any agent), run `/setup` to answer the 12-question
questionnaire. This fills in your ICP, offer, and voice configuration.

### 5. (Optional) Configure posting credentials

Create `~/.config/opencode/.env`:

```
X_BEARER_TOKEN=your_token
LINKEDIN_ACCESS_TOKEN=your_token
```

## Questionnaire (12 Questions)

### Block 1: Identity
1. What is your brand name and tagline?
2. Who are you as a creator? (1-2 sentences)
3. What is the core idea your content revolves around?

### Block 2: ICP
4. Who is your ideal reader? (demographics, psychographics)
5. What problem does your ICP struggle with daily? (4 layers)
6. What 7 questions does your ICP ask internally?

### Block 3: Offer
7. What do you sell in the customer's words?
8. How does the ICP describe the problem before your solution?
9. What do they say after?

### Block 4: Voice
10. Describe your writing voice in 3 words.
11. Paste your 3 best posts (LLM will analyze for patterns).
12. What is one thing you never want to sound like?

## Git Clone Distribution

```bash
git clone <url> TheSpielEngine
cd TheSpielEngine
bash scripts/install.sh
```

## Manual Zip Distribution

1. Unzip the engine
2. `bash scripts/install.sh`
