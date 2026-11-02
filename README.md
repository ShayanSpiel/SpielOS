# SpielOS

<img src="company/init_templates/integrations/spielos/assets/logo.png" alt="SpielOS logo" width="96" height="96">

**Turn recurring company work into workflows you can test and improve.**

Research leads, build outbound and prepare reports with Director. Keep your company facts, strategy, brand, memory and decisions together across conversations — with a dashboard showing what actually happened.

[**Install in ChatGPT desktop / Codex →**](docs/tester-guide.md#chatgpt-and-codex) · [**Install in Claude Code →**](docs/tester-guide.md#claude-code)

![SpielOS in Codex with the company dashboard and work tracking](docs/images/spielos-in-codex.png)

*Owner-supplied reference. Historical company counts are not product benchmarks. Fresh installs show their own records and empty states.*

## Give Director a real job

> Director, build an outbound email workflow for **[ICP]**. Research fit, draft personalized emails and require review before sending.

> Build a lead research agent for **[ICP]** that cites its sources and explains each fit score.

> Turn our **[recurring report]** into a workflow. Agree the quality criteria, test real outputs and show what improved.

Director helps define the inputs, sources, permissions, examples and evaluation criteria, then builds and tests a reusable workflow. Sources and integrations are selected for your company. Nothing is sent just because a quality check passed.

## Install the plugin

Use the [official SpielOS marketplace](https://github.com/ShayanSpiel/SpielOS-Plugin). The desktop plugin includes the canonical SpielOS runtime; no separate SpielOS CLI installation or Python commands are needed from you. Setup checks the supported Python prerequisite and helps with missing software or command aliases.

### ChatGPT and Codex

Tell Codex: **“Install SpielOS from the ShayanSpiel/SpielOS-Plugin marketplace and run Setup.”** Choose your company folder. Use **Director**, **Dashboard** and **Help** from the plugin skills, or invoke `$spielos:director`, `$spielos:dashboard` and `$spielos:help`.

### Claude Code

```text
/plugin marketplace add ShayanSpiel/SpielOS-Plugin
/plugin install spielos@spielos
/spielos:setup
```

Then use `/spielos:director`, `/spielos:dashboard` and `/spielos:help`. Director is the role of your main chat; you do not need to spawn another agent.

The GitHub marketplace is the public tester distribution. A public ChatGPT or Anthropic directory listing is a separate approval process. This local runtime is for desktop execution, not ChatGPT web or Claude web.

## Your first conversation

Choose or create a company folder. Setup asks whether to **connect Langfuse now or continue locally**. Project keys go into a private local connection form, never chat. The selected project must verify before export is enabled.

Open that company as your workspace and review its hooks through your host's normal controls. After your first meaningful chat, Director shows your actual dashboard and explains how to read it:

- **Home:** current work, counts and pending decisions.
- **History & examples:** actual runs and outputs; examples remain separate evidence.
- **Quality & learning:** criteria, missing reviews, judgments and the evidence required to prove later improvement.
- **Activity & cost:** exposed token totals and measured intervals. Missing usage and actual billing stay unknown.
- **Memory, Loaded context and Langfuse delivery:** saved facts, what was actually supplied, and queued versus remotely confirmed evidence.

Meaningful chats end with a concise **Work tracked** receipt. It is Markdown in the chat, with real dashboard/trace links and review status. Installation alone trusts no hooks and creates no company.

## A portable company. Workflows that improve with evidence.

Your company stays in readable files in the folder you choose, with private state and outputs alongside it. Updating or removing the plugin does not delete that folder. Workflow implementations, context, criteria, inputs and actual outputs remain attributable to their versions.

Experiments use representative, held-out and negative cases. Local tracking, drafts and candidate experiments need no Langfuse account. The current production release policy requires verified Langfuse evidence and independent review. Passing a test alone does not prove a workflow improved or produced business impact.

The dashboard provides inspection and evidence. A complete before/after improvement scorecard is not yet implemented. Activepieces remains inactive; external sending and publishing require exact-action authorization.

[Tester guide: devices, setup, first workflow and updates](docs/tester-guide.md) · [Support](https://github.com/ShayanSpiel/SpielOS/issues)

## For technical reviewers

CLI, host adapters and MCP use one Python workflow core: Company, Workflow, Run and Improvement. Production uses pinned releases and bounded invocations, without an autonomous Goal pursuit loop. The package contains reusable software and neutral templates, never an owner's company or credentials. Source boundary, runtime parity, behavior/scenario checks, installed-wheel journeys and native-platform acceptance remain separate evidence.

This is trusted local software; enterprise isolation and untrusted-code sandboxing are not claimed. See the tester guide for prerequisites and actual platform qualification.

[Operating guide](company/README.md) · [Architecture](company/ARCHITECTURE.md) · [Evaluation standard](company/EVALUATION.md) · [Technical review](docs/reviews/2026-11-02-technical-review.md) · [Privacy](docs/plugin-privacy.md) · [Terms](docs/plugin-terms.md) · [MIT license](LICENSE)
