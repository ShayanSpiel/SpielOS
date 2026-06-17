# Porting: TheSpielEngine

TheSpielEngine is the portable backend. Changes are developed in a root
vault (where the user keeps their personal content strategy and personal
data) and ported here as feature-only updates.

**Model:** manual port. No symlinks. No auto-merge.

## When to port

- You say "port the engine" or "push the engine"
- Before a public push to GitHub
- After a feature/script change has been tested in the root vault

## What to port

Any script change in `scripts/` that:
- Fixes a bug shared by both vaults
- Adds a useful feature (e.g., banner auto-scale, gate guard)
- Improves portability (auto-resolve paths, no hardcoded names)

Do NOT port:
- Anything hardcoded to a personal vault path
- Personal brand names, handles, or branding strings
- Personal strategy data (`rules.yaml`, `concepts/*.md` personal files)
- `.env` files (each vault has its own)
- Personal `concepts/*.md` content (root vault has ICP/voice/funnel data; portable engine ships with skeletons only)

## How to port

```
1. Make the change in <root-vault>/scripts/
2. Test it: spiel status
3. Copy the change to TheSpielEngine/scripts/
4. Test it there: spiel status
5. Commit + push the engine
```

## Files that may differ between the two vaults

| File | Root vault | TheSpielEngine (portable) | Porting rule |
|------|------------|--------------------------|--------------|
| `pipeline.sh` | May have personal paths in comments | Auto-resolve VAULT, neutral comments | Port changes both ways, keep generic style |
| `engine.py` | "═══ <root-vault-name> State ═══" branding | "═══ Spiel Engine State ═══" branding | Port feature changes. Keep branding per vault. |
| `banner_tool.py` | Should match engine | Should match root vault | Keep in sync. Banner tool is shared code. |
| Other scripts | Independent copy | Independent copy | Port feature changes. |

## Typical port session

When you say "port the engine", the agent will:
1. Diff `<root-vault>/scripts/` vs `TheSpielEngine/scripts/`
2. Identify changes worth porting
3. Apply feature changes to the engine
4. Apply engine-only improvements back to the root vault
5. Commit the engine with a clean message
6. Show you the diff for approval
7. Force-push on approval

## Production readiness checklist

Before pushing a port to GitHub:
- [ ] `scripts/bin/spiel` exists and is executable
- [ ] `engine.py` has `os.chdir(VAULT)` at startup
- [ ] `publishers/` package exists (buffer/twitter/linkedin)
- [ ] `banner_tool.py` is the v2 Playwright version (not old `banner.py`)
- [ ] `tests/test_shim.py` passes (4 resolution paths)
- [ ] `tests/test_chain.py` passes (cross-cwd invocation)
- [ ] `pytest tests/` passes all 197+ tests
- [ ] `README.md` has the `### The spiel shim` section
- [ ] `README.md` uses `spiel <cmd>` in all examples
- [ ] No personal GitHub URL in `README.md`
- [ ] No personal-name references anywhere (`grep -ri "<your-name>\|<your-handle>" .` returns 0)
- [ ] `concepts/icp-offer.md` is a placeholder (not personal data)
- [ ] `concepts/voice-corpus.md` is a placeholder
- [ ] `assets/brand-config.json` has `name: "Your Brand"` placeholder
- [ ] `pyproject.toml` has `[build-system]` + `[project]` with deps
- [ ] `.gitignore` covers `.env`, `__pycache__/`, `.opencode/`, `assets/banners/.preview/`
- [ ] No `.env` file in the repo (gitignored)
- [ ] No `.cursor/` directory
- [ ] No `__pycache__/` directories
