# SpielOS Reliability Audit + Remediation Plan

**Status:** Audit complete. Plan documented. **Not yet executed.**
**Date:** 2026-06-29
**Scope:** Pipeline reliability, production readiness, install/update/wizard, adapters + Codex plugin, publisher dispatch, structure leanness, and machine-state JSON relocation.

> Note: This document was to be saved to project root as `Reliability.md`, but a permission rule restricts edits to `.opencode/plans/*.md`. It lives here instead — move to root when ready.

---

## 1. Executive summary

The pipeline's deterministic core (`post.py`, `advance.py`, `simulator.py`, atomic IO, state machine) is sound. The reliability risk is concentrated in **the surfaces around it**: vault resolution, the `spiel update`/adapter-sync path, the wizard backend, the publisher dispatchers, and the absence of CI.

**Headline numbers:** 10 CRITICAL, 14 HIGH, 18 MEDIUM, 14 LOW issues found across 4 subsystems. 3 tests are currently red. No CI exists. Two `spiel update` code paths **silently destroy user IDE config** on every run. One publisher path **silently deletes blog content**. The `--vault` override is a no-op in all three social publishers.

**One decision is locked:** machine-state JSONs move from `content/` to `system/state/` (machine-state only; `current.md` stays in `content/`). This is a ~30-file mechanical change detailed in §7.

---

## 2. Methodology

Three parallel deep-dive passes (install/wizard, adapters/plugins, publisher/tests) over the full tree, plus direct verification of every CRITICAL claim against source. No files were modified during the audit. All file:line references are against the current tree.

---

## 3. Findings — CRITICAL

| # | Issue | Location | Verified |
|---|---|---|---|
| C1 | **Vault resolution order contradicts AGENTS.md.** Both `bin/spiel` and `_vault.py` check `~/.config/spielos/config` **before** `$VAULT_DIR`. Post-install the global config always exists, so `VAULT_DIR=/other/vault spiel post` silently operates on the wrong vault. The shim's own header comment (lines 7-12) contradicts its inline help (lines 68-73) which contradicts AGENTS.md. | `bin/spiel:91-107`, `tools/_vault.py:46-63` | yes |
| C2 | **`sed -i ''` is BSD-only → `spiel update`, `set-vault`, `set-source` abort on Linux.** `set -euo pipefail` (bin/spiel:28) turns the GNU-sed error into a hard exit, leaving the vault updated but pointer files stale. | `bin/spiel:636,669` (and `:358` in `_rewrite_vault_pointers`) | yes |
| C3 | **`install_claude_hooks` wipes the user's `hooks` key** in `~/.claude/settings.json` on every `spiel update`. `adapters/claude/hooks.json` is `{}`, so `existing["hooks"] = {}` replaces every user hook. | `tools/sync_adapters.py:670` | yes |
| C4 | **`install_cursor_hooks` overwrites the entire `~/.cursor/hooks.json`** with the empty stub on every update. No merge at all. | `tools/sync_adapters.py:694-699` | yes |
| C5 | **Dashboard "Run /post" invokes the bash shim through `python3`** → `NameError`. The primary CTA is dead. | `install/wizard/serve.py:358` | yes |
| C6 | **Wizard has no CSRF/Origin protection** and sets `Access-Control-Allow-Origin: *`. Any open browser tab can POST to `/api/finish`, `/api/env/set`, `/api/file` and write `strategy/`, `team/`, `.env`. | `install/wizard/serve.py:742,930-935` | yes |
| C7 | **`blog.sh` `strip_leading_h1` deletes the first content paragraph** of every post whose H1 matches its title (the normal case). Duplicated `if` block re-deletes `lines[0]` after the H1 is already gone. | `tools/publisher/blog.sh:444-450` | yes |
| C8 | **`blog.py` Hashnode publication lookup broken** by operator precedence: `(... or {}).get("me") or {}` chains parse `{}` as the receiver of `.get("publications")`, always returning `[]`. Auto-discovery never works without `HASHNODE_PUBLICATION_ID`. | `tools/publisher/blog.py:202-203` | yes |
| C9 | **`--vault` override is a no-op in all 3 social publishers.** `twitter.py`/`linkedin.py` set local `ENV_FILE`/`POSTED_DIR` globals that `_common.load_creds()`/`archive()` never read. `buffer.py` mutates `_common` attrs but its own `ENV_FILE` binding stays stale. Creds load from the wrong `.env`; archives land in the wrong `posted/`. | `tools/publisher/{twitter,linkedin,buffer}.py` | yes |
| C10 | **3 tests in `test_stamp_and_gates.py` are red.** Fixtures predate the `meaning` field + `## Trace` block requirement, so `brief_complete`/`trace_present`/`axis_valid` fail. With no CI, this is invisible. | `tests/test_stamp_and_gates.py:178-202` | yes (`21 passed, 3 failed`) |

---

## 4. Findings — HIGH

| # | Issue | Location |
|---|---|---|
| H1 | **`/api/skeleton/<name>` path traversal** — `name` is unsanitized; `/api/skeleton/../../../.env` reads secrets. Compounds with C6. | `install/wizard/serve.py:806-811` |
| H2 | **All wizard file writes are non-atomic** (`Path.write_text` truncate-then-write). `/api/finish` writes 7+ files sequentially; a crash mid-sequence leaves a half-configured vault. The 3s `os._exit(0)` timer can race an in-flight request. | `install/wizard/serve.py:69,421,454,510,521,885,909` |
| H3 | **No lock on `/api/finish`** — `ThreadingHTTPServer` + double-click = concurrent read-modify-write on `.env` → data loss. | `install/wizard/serve.py:890-919` |
| H4 | **Codex `post.toml` falsely assumes the hook ran.** When the hook is untrusted or `spiel` is off PATH, `post.toml` still tells the LLM "The hook already ran `spiel post`. Run: `spiel next`" → state corruption / out-of-order dispatch. | `adapters/codex/agents/post.toml:50-58` |
| H5 | **Hook `exit 0`s silently when `spiel` is not found**, so Codex reports success while doing nothing. | `plugins/spielos/scripts/post-hook.sh:15` |
| H6 | **Hook's `../../../bin/spiel` never resolves in the plugin cache** — `install_codex_plugin_hooks` never copies `bin/spiel` into the cache, so the relative lookup always fails and the hook depends entirely on PATH. | `plugins/spielos/scripts/post-hook.sh:7-9`, `tools/sync_adapters.py:470-514` |
| H7 | **No checksum/signature on `curl|bash`** download; `SPIELOS_VERSION` defaults to `main`. Supply-chain risk for a script that installs a PATH shim + prompt hooks. | `install/install.sh:194,198-201,209-212` |
| H8 | **Re-install/update overlay uses non-atomic `shutil.copy2`** — a crash mid-overlay leaves truncated tool files. | `install/install.sh:268`, `bin/spiel:300,566` |
| H9 | **`_cleanup_stale_files` may delete the user's non-SpielOS IDE files** — it removes any installed file not in `_expected_content()`, with no SpielOS-marker guard. | `tools/sync_adapters.py:843-847` |
| H10 | **MCP config corrupts JSONC via string manipulation** (find-last-`}` insert) for `opencode.jsonc`. Comments/trailing commas break it. | `tools/sync_adapters.py:1026-1042` |
| H11 | **`check_gates_verdict` accepts any non-`fail` value** (`maybe`, `pending`, `pas` all pass). Should whitelist `pass`. | `tools/publisher/_common.py:182-197` |
| H12 | **`blog.sh` does not enforce `gates_verdict`** — only checks `status: ready`. A failed-gate draft can ship to the public blog. | `tools/publisher/blog.sh:188-193` |
| H13 | **Direct publishers: no retry, no error-body extraction, "posted" confirmation inside the archive try.** A 429 kills the publish with no diagnostic; an archive failure hides the live post → double-post on retry. | `tools/publisher/twitter.py:65-67,114-119`, `linkedin.py:57-58,106-111` |
| H14 | **`spiel set-vault` overwrites the global config with `>`**, destroying `SOURCE_DIR` if set (unlike `_rewrite_vault_pointers` which merges). Also non-atomic. | `bin/spiel:630` |

---

## 5. Findings — MEDIUM (summary)

- `rules.yaml` banned-label list incomplete: missing `L1-L4`, "the engine", "the pipeline" (`rules.yaml:17-24`).
- `sanitize()` leaks `[link](url)` and `#`/`###` headings to social platforms; `LEAKED_MARKDOWN` regex doesn't catch `](` (`_common.py:118-126`).
- Blog 2500-word limit in `rules.yaml` vs "unbounded" in docs — decide and align (`rules.yaml:9-10`).
- Em-dash checked twice (em_dash gate + banned.regex `"—"`) — remove the redundant entry.
- `buffer_channels` UI selection silently dropped — never mapped to `BUFFER_CHANNEL_IDS` (`serve.py:472-493`).
- `os._exit(0)` on a 3s timer bypasses cleanup and can orphan `run_post_install` subprocess (`serve.py:909`).
- MCP client stderr pipe never drained → deadlock risk; `stop()` can raise `TimeoutExpired` (`_mcp_client.py:46-62`).
- Hashnode non-publish mode sends invalid GraphQL settings fields (`blog.py:242-245`).
- `blog.sh` `source`s the entire `.env` → leaks all secrets to every child process (`blog.sh:45`).
- `blog.sh` commit message contains an em-dash (`blog.sh:552`).
- `_read_platform` in buffer.py silently defaults to "linkedin" on missing platform (`buffer.py:79-90`).
- buffer.py confirmation prompt hardcodes "LinkedIn" regardless of platform (`buffer.py:218`).
- `_vault.py` lacks the shim-bundled resolution step → doctor can fail when the shim works.
- `--check` stale-file detection broken (Path-vs-generator membership test, always empty) and exit codes swapped vs docs (`sync_adapters.py:1168-1185`).
- `emit_mcp` bakes in `str(VAULT)` not `TEMPLATED_VAULT_ROOT` (`sync_adapters.py:286-300`).
- Codex `post.toml` is self-bootstrapping with no canonical source → drifts forever from `team/post.md`; contains stale `@director` reference.
- `_rewrite_vault_pointers` config write non-atomic (`bin/spiel:346`); `.spiel-vault`/global config writes use shell `>` (`install.sh:371,376`).
- `codex_hook.py` session mode runs `spiel reset` on bare `/post` before the user confirms — can destroy an in-progress run (`codex_hook.py:111-121`).

---

## 6. Findings — LOW (summary)

- 5 dead skills (`format_wizard`, `icp_simulation`, `publish_wizard`, `template_picker`, `voice_match`) — confirmed unused; `team/strategist.md:219` bans `format_wizard`. Empty leftover dirs in `adapters/opencode/skill/`. Only `plugins/spielos/skills/spiel-post` is live.
- `adapters/` saturated with `/private/tmp/spielos-test-vault` test paths (gitignored but messy; breaks `spiel sync --check`).
- Stray `.backup-post-hook.ts` in root; dormant banner infra (`tools/designer.py`, `assets/icons/`, `tools/banner-templates/`).
- Legacy gitignore entries from old architecture (`.brief/`, `.engine-state`, `.content-brief.json`, `.werk/`, `.vault/`).
- `tools/publisher/` missing `__init__.py`; `_common.py` imports `sys` twice; `buffer.py` `__import__` convolutedness.
- Temp-file path drift across codex_hook.py / post.toml / SKILL.md / team/post.md (`/tmp/spiel-session-*` vs `/tmp/spiel-capture.*`).
- `spiel continue` vs `spiel next` drift between hook and agent prompts.
- `strip_invocation` only checks the first line (`codex_hook.py:51`).
- Grounding `_tokenize` drops <3-char tokens (loses "AI", "PR", "API"); banned-word matching misses word variants (`editor.py:212-223,503`).
- `plugin.json` version hardcoded `1.0.0` with no bump mechanism; `defaultPrompt` uses `@post` not `/post`.
- `hook_log.py` rotation non-atomic; `next.py` tz handling convoluted; `guard.py` `cmd_clean` overwrites name collisions in `rejected/`.

---

## 7. Machine-state JSON relocation (decision: locked)

**Decision:** move machine-state files to `system/state/` (subfolder). `content/current.md` stays in `content/` (creative handoff, user-facing).

### 7.1 What moves

| Old path | New path | Owner tool |
|---|---|---|
| `content/.state.json` | `system/state/.state.json` | `advance.py` |
| `content/.icp-world.json` | `system/state/.icp-world.json` | `simulator.py` |
| `content/.run-counter` | `system/state/.run-counter` | `post.py` |
| `content/runs/<run_id>/events.jsonl` | `system/state/runs/<run_id>/events.jsonl` | `post.py` |
| `content/current.md` | **stays** | `post.py` |

### 7.2 Why `system/state/` is safe (and must be skip-listed)

`system/` is in the update "refresh" column, but only `system/brand.*` and `system/rules.yaml` are currently skip-listed. The overlay only writes files present in the tarball (and these dotfiles are gitignored, so absent from the tarball) — so it will not clobber them. **Defense-in-depth:** add `system/state` to `_SPielos_SKIP_DIRS` (bin/spiel:236) and `skip_dirs` (install.sh:242), and add `system/state/` to `.gitignore`. Update `test_skip_list.py` to assert preservation.

### 7.3 Implementation approach

Centralize the path so this never scatters again: add `state_dir(vault)` / `state_file(vault, name)` helpers to `tools/_vault.py` (or a new `tools/_state.py`) and have every tool import from there. Role prompts and docs reference the constant path string `system/state/...`.

### 7.4 Reference update checklist (~30 files)

**Tools (path constants):**
- `tools/post.py` — `RUN_COUNTER_REL`, `ICP_WORLD_REL`, `run_dir()` (runs/), the reset logic that deletes `.state.json` + `.icp-world.json` (`post.py:238-251`).
- `tools/advance.py` — `STATE_FILE_REL` (`advance.py:77`).
- `tools/simulator.py` — `ICP_WORLD_REL` (`simulator.py:64`).
- `tools/editor.py` — `icp_path` (`editor.py:574`).
- `tools/next.py` — `state_path` (`next.py:91`).
- `tools/guard.py` — `path` (`guard.py:15,44,47`).
- `bin/spiel` — `state_file` in `status` (`bin/spiel:397`); `reset` deletes `content/.state.json` + `content/current.md`.
- `install/wizard/serve.py` — dashboard `state_path` (`serve.py:209`).

**Role prompts (read paths):** `team/strategist.md`, `team/writer.md`, `team/editor.md`, `team/publisher.md`.

**Tests:** `test_advance.py`, `test_post_runtime.py`, `test_simulator.py`, `test_stamp_and_gates.py`, `smoke.py`.

**Docs/schemas:** `system/run-state.md`, `system/icp-world-schema.md`, `system/draft-schema.md`, `system/pipeline.md`, `system/session-schema.md`, `AGENTS.md`, `README.md`, `team/README.md`.

**Skip-list / gitignore:** `bin/spiel:236`, `install/install.sh:242`, `.gitignore`, `tests/test_skip_list.py`.

---

## 8. Wizard — backend issues that survive the UI redesign

The UI is being redesigned; the following are **backend** issues and must be fixed regardless of the new UI:

- C5 (python3 runs bash), C6 (CSRF/Origin), H1 (path traversal), H2 (atomic writes), H3 (finish lock) — see §3/§4.
- `buffer_channels` → `BUFFER_CHANNEL_IDS` mapping missing (§5).
- `run_post_install` duplicates `install.sh` post-wizard steps — gate on `--exit-on-finish`.
- `bootstrap_vault` has a duplicate `team/strategist.md` entry (`serve.py:986`).
- Frontend-only (for the redesign): CDN assets without SRI; `@import` after other CSS rules; inline ~550-line dashboard script; `localStorage` crash-recovery has no vault-identity check.

---

## 9. Leanness / structure cleanup

- Delete the 5 dead skills + empty `adapters/opencode/skill/{format_wizard,publish_wizard,voice_match}/` dirs; prune `archive/skills/` if not referenced.
- Clean `adapters/` of `/private/tmp/spielos-test-vault` artifacts (regenerate via `spiel sync`).
- Remove stray `.backup-post-hook.ts` from root.
- Decide on dormant banner infra (`tools/designer.py`, `assets/icons/`, `tools/banner-templates/`) — delete or document as dormant.
- Remove legacy gitignore entries (`.brief/`, `.engine-state`, `.content-brief.json`, `.werk/`, `.vault/`).
- Add `tools/publisher/__init__.py`; remove double `import sys` in `_common.py`; simplify buffer.py `__import__`.
- Resolve `blog.sh` vs `blog.py` documentation split (AGENTS.md lists only `blog.sh`; `publisher.md` instructs `blog.py`).

---

## 10. Remediation plan (phased)

### Phase 0 — Stop the bleeding (quick, high-leverage)
1. C3/C4: make `install_claude_hooks`/`install_cursor_hooks` merge by event (deep-merge), and skip when canonical `hooks.json` is empty.
2. C1: fix vault resolution order in `_vault.py` + `bin/spiel` (`$VAULT_DIR` before global config); add shim-bundled step to `_vault.py`; reconcile the three contradicting doc strings.
3. C10: fix the 3 red tests (add `meaning`, `## Trace`, `offer.md` to fixtures).
4. H13 (partial): move "posted" print before archive; add `missing_ok=True` to `archive()` unlink.
5. H14: make `set-vault` merge `SOURCE_DIR` (reuse `_rewrite_vault_pointers` logic) and write atomically.

### Phase 1 — CRITICAL reliability
6. C2: replace `sed -i ''` with portable temp+`mv` (or a Python one-liner) at `bin/spiel:358,636,669`.
7. C9: fix `--vault` override in all 3 publishers — update `_common` module attrs (and buffer.py's local `ENV_FILE` binding).
8. C7: delete the duplicated `if` block in `blog.sh` `strip_leading_h1`.
9. C8: fix Hashnode precedence parens in `blog.py`.
10. C5: invoke the shim via shebang/bash, not `python3`.
11. C6 + H1/H2/H3: wizard hardening — drop `*` CORS, validate `Origin`/`Host` on POST, sanitize `/api/skeleton/` name, `threading.Lock` on `/api/finish`, make all writes atomic (temp+rename), wire `buffer_channels`.

### Phase 2 — Machine-state relocation (§7)
12. Add `state_dir` helpers; move the 4 artifacts to `system/state/`; update the ~30 references; add `system/state` to skip-lists + `.gitignore`; update `test_skip_list.py`; update all schemas/docs.

### Phase 3 — HIGH hardening
13. H4/H5/H6: Codex hook — write a sentinel on success; `post.toml` verifies state (run `spiel status`; if not `strategy`, run `spiel post`) instead of assuming; copy `bin/spiel` into the plugin cache OR source `~/.config/spielos/config` in `post-hook.sh`; consider `exit 1` (test Codex behavior) instead of silent `exit 0`.
14. H4 (cont): give `post.toml` a canonical source generated from `team/post.md`; drop the `@director` reference.
15. H11: `check_gates_verdict` whitelist `pass` only.
16. H12: enforce `gates_verdict` in `blog.sh`.
17. H13 (rest): publisher retry/backoff for 429/5xx + error-body extraction.
18. H9: guard `_cleanup_stale_files` with a SpielOS-content marker.
19. H10: safe JSONC edit (or refuse to touch `opencode.jsonc` if it has comments).
20. H7/H8: publish a signed `SHA256SUMS`; pin `SPIELOS_VERSION` to a tag; make overlay writes atomic (temp+rename).

### Phase 4 — Leanness (§9)
21. Remove dead skills, stray files, legacy gitignore entries; decide on banner infra; add `__init__.py`; fix double imports; clean `adapters/` artifacts.

### Phase 5 — CI + coverage
22. Add `.github/workflows/test.yml` running all `tests/*.py` on push/PR (macOS + Linux matrix to catch C2-class bugs).
23. Add `pyproject.toml`/`Makefile` with `lint`/`typecheck`/`test` targets.
24. Add publisher tests (mock MCP client + `urllib`); add an end-to-end install/update test; add a `--check` sync test.
25. Add a doctor check for shim-on-PATH, Python ≥3.10, `.env` + `strategy/*.md` presence.

---

## 11. Acceptance criteria

- `python3 tests/*.py` all green on macOS **and** Linux.
- `spiel update` on a vault with custom Claude/Cursor hooks leaves those hooks intact (verified by test).
- `VAULT_DIR=/x spiel status` resolves to `/x` even when global config points elsewhere.
- A blog post whose H1 matches its title publishes with its first paragraph intact.
- `curl`-install + `spiel update` round-trip preserves `strategy/`, `content/`, `.env`, `system/brand.*`, `system/rules.yaml`, **and** `system/state/`.
- No machine-state files remain under `content/` except `current.md`.
- Wizard rejects cross-origin POSTs and double-`/api/finish`.
- `check_gates_verdict` rejects any verdict ≠ `pass`.

---

## 12. Open items (non-blocking)

- Decide `blog.sh` (GitHub Pages/Jekyll) vs `blog.py` (WordPress/dev.to/Hashnode) as the documented default; update AGENTS.md accordingly.
- Decide whether to keep dormant banner/Designer infrastructure or remove it.
- Confirm Codex's behavior on hook `exit 1` (may block the prompt) before changing H5's `exit 0`.
- Confirm the wizard UI redesign will vendor CDN assets with SRI (frontend, tracked separately).
