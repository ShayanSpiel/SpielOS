# SpielOS

**Give your AI a company to work for—and work it can get better at.**

SpielOS turns recurring business work into reusable workflows for Codex and Claude Code. Research leads, prepare reports or draft outbound campaigns with Director. Keep your company context, decisions and results together in a workspace you control.

## Install and start

Both desktop routes need Python 3.11+ available as `python3`. The plugin includes SpielOS code; you do not need to install the CLI. If Python is missing, install it from [python.org](https://www.python.org/downloads/) or your package manager and restart your host. On Windows, [check the Python alias](https://docs.python.org/3/using/windows.html#troubleshooting) if `python3` does not work.

**Codex:** paste this into your chat:

> Install SpielOS from the ShayanSpiel/SpielOS-Plugin GitHub marketplace, then run its setup.

If prompted, select **SpielOS → Setup** or enter `$spielos:setup`.

**Claude Code:** enter these commands one at a time:

```text
/plugin marketplace add ShayanSpiel/SpielOS-Plugin
/plugin install spielos@spielos
/spielos:setup
```

Choose a new company folder or an existing SpielOS company. Setup checks your prerequisites and asks whether to connect Langfuse or continue locally. Then open that company folder as your workspace and review its hooks through your host's normal controls.

## Give Director a first job

> Director, build a lead research workflow for [describe your ideal customer]. Find relevant companies, cite your sources, and explain why each one fits.

Director helps define the inputs, sources, permissions and quality criteria, then build and test the workflow. After a meaningful conversation, ask to see your dashboard: it shows actual work, pending decisions, context and available evidence. New companies start with empty records.

Use `$spielos:director`, `$spielos:dashboard` and `$spielos:help` in Codex, or `/spielos:director`, `/spielos:dashboard` and `/spielos:help` in Claude Code. Director is the role of your main chat.

Your company folder stays yours when the plugin is updated or removed. Local tracking, drafts and candidate experiments do not need Langfuse. If you connect it, enter keys in the private local form, never in chat; the selected project must verify before export. Production workflow qualification currently requires verified Langfuse evidence and independent review. Sending and publishing require separate approval for the exact action. A test pass alone does not prove improvement or business impact.

[Full guide and CLI installation](https://github.com/ShayanSpiel/SpielOS#readme) · [Tester guide](https://github.com/ShayanSpiel/SpielOS/blob/main/docs/tester-guide.md) · [Support](https://github.com/ShayanSpiel/SpielOS/issues) · [Privacy](https://github.com/ShayanSpiel/SpielOS/blob/main/docs/plugin-privacy.md) · [Terms](https://github.com/ShayanSpiel/SpielOS/blob/main/docs/plugin-terms.md)

This is trusted local software; enterprise isolation and untrusted-code sandboxing are not claimed. The manual marketplace installation supports desktop hosts with local execution, not ChatGPT web or Claude web.
