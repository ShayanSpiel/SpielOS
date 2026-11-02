# SpielOS — AI Company Operating System

**Give your AI company a workspace that lasts beyond the chat.**

SpielOS is an open-source local workspace for company context, repeatable workflows and evidence-backed improvement. Work with a Director in **Codex, Claude Code or OpenCode**. Keep your strategy, brand, memory, outputs and decisions together, even when the conversation ends.

![SpielOS in Codex with the company dashboard and work tracking](docs/images/spielos-in-codex.png)

*Owner-supplied product reference: SpielOS in Codex beside a company dashboard. This company uses a custom dashboard; the screenshot's historical counts are not release benchmarks.*

## Install — one command

Requires **Python 3.11+** and **pipx** on macOS or Linux:

```sh
pipx install spielos && spielos init --dir "$HOME/my-company" -y
```

Open your company folder in your preferred host:

```sh
cd "$HOME/my-company"
spielos status
spielos report --home "$PWD"
```

In Codex, the main company chat acts as Director. In Claude Code, use `claude --agent director`; in OpenCode, select the Director agent. Review the host's hook configuration first. If automatic context is missing, use `spielos status --home "$PWD"` to restore the explicit company view.

The dashboard runs locally with authentication. Keep its access URL private. Installation creates no scheduler and connects no external service.

**Trying this source version before publication?** Registries may contain an older release. From an inspected checkout, use:

```sh
pipx install --force /absolute/path/to/SpielOS && spielos init --dir "$HOME/spielos-preview" -y
```

Keep your company home outside the product source. The npm package is a launcher for an existing Python runtime. Native Windows is not currently qualified.

## Update — one command

```sh
pipx upgrade spielos && spielos update --dir "$HOME/my-company" --keep-stale
```

This refreshes product runtime and host files in the selected company while preserving editable company content and untracked owner files. `--keep-stale` avoids pruning retired shipped files. Legacy content moves require a separate reviewed migration.

For a source installation, replace `pipx upgrade spielos` with `pipx install --force /absolute/path/to/SpielOS`.

## Start with the work you need

Tell the Director in ordinary language:

> Help me build a weekly sales report. Check the totals, use our voice, and show me a draft before anything is sent.

The Director helps agree the inputs, examples, constraints and acceptance criteria. Build a candidate, test the real implementation, review the evidence, then release the exact version. Each production Run uses a pinned release. Sending or publishing needs its own exact-action approval.

A new company includes a synthetic **sales-report draft** with an executable implementation and example cases. To pin a candidate:

```sh
spielos workflow candidate --home "$PWD" \
  --manifest "$PWD/company/workflows/sales-report/workflow.json" --json
```

Use the returned release digest with `workflow experiment`; see `spielos workflow experiment --help` and [the operating guide](company/README.md). The draft needs local qualification, verified configured telemetry and independent review before production use.

## Four ideas, one workspace

| Concept | Purpose |
| --- | --- |
| **Company** | Your shared facts, strategy, brand and boundaries |
| **Workflow** | A versioned capability with execution and evaluation contracts |
| **Run** | One bounded invocation with durable output and review |
| **Improvement** | A scoped change with observations, design and acceptance evidence |

Agents and skills implement workflows. Departments optionally group ownership. GODAE guides bounded Improvements; production does not start an autonomous Goal pursuit or self-repair loop.

Your editable files live in `company/`: profile, strategy, brand, workflows, agents and skills. Pinned runtime, private state and generated artifacts live under `.spielos/`. You keep the workspace when you switch conversations or supported hosts.

## Recorded work, real evaluations, proper experiments

**Langfuse records approved execution and evaluation evidence**: scoped inputs and outputs, supplied context, artifact provenance, criterion scores, reviewer rationale and delivery status. Local state remains the execution and approval journal. Export needs an explicitly configured destination and evidence policy; queued records stay pending until remote readback confirms them.

**Experiments run actual workflow cases against a pinned version.** Representative, held-out and negative cases map to versioned datasets, real runs and declared evaluation criteria. Comparisons retain their case and version evidence. Missing criteria cannot pass, and a high average cannot hide a blocking failure. Model judges require independently recorded calibration. A test pass or same-host judgment never substitutes for independent acceptance.

Use `/report` in configured company context, or `spielos report --home "$PWD"`, to inspect runs, memory, supplied context, usage and Langfuse delivery. Reported tokens, reference price estimates and actual billing stay separate; unavailable usage remains unknown.

## Inspect the architecture

CLI, host adapters and the optional MCP plugin use the same workflow core. Releases pin implementation and context. Company-scoped identities, execution claims and exact-action approvals make decisions attributable. Portable imports preview collisions, execute no installation code and inherit no production approval.

The current target is a **trusted local pilot**. Trusted process execution is not an untrusted-code sandbox. Enterprise isolation, shared network SQLite and untested remote deployments are outside the current claim. Activepieces preparation stays offline; live connection and activation require separate authorization.

[Operating guide](company/README.md) · [Architecture](company/ARCHITECTURE.md) · [Graph explorer](company/GRAPH.md) · [Evaluation standard](company/EVALUATION.md) · [Technical review](docs/reviews/2026-11-02-technical-review.md)

## Develop and verify

Keep owner data and credentials outside this checkout. The operational Python runtime uses the standard library; distribution building needs setuptools/build, and launcher/scenario checks also use Node.

```sh
python3 -B tools/check_source_boundary.py
python3 -B tools/sync_runtime_templates.py
python3 -B -m unittest discover -s company/tests -t .
python3 -B tools/test_acceptance.py --out /tmp/spielos-acceptance.json
```

CI is configured for macOS/Linux and Python 3.11/3.12/3.14, including an isolated installed-wheel journey. Local passes establish their tested scope, not creative quality, business impact or enterprise certification.

MIT licensed. [Source and releases](https://github.com/ShayanSpiel/SpielOS).
