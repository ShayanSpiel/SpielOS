# SpielOS

**Your company context, ready for the next conversation.**

SpielOS gives recurring AI work a lasting home. Keep your company facts, strategy, brand, workflows and decisions together. Build a workflow, test real outputs, and review the evidence before relying on it.

![SpielOS in Codex with the company dashboard and work tracking](docs/images/spielos-in-codex.png)

*SpielOS in Codex beside a company dashboard. Owner-supplied reference; this company uses a custom dashboard. Historical counts are not release benchmarks.*

## Start with the plugin

[**Get SpielOS for Codex & Claude Code →**](https://github.com/ShayanSpiel/SpielOS-Plugin)

Tell Codex:

> Install SpielOS from the ShayanSpiel/SpielOS-Plugin marketplace and run its setup.

Then choose a company folder and tell it the work you want help with. The plugin carries the SpielOS runtime, so you do not need to install a separate SpielOS CLI or copy Python commands. Desktop execution requires macOS/Linux and Python 3.11 or newer; setup checks for a supported interpreter and helps explain missing prerequisites.

Use **Director** to operate your company, **Dashboard** to see its work, or **Help** for the available actions. In Codex, choose these from the plugin's skills or type `$spielos:director`, `$spielos:dashboard` or `$spielos:help`. Director is the role of your main chat. Plugin skills do not replace Codex's built-in slash commands.

**Claude Code:** use `/plugin marketplace add ShayanSpiel/SpielOS-Plugin`, then `/plugin install spielos@spielos` and `/spielos:setup`. Use `/spielos:director`, `/spielos:dashboard` and `/spielos:help` afterward.

[Tester guide: install, first workflow, hooks, receipts and updates](docs/tester-guide.md)

Distribution is through the public GitHub marketplace. An OpenAI universal-directory listing is a separate review process; it is not implied by marketplace availability.

## Start with a job you already do

> Help me build our weekly sales report. Check the totals, use our company voice, and show me a draft before anything is sent.

SpielOS helps turn that request into a reusable workflow with agreed inputs, examples and evaluation criteria. Test the actual implementation, inspect its failures, and review the exact version before release. A new company includes a synthetic sales-report draft you can use to explore the process.

Or ask:

- “Show my company work and pending decisions.”
- “What context and memory were supplied for this task?”
- “Test this candidate and show which cases failed.”
- “Open my company dashboard.”

## Two things that belong together

**A portable company workspace.** Company context stays in readable files, with private run records and outputs in the selected company folder. Keep the workspace when you start another conversation or move between supported hosts. Agents and skills are reusable ways to implement the work.

**Workflows you can test and improve.** Retain the implementation, context, criteria, inputs and actual outputs for each version. Compare real baseline and candidate evidence before claiming improvement. A passing test means its acceptance criteria were met; it does not by itself establish better business results.

The user-facing journey is simple: **choose your company → build or use a workflow → test and review the result.** The runtime keeps the evidence behind it.

## Dashboard, context and chat receipts

The local dashboard shows workflows, actual runs, memory, supplied context, reported usage and pending decisions. It stays authenticated on your computer. Keep its access link private.

Setup explains and prepares private local activity recording. Open the selected company folder in Codex and review its shipped hooks. They restore relevant context, capture supplied-context evidence and request bounded evaluations. Meaningful chats end with a concise tracking receipt: evaluation and delivery status, dashboard/trace links and actual exposed token/cost information. Host-rendered Markdown is the supported baseline; missing usage or billing remains unknown. Local tracking works without a Langfuse account; no exporter is connected by setup.

**Langfuse recording** is optional for local tracking, drafts and experiments. The current runtime requires verified Langfuse evidence and independent review to qualify a new production workflow release. Recording retains approved execution and evaluation evidence: scoped inputs/outputs, artifact provenance, criteria and reviewer rationale. Experiments run representative, held-out and negative cases against pinned versions. Pending export remains pending until remote readback confirms it. Reported tokens, reference price estimates and actual billing remain distinct.

The current dashboard is an inspection view. A complete workflow before/after improvement scorecard is not yet implemented. We do not manufacture improvement percentages or business impact from activity counts.

## Your company stays yours

The plugin contains reusable software, not your company. Setup asks which folder to use; installation alone creates no company and connects no external provider. Plugin updates and removal do not delete the company folder. Sending and publishing need separate authorization for the exact action, destination and content.

SpielOS is open source under MIT. The current target is trusted local use on macOS/Linux. Local process execution is not an untrusted-code sandbox. Native Windows, enterprise isolation and automatic self-improvement are not claimed. Activepieces preparation remains offline.

## For technical reviewers

CLI, host adapters and the optional MCP interface share one workflow core. Company, Workflow, Run and Improvement are its durable concepts. Production uses pinned releases; it does not start an autonomous Goal pursuit. Qualified releases require the configured evaluation evidence and independent review.

The Python runtime uses the standard library. The desktop plugin bundles the same source and neutral installation templates. Build outputs and synthetic acceptance homes stay outside this checkout; owner data and credentials never belong here.

[Operating guide](company/README.md) · [Architecture](company/ARCHITECTURE.md) · [Evaluation standard](company/EVALUATION.md) · [Technical review](docs/reviews/2026-11-02-technical-review.md) · [CI repair evidence](docs/reviews/2026-11-02-ci-repair.md)

[Support](https://github.com/ShayanSpiel/SpielOS/issues) · [Plugin privacy](docs/plugin-privacy.md) · [Plugin terms](docs/plugin-terms.md) · [MIT license](LICENSE)
