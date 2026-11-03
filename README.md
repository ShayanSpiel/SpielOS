# SpielOS

<img src="company/init_templates/integrations/spielos/assets/logo.png" alt="SpielOS logo" width="96" height="96">

**Give your AI a company to work for—and work it can get better at.**

SpielOS turns recurring business work into reusable workflows for Codex and Claude Code. Tell Director what you need: research leads, prepare a report, or draft an outbound campaign. It helps you build and test the process while keeping your company context, decisions and results together in a workspace you control.

Your work carries across conversations. Your dashboard shows what ran, what needs review, and the evidence behind it.

![SpielOS in Codex with the company dashboard and work tracking](docs/images/spielos-in-codex.png)

*Reference image supplied by the owner; a new company starts with its own records and empty states.*

## Get started

Choose your host below. Both the plugin and CLI require **Python 3.11 or newer**. For the plugin, `python3 --version` must work; on Windows, see [Python's alias troubleshooting](https://docs.python.org/3/using/windows.html#troubleshooting). Install Python from [python.org](https://www.python.org/downloads/) or your package manager and restart your host. No separate SpielOS CLI is needed for the plugin.

### Codex desktop

1. Paste this into Codex:

   > Install SpielOS from the ShayanSpiel/SpielOS-Plugin GitHub marketplace, then run its setup.

2. If prompted, select **SpielOS → Setup** or enter `$spielos:setup`. Choose a new company folder or an existing SpielOS company. Setup checks Python and asks whether to connect Langfuse or continue locally.
3. Open that company folder as your workspace, review its hooks when prompted, and give Director your first job (see below).

This is a manual marketplace install for Codex with local execution; it is not a public ChatGPT store listing or a ChatGPT web install.

### Claude Code

1. Enter these commands one at a time in Claude Code:

   ```text
   /plugin marketplace add ShayanSpiel/SpielOS-Plugin
   /plugin install spielos@spielos
   /spielos:setup
   ```

2. Choose a new company folder or an existing SpielOS company. Setup checks Python and asks whether to connect Langfuse or continue locally.
3. Open that company folder as your workspace, review its hooks when prompted, and give Director your first job (see below).

Claude Code uses separate marketplace and install commands; the setup command starts the guided conversation. This desktop plugin is not qualified for Claude web or Cowork.

### Terminal / Python CLI

Install the CLI with [pipx](https://pipx.pypa.io/stable/installation/) and Python 3.11 or newer:

```sh
pipx install spielos
```

Create your company in a folder outside the SpielOS source checkout:

```sh
spielos init --dir ./my-company
```

Open `my-company` in Codex or Claude Code, review its hooks, and give Director your first job. The CLI creates the company and host configuration; chat activity tracking needs separate setup. Plugin setup can guide local recording and the Langfuse choice. If `spielos` is not found, run `pipx ensurepath` and restart your terminal. See the [tester guide](docs/tester-guide.md) for more help.

## Give Director your first job

Start with work you already repeat. For example:

> Director, build a lead research workflow for [describe your ideal customer]. Find relevant companies, cite your sources, and explain why each one fits.

Or try: “Turn our weekly [report] into a workflow. Help me define what a good result looks like, then test it with real examples.” Director helps you agree on inputs, sources, permissions and quality criteria before building and testing a reusable workflow. For outbound work, ask it to draft messages for your review.

After a meaningful conversation, Director can show your local dashboard and a **Work tracked** receipt with the records and usage actually available. Your new company starts empty: no activity or results are invented.

## Your company, your evidence

- **Keep context together.** Company facts, strategy, brand, scoped memory and decisions live in the folder you choose. Updating or removing the plugin does not delete it.
- **Build work you can repeat.** Save workflows and inspect their inputs, versions, outputs and evaluations.
- **See what happened.** The dashboard shows work, pending decisions, context, quality evidence and available usage. Missing usage and billing remain unknown.
- **Stay in control.** Local tracking, drafts and candidate experiments work without Langfuse. Setup offers a connection; credentials are entered in a private local form. Production qualification currently requires verified Langfuse evidence and independent review. Sending and publishing require separate approval for the exact action.

A passing test alone does not prove improvement or business impact. A complete before/after improvement scorecard is not yet implemented; Activepieces remains inactive.

## Find your way back

| What you want | Codex plugin | Claude Code plugin | CLI |
| --- | --- | --- | --- |
| Set up a company | `$spielos:setup` | `/spielos:setup` | `spielos init --dir ./my-company` |
| Work with Director | `$spielos:director` | `/spielos:director` | Open the company folder in your host |
| Open the dashboard | `$spielos:dashboard` | `/spielos:dashboard` | `spielos report --home ./my-company` |
| Get help | `$spielos:help` | `/spielos:help` | `spielos --help` |

To update the plugin, refresh its marketplace and update it in your host. For Claude Code use `/plugin marketplace update spielos`, then `/plugin update spielos@spielos`. To update the CLI, run `pipx upgrade spielos`, then run `spielos update --dir ./my-company` to refresh an existing company. Review changed hooks through your host's normal controls.

[Tester guide](docs/tester-guide.md) · [Operating guide](company/README.md) · [Architecture](company/ARCHITECTURE.md) · [Architecture maps](docs/architecture/README.md) · [Evaluation](company/EVALUATION.md) · [Support](https://github.com/ShayanSpiel/SpielOS/issues) · [Privacy](docs/plugin-privacy.md) · [Terms](docs/plugin-terms.md) · [MIT license](LICENSE)

SpielOS is trusted local software; enterprise isolation and untrusted-code sandboxing are not claimed. Platform qualification is recorded separately from local tests.
