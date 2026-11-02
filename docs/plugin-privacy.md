# SpielOS desktop plugin: privacy and data locations

SpielOS is an open-source desktop plugin published by Shayan Spiel. This notice describes the plugin code distributed from this repository. Your Codex or other AI host has its own data practices and terms.

## Your company workspace

You choose a company folder on your computer. SpielOS stores company files, workflow definitions, memory, run records, approvals and generated outputs there. The plugin package contains reusable software and setup instructions; it does not contain a company database or publisher credentials. The plugin does not require a SpielOS account or a publisher-hosted backend.

The host may receive the company content selected for the task, tool requests/results and artifacts you ask it to use. Treat information supplied to an AI host according to that host's privacy controls. The local dashboard is authenticated and loopback-only; its access URL is private.

Guided setup explains and prepares local activity recording: supplied context, exposed tool requests/results, final answers, reported usage and bounded same-host evaluation evidence remain in that company folder. It preserves any existing policy and respects an explicit opt-out. Hooks require ordinary host review before running. Local recording does not enable Langfuse export or collect hidden reasoning. Without a reviewed, active hook or exposed host event, capture remains incomplete.

## Optional services

External providers are separate connections. If you explicitly configure Langfuse export, the selected destination receives evidence under the approved policy. The reviewed-evidence policy can include actual scoped inputs, outputs, supplied context and evaluation rationale. Digest-only export is different. Export failures and pending delivery remain visible. Provider and AI-host processing follows their respective policies and your selected settings.

Credentials belong in private environment or company connection settings, never in this plugin, portable workflow definitions or public exports. Metadata-only Codex usage capture uses an explicitly bound chat log and retains usage metadata rather than message or reasoning bodies.

## Retention and removal

Company records persist in the selected folder. Retiring a memory keeps its evidence. Uninstalling the plugin does not delete the company folder or remotely exported records. You control local files and any separately configured provider account; removal of remote records follows that provider's controls. SpielOS does not promise that deleting a local file deletes a provider's copy.

## Support

Use the [public issue tracker](https://github.com/ShayanSpiel/SpielOS/issues) for support. Do not post private company records, access links, credentials or chat logs in public issues. GitHub handles information submitted there under its own policies.
