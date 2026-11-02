# SpielOS

**Your company context, ready for the next conversation.**

Turn recurring AI work into workflows you can test and improve. SpielOS keeps your company facts, strategy, brand, memory and decisions together in a folder you control.

## Start in Codex

Install the desktop plugin and run **Set up SpielOS**. Choose an existing company folder or a new workspace, then describe the recurring job you want help with. The plugin includes its runtime; a separate SpielOS CLI installation is not needed. Local execution requires macOS/Linux and Python 3.11 or newer. Setup helps check that requirement and explains any missing prerequisite.

Try:

- “Set up a company workspace for me.”
- “Help me turn our weekly report into a tested workflow.”
- “Show my company work, memory and pending decisions.”

Choose **Director**, **Dashboard** or **Help** from the plugin's skills. In Codex you can invoke them as `$spielos:director`, `$spielos:dashboard` and `$spielos:help` (or the namespaced entries shown by your host). Director is the role of the main chat; no separate agent has to be spawned. These skills do not override Codex's built-in slash commands.

## What you get

A company workspace that lasts beyond the chat; reusable workflow definitions; real case executions and evaluations; a local dashboard for work, memory, context and reported usage; and explicit review before consequential releases or external actions.

Langfuse recording is optional and needs your selected project and evidence policy. Tests and experiments retain their actual versions and cases. A passing evaluation is distinct from proof that a workflow improved; compare baseline/candidate evidence before making that claim. The dashboard currently shows records and review status rather than a complete before/after improvement scorecard.

## Your workspace stays yours

Company files, credentials, private state and outputs stay outside the plugin package. Installation selects no company and connects no external service. Setup creates a company only after you request it and choose the folder. Updating/removing the plugin does not delete that folder. Normal host review is required for company lifecycle hooks; this package bundles no plugin hooks.

This is a trusted local tool. Independent review and verified configured evidence remain release requirements. No external-effect provider ships enabled. Native Windows, enterprise isolation and automatic improvement are not claimed.

[Source and guide](https://github.com/ShayanSpiel/SpielOS) · [Support](https://github.com/ShayanSpiel/SpielOS/issues) · [Privacy](https://github.com/ShayanSpiel/SpielOS/blob/main/docs/plugin-privacy.md) · [Terms](https://github.com/ShayanSpiel/SpielOS/blob/main/docs/plugin-terms.md)

The GitHub marketplace and private account install are separate from OpenAI universal-directory approval. Local MCP public submissions require the platform's approved-partner process.

## Dashboard, context and chat receipts

Setup explains and prepares local activity recording while preserving any existing policy. Open your selected company folder in Codex and review its company hooks using the host's normal controls. The same runtime supplies context tracking, the authenticated dashboard, bounded evaluation requests and the end-of-chat tracking receipt. Local tracking works without Langfuse; setup enables no exporter. The receipt shows actual evaluation/delivery status and reported tokens/cost, with real report/trace links where available. Unknown billing stays unknown. It is assistant-rendered Markdown, not a promise of arbitrary native rich cards.
