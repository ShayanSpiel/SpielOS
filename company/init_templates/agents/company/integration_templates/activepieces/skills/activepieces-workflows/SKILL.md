---
name: activepieces-workflows
description: Design, build, inspect and improve Activepieces flows using its official MCP server, with execution contracts and evaluation cases. Use for Activepieces workflow work or preparing its connection; preparation alone never authorizes connecting, testing, publishing or enabling flows.
---

Use Activepieces' built-in project MCP server. Do not create a competing wrapper or guess action names, properties, connections, sample data or successful runs. Distinguish preparing a connection, creating a draft, testing it and enabling live execution.

If the owner says to prepare but not use Activepieces, work offline: maintain this skill, connection template and acceptance brief. Do not open OAuth, enable the server, discover live tools, create flows, run tests or publish. A later explicit instruction to use Activepieces lifts that temporary hold for its named task; it is not a permanent product restriction.

For connection preparation read [connection.md](references/connection.md). For actual workflow work read [building.md](references/building.md), then discover current tool names and schemas in the connected client. The documented catalog is a guide, not evidence that a selected deployment exposes those tools.

Use bounded GODAE:

- Goal: agree the useful output, accountable owner, business outcome window, baseline or explicit unknown, permissions and spending bounds.
- Observe: inspect the actual process and existing flow before changes. Collect representative inputs, a good reference output, held-out cases and unacceptable outputs. Keep artifact quality separate from downstream business impact.
- Decide: select a simple provider-native graph and design execution plus evaluation around the same stable criterion identities. Explain data mappings, side effects, timeout, retry/replay handling, costs and recovery.
- Act: build a disabled draft within the authorized scope. Validate structure and configuration before any authorized tests. Inspect real outputs; rendered media needs visual inspection. An API success or green run status alone does not establish quality.
- Evaluate: compare each case/criterion with its reference and rating anchors; retain explanations and artifact digests. Empty/duplicate/missing coverage fails release. Record accept, revise or reject with the actual reviewer and exact flow version.

Review the acceptance brief and architecture, then the candidate release; add intermediate owner interruptions only for a real decision, permission boundary or explicit policy. Do not infer causal strategy from a flat metric or promote repeated work automatically.

Keep provider execution and SpielOS evaluation records linked by flow/version/run identities and stable request identity. The remote platform owns its internal graph and scheduling. A published provider version is different from a reviewed SpielOS release; a completed run is different from an accepted output. Record measured, estimated or unknown usage/cost, including evaluator and retry cost. Never invent tokens or costs.

Draft creation is not publication approval. Publishing, enabling, scheduling, sending or rerunning a flow with effects requires authorization for the exact version, action, destination, content and scope. A test can send real messages or incur charges. Check the selected test's effects before running it. After an ambiguous response inspect flow/run state; never blindly repeat creation, publishing or an external action. Do not automatically switch providers or broaden permissions when a tool is missing.
