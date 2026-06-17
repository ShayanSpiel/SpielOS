# The Spiel Engine — Setup

Clone the repo. Open this file in any LLM-powered agent (Cursor, Claude Code,
opencode, Continue, etc.). Copy from the line below to the end and paste.

---

## SETUP PROMPT — copy from here ↓

**GOAL:** Wire this engine natively into the current environment. Install all
commands, all skills, all configs, the `spiel` shim, and all files. Then run
the 14-question setup and write every config file.

**RULES — obey these without exception:**
1. Do NOT stop before the goal is reached.
2. Do NOT ask me any questions.
3. Do NOT ask about plans, phases, or permission.
4. Do NOT suggest alternatives or present choices.
5. Do NOT estimate or tell me what you will do — just do it.
6. Naively install everything — do not filter, select, or skip anything.
7. After every command/skill is installed, confirm it shows up in the
   agent's native command menu (command palette, slash commands, etc.).
8. When done, report exactly what was installed and where.

### Phase 1 — Read everything from the filesystem

Read every file in these paths cover to cover:

- `SETUP.md` (this file — read it from disk, not from the pasted text)
- `AGENTS.md`
- `.opencode/commands/` — every file
- `.opencode/skill/` — every file
- `concepts/` — every file
- `rules.yaml.example`
- `assets/brand-config.json`

### Phase 2 — Install commands and skills in this platform

Detect which platform you are running on right now. Then install.

**If opencode:**
- Copy `.opencode/commands/` into `~/.config/opencode/commands/` — every file
- Copy `.opencode/skill/` into `~/.config/opencode/skill/` — every file
- Set `VAULT_DIR` to this vault root in `~/.config/opencode/opencode.jsonc`

**If Cursor:**
- Register every command from `.opencode/commands/` as Cursor rules or
  slash commands so they appear in Cursor's command menu
- Inject the skill methodology from `.opencode/skill/` into `.cursorrules`
  or the agent system prompt — fully, not summarized
- Set `VAULT_DIR` as an environment variable in the Cursor project config

**If Claude Code:**
- Set `VAULT_DIR` in `.claude/settings.json` or shell profile
- Register commands so they work as native Claude Code commands
- Inject skill methodology into the project CLAUDE.md or settings

**If Continue:**
- Add every command as a custom slash command in `~/.continue/config.json`
- Insert skill content into the active context provider
- Set `VAULT_DIR` under environment variables

**If unknown platform:**
- Write a complete setup summary at `SETUP_NATIVE.md` listing every command,
  every skill, and where they should be placed for the user to install manually
- Set `VAULT_DIR` as an environment variable

### Phase 2.5 — Install the `spiel` shim

The shim is the single entrypoint. It resolves the vault from
`~/.config/opencode/.env` and execs `scripts/engine.py` inside it — from any
project cwd, in any IDE. Every command in Phase 2 ultimately invokes `spiel`.

1. Confirm `scripts/bin/spiel` exists in this vault. (It does — bundled.)
2. Copy it to `~/.local/bin/spiel`:
   ```bash
   install -d -m 0755 "$HOME/.local/bin"
   install -m 0755 scripts/bin/spiel "$HOME/.local/bin/spiel"
   ```
3. Verify `~/.local/bin` is on PATH:
   ```bash
   echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/.local/bin" && echo "PATH OK" || echo "PATH MISSING"
   ```
4. If PATH is missing, append this idempotent guard to the user's shell rc
   (use `~/.zshrc` for zsh, `~/.bashrc` for bash, `~/.config/fish/config.fish`
   for fish). The `# spiel-engine-shim-path` comment marks the block; the
   `[[ ... ]]` guard makes re-runs safe.
   ```bash
   # spiel-engine-shim-path
   [[ ":$PATH:" != *":$HOME/.local/bin:"* ]] && export PATH="$HOME/.local/bin:$PATH"
   ```
5. Verify the shim works from outside the vault:
   ```bash
   cd /tmp && "$HOME/.local/bin/spiel" --version
   # expected: spiel 1.0.0 / vault: <abs path to this vault>
   ```
6. Write `VAULT_DIR` into the global env file so the shim works without
   inline overrides (the shim reads this as a fallback):
   ```bash
   ENV_FILE="$HOME/.config/opencode/.env"
   mkdir -p "$(dirname "$ENV_FILE")"
   chmod 600 "$ENV_FILE" 2>/dev/null || true
   if ! grep -q '^VAULT_DIR=' "$ENV_FILE" 2>/dev/null; then
     echo "VAULT_DIR=$(pwd)" >> "$ENV_FILE"
   fi
   ```
7. Re-verify from a different cwd:
   ```bash
   cd /tmp && "$HOME/.local/bin/spiel" --where
   # expected: <abs path to this vault>
   ```
8. Report: shim installed at `~/.local/bin/spiel`, vault resolved to `<abs path>`.

### Phase 3 — Filesystem prep

Create these directories (exact names, no changes):

```
assets/banners/
assets/screenshots/
content/queue/
content/rejected/
content/sessions/
content/posted/
logs/
```

If `rules.yaml` does not exist, copy `rules.yaml.example` → `rules.yaml`.
If `.env` does not exist, create it and write `VAULT_DIR=` followed by the
vault root path (the directory containing this SETUP.md file).

### Phase 4 — 14-question setup

Ask all 14 questions in order across 5 blocks. Do NOT ask for confirmation
between blocks. When all 14 are answered, immediately move to Phase 5.

**Block 1 — Identity**
1. What is your brand name and tagline?
2. Who are you as a creator? (1-2 sentences)
3. What is the core idea your content revolves around?

**Block 2 — ICP**
4. Who is your ideal reader? (demographics, psychographics)
5. What problem does your ICP struggle with daily? (4 layers: surface → root)
6. What 7 questions does your ICP ask internally?

**Block 3 — Offer**
7. What do you sell in the customer's words?
8. How does the ICP describe the problem before your solution?
9. What do they say after?

**Block 4 — Verticals and CTAs**
10. What main content verticals or topics do you cover?
    (e.g. "startup growth, technical architecture, team dynamics")
11. What action do you want readers to take after each post?
    (e.g. subscribe, comment, share, book a call, buy a product)

**Block 5 — Voice**
12. Describe your writing voice in 3 words.
13. Paste your 3 best posts. Analyze them for patterns (hooks, structure,
    pacing) and write the analysis into the voice corpus.
14. What is one thing you never want to sound like?

### Phase 5 — Write all config files

Write every file below with the answers filled in. Overwrite existing content.

- `concepts/icp-offer.md` — full ICP profile, offer, funnel stages
- `concepts/voice-corpus.md` — 8 canonical examples with the user's posts
- `concepts/funnel-and-matrix.md` — derive 10 archetypes (S1-S10) from
  the user's content style and ICP answers; fill the name, description,
  and when-to-use columns from the questionnaire. Then fill content
  verticals, funnel stages with goals/CTAs, and the archetype→CTA matrix
- `rules.yaml` — merge the strategy section (ICP, offer, voice, posting mode)
  into the existing config; do not overwrite other sections
- `assets/brand-config.json` — brand name, tagline, voice keywords, content
  focus, target platforms (from Block 1 + Block 5 answers). Leave colors,
  fonts, and logo_path as empty strings for the user to fill later.

### Phase 6 — Verify and report

1. Confirm `VAULT_DIR` resolves to the correct absolute path:
   `spiel --where` from any cwd should print the vault root.
2. Confirm every command from `.opencode/commands/` is wired into this
   platform and visible in the command menu
3. Confirm every skill from `.opencode/skill/` is installed fully
4. Confirm `spiel` is on PATH and works from `/tmp`:
   `cd /tmp && spiel --version` should print `spiel 1.0.0` and the vault path
5. List what was installed and where (exact file paths)
6. Show: `spiel content post "my first post"`

**Do not ask "does this look right?" Do not ask "shall I continue?"**
**The goal is achieved when all 6 phases are complete and verified.**

---

## Note for Forked or Copied Copies

If you received this engine by forking, copying, or zipping it from another
user, the `.git/` history may still carry that user's commit author metadata.
To start with a clean history under your own name, run once after cloning:

```bash
rm -rf .git
git init
git add -A
git commit -m "init: portable Spiel Engine"
git remote add origin <your-repo-url>
```

If you are setting the `origin` remote, replace `<your-repo-url>` with your
fork (e.g. `https://github.com/<your-username>/TheSpielEngine.git`).
