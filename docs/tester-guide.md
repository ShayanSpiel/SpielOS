# Try SpielOS

SpielOS is a portable company workspace for recurring AI work you can test and improve. This desktop tester preview supports Codex and Claude Code on qualified desktop systems with Python 3.11 or newer available as `python3`. Windows setup must check the actual Python alias and local filesystem; do not assume a Unix shell. The plugin carries the SpielOS runtime; no separate SpielOS installation or Langfuse account is needed.

## Install

Use the [official SpielOS marketplace](https://github.com/ShayanSpiel/SpielOS-Plugin).

## ChatGPT and Codex

**Codex:** tell it, “Install SpielOS from the ShayanSpiel/SpielOS-Plugin marketplace, then run its setup.” Choose **SpielOS → Setup** in the plugin's skills. Explicit shortcuts are `$spielos:setup`, `$spielos:director`, `$spielos:dashboard` and `$spielos:help`.

## Claude Code

**Claude Code:** enter these in the chat:

```text
/plugin marketplace add ShayanSpiel/SpielOS-Plugin
/plugin install spielos@spielos
/spielos:setup
```

Use `/spielos:director`, `/spielos:dashboard` and `/spielos:help` afterward. Reload plugins or restart the host if its command catalog still shows an older release. Claude web and Cowork are not qualified by this desktop preview.

## Set up your company

Choose an empty folder for a test company, or explicitly select an existing SpielOS company. Setup explains local activity recording, checks Python and asks whether to connect Langfuse now or continue locally. Existing settings are preserved. Keys are entered in a private local form; export is enabled only after the selected project verifies.

Open that company folder as the host's workspace. Review its project instructions and lifecycle hooks through the host's normal controls. Use `/hooks` to inspect them. New or changed hooks may need another review. Installation does not bypass trust or automatically make an unrelated chat a company session.

Director is the role of your main chat. You do not need to spawn a second agent. Ask **“Show my company work and pending decisions”**, then **“Open my dashboard.”** The report link is private to your local computer.

After the first meaningful chat, Director should open or link this company’s dashboard and explain its sections, pending evidence and unknown usage. If you deferred Langfuse, that choice should not be asked again on every message.

## A first test

1. Ask Director to inspect the company. Check the dashboard's draft workflows and confirm there is no invented production activity.
2. Give one explicit company fact or preference. Start another chat in the same company and check that relevant context can be restored. Saved memory and actually supplied context are separate records.
3. Complete a meaningful task. Expect one bounded same-host review and a concise **Work tracked** receipt after the answer. Confirm its review state, dashboard link, reported usage and unknown fields. The receipt is Markdown in the chat, not a separate native card.
4. Open **Loaded context**, **Evaluations** and **Usage** in the dashboard. Inspect named supplied documents, frozen questions, pass/fail anchors and judgment evidence. Pending reviews must remain pending until recorded. Self-review is diagnostic; it is not independent acceptance.
5. Ask to test the included synthetic sales-report workflow. Inspect representative, held-out and negative case outputs. Passing an experiment does not itself release a workflow or prove improvement over a baseline.

Token totals appear only when the host exposes attributable usage. Missing usage and billed cost stay unknown. A synthetic acceptance test is not your actual usage. Codex can import metadata from an explicitly bound session log; do not assume equivalent transcript import or reference prices for another host.

## What to expect

The product dashboard uses the same Work & learning layout as the supplied reference. A fresh company shows its own actual records and empty states, without the reference company’s gallery or history. No company-specific designs, transcripts, credentials or production records are included.

Langfuse is optional for local tracking, drafts and candidate experiments. Under the current release policy, qualifying a new production workflow requires verified Langfuse evidence and independent review. Choose the exact project and evidence policy before connecting. Confirm remote records before calling them delivered. Activepieces and other effect providers are not enabled by setup. Publishing or sending still requires authorization for the exact action and destination.

This preview provides inspection and versioned experiments. A full before/after improvement scorecard is not implemented. Native-platform qualification is recorded in release checks. Untrusted execution and enterprise isolation are not claimed.

## Updates and feedback

Ask the host to refresh the SpielOS marketplace and update the plugin. In Claude Code, use `/plugin marketplace update spielos` and `/plugin update spielos@spielos`. Company files remain in your chosen folder. Apply company-template updates explicitly from that company; changed hooks need normal review again.

For a missing command, hook, receipt or dashboard, record the host/version, plugin version, attempted step and visible error. Report it through [SpielOS issues](https://github.com/ShayanSpiel/SpielOS/issues). Redact company content, local access links and credentials. Do not submit private transcripts.
