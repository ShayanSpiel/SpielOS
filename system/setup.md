# SpielOS Setup

This is the canonical setup contract. Setup is separate from `/post`.

## Mission

Create or select one SpielOS vault: the folder where strategy files, brand config, credentials, generated content, run state, and IDE adapters live.

## Default

Use `~/SpielOS` unless the user provides a different absolute path.

## Fresh Setup

1. Explain: "SpielOS needs a vault, a folder where your strategy files and generated content live."
2. Use the default path `~/SpielOS`, unless the user supplied another path.
3. Run the installer with that target:

```bash
SPIELOS_INSTALL_DIR="$HOME/SpielOS" bash <(curl -fsSL https://spielos.xyz/install)
```

4. The installer opens the setup wizard.
5. The wizard writes strategy files, brand config, `.env`, `.spiel-vault`, `~/.config/spielos/config`, the `spiel` shim, IDE adapters, and Codex plugin hook files.
6. End state: `/post` works from any supported IDE project and saves to the configured vault.

## Existing Vault

If the user already has a vault, do not reinstall. Point SpielOS at it:

```bash
spiel set-vault /path/to/SpielOS
```

Then run:

```bash
spiel doctor
```

## Hard Rules

- Do not run setup from `/post`.
- Do not write content files during setup.
- Do not choose a project working directory as the vault unless the user explicitly chooses it.
- Do not create a fallback vault silently.
- Do not duplicate the content pipeline here. `team/post.md` owns `/post`; `team/*.md` owns role behavior.
