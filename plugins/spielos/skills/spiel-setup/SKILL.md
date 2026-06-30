---
name: spiel-setup
description: Set up the SpielOS vault required before /post can save content.
---

# Set Up SpielOS

Use this skill when the user asks to set up SpielOS, when they install the Codex plugin before running the curl installer, or when `/post` reports that no vault is configured.

SpielOS needs one vault: a folder where strategy files and generated content live. The default vault path is `~/SpielOS`.

## Steps

1. If the user gave a vault path, use it. Otherwise use `~/SpielOS`.
2. Tell the user which vault path will be used.
3. Run the existing installer with that target:

```bash
SPIELOS_INSTALL_DIR="$HOME/SpielOS" bash <(curl -fsSL https://spielos.xyz/install)
```

If the user chose a different path, replace `$HOME/SpielOS` with that path.

4. Let the installer open the wizard. The user completes the wizard in the browser.
5. After the wizard finishes, run `spiel doctor`.
6. If `spiel doctor` passes, tell the user: "Done. Use `/post` from any Codex project."

## Existing Vault

If the user already has a SpielOS vault, do not reinstall. Run:

```bash
spiel set-vault /path/to/SpielOS
spiel doctor
```

## Hard Rules

- Do not run `/post` as part of setup.
- Do not create drafts, ready files, posted files, or session files.
- Do not silently use the current project as the vault.
- Do not duplicate the content pipeline. Setup ends when the vault and adapters are installed.
