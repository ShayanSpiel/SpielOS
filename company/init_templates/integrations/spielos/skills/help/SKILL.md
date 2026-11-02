---
name: help
description: Show SpielOS commands, available skills, Director usage, setup and troubleshooting when the user asks how to use the plugin or cannot find its commands, hooks or cards.
---

Explain the installed entry points in the host's skill picker: setup, director, dashboard, spielos-company, spielos-build-workflow, spielos-run-workflow and spielos-review-output. In Codex users can invoke a skill with `$<skill-name>` or select its plugin-qualified entry. The host may display a namespace such as spielos:director. Do not promise custom native slash commands: `/status`, `/stop` and `/approve` are Codex controls, not plugin-owned commands.

Director is the role of the main chat operating one selected company, not a second agent that must be spawned. Setup chooses or creates that folder, prepares local recording, opens its dashboard and guides normal host hook review. Opening a chat in product source does not make it a company home. Installation alone does not trust hooks.

For missing entries, inspect the installed plugin version and enabled state, then refresh the plugin or reopen the chat if the host still has an old catalog. Never reinstall from Karwise or another product. For missing context/receipts, check the selected company folder, shipped hook definitions, host trust status and actual events. Explain what was verified and what the host still needs to expose. Tokens and costs are shown only when reported; unknown is not zero. Langfuse is optional and needs a separate explicit project connection.
