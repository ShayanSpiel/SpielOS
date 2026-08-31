# SpielOS operating contract

SpielOS has one durable company loop:

```
GOAL → OBSERVE → DECIDE → ACT → EVALUATE
```

The runtime owns Goals, runs, approvals, evidence, work orders, notifications, and evaluation. Chat hosts are clients; closing a session does not discard company state.

## Vocabulary

| Term | Meaning |
|---|---|
| Goal | Measurable company outcome owned by the runtime |
| Department | Installable Agent-owned capability |
| Workflow | Bounded playbook inside a Department |
| Agent | Executor that performs one declared workflow |
| Skill | Reusable method an Agent follows |
| Connection | Authorized access to an external or local system |
| Artifact | Output or evidence from a run |

## Universal vocabulary

The terms above are the only public layers. The runtime owns the loop; a Department supplies a capability; an Agent executes its assigned Workflow; Skills and Connections are declared inputs; Artifacts are the durable outputs.

Legacy vocabulary is accepted only at migration and persisted-state boundaries;
new prompts, packages, commands, and output use the canonical terms above.
`company overview` returns Goals, topology health,
Departments, Agents, assignments, artifacts, and friction in one read.

## Pursuit semantics and alignment

A primary Goal is a durable measurable outcome. A supporting Goal is an active bottleneck. A system-improvement Goal is a bounded technical change that enables or protects an active outcome. A run, batch, task, and guardrail are not Goals. Technical acceptance proves only technical readiness, never market success.

## Department contract

Departments are declarative packages under `departments/<id>/`. A Department declares its metrics, Agents, and Agent workflows. A workflow declares its worksteps, evidence, skills, Connections, and explicit approval points. The shared interpreter advances the one company loop; Departments and Agents never create a second loop.

Install into a chosen home only after validation:

```sh
spielos department validate --file department.json
spielos department install --file department.json --dir /chosen/home
spielos department install --all --dir /chosen/home
```

## Safety and system improvement

External actions always park for approval. Generated material is not business evidence. Technical-only, invalid, or contaminated evidence cannot support market conclusions.

Durable knowledge is separated by authority:

- `strategy/` is the reviewed company-profile base. Typed profile overlays hold
  owner-explicit updates to identity, ICP, positioning, offers, voice, methods,
  and related strategy. A new value supersedes only the same key and scope.
- Experiment Memory comes only from the EVALUATE stage of a Goal run, after a
  reusable claim cites valid evidence and declares where it applies. Repeated
  matching outcomes reinforce it; contradictions reduce confidence.
- Workflow Memory starts as a concise procedural candidate. A direct reusable
  correction hardens immediately; otherwise the same semantic behavior key must
  appear twice within 14 days. Newer explicit corrections supersede the prior
  record without deleting provenance. Trigger and dependency fields are hard
  applicability gates. Consolidation expires stale one-off candidates.
- The host model semantically extracts typed candidates on user turns; the
  deterministic memory writer owns validation, scope, authority, identity,
  deduplication, supersession, and routing. Task/run instructions remain
  temporary, ambiguous criticism is audited but not promoted, and canonical
  Workflow defects route to source repair rather than contradictory memory.
- Goals, the control tree/support graph, work orders, approvals, and attention
  remain operational state—not semantic Memory.

The context assembler is a bounded projection, not another database. Codex runs
it at `SessionStart` and `UserPromptSubmit`; OpenCode runs it before each model
request. Boot context loads compact strategy, top Goal state, and attention.
Per-message context retrieves only relevant profile overlays, evidence-backed
learning, and Workflow instructions. Both adapters are read-only, deterministic,
and fail open. The host continues to own conversation and tool history.

Hosts resolve semantically extracted direction and corrections with `company
memory apply-candidate --candidate JSON`; explicit low-level writes remain
available through `company profile set` and `company memory observe-workflow`.
They can inspect the projection with `company context --prompt ...`. Ambiguous
comments and task-only detail are
never promoted automatically.

Source changes use a bounded system-improvement Goal with an explicit problem, allowed files, and acceptance commands. The executor records actual acceptance evidence before the change is complete.

## Artifact contract

Every generated task uses
`.spielos/artifacts/<goal>/<run>/<workflow?>/{work,final}` plus `manifest.json`.
Intermediates live in `work`; only verified outcomes live in `final`.
`company artifact finalize` records hashes and removes the canonical work folder
unless an intermediate is required evidence. After an owner-facing creative or
content task (video, image, audio, copy, document, deck, or comparable output),
the executing host presents the final path and opens the final folder. Code,
packages, archives, tests, logs, manifests, migration plans, and internal
evidence are linked but never opened unless the owner explicitly asks. The host
never opens an intermediate render directory or deletes outside canonical work.

## Friction contract

A missing or misleading tool, command, instruction, contradiction, duplicate,
unexpected result shape, or required fallback is recorded with `company friction
report`. The Director tells the owner what was expected, what happened, and the
safe fallback before continuing. Repeated fingerprints remain visible in
`company overview`; they are system-improvement evidence, not hidden retries.

## Migration contract

Migration starts in a fresh home with `company migration inspect --from PATH`
and `company migration plan --from PATH --out PLAN.json`. The current runtime
schema is authority. Foreign runtime code is replaced, unknown files are
quarantined, historical state is archived, and only owner-selected Goals with
explicit lineage enter the new active graph. Department and Workgroup normalize
to Department; Agent, Employee, and Worker normalize to Agent; playbooks become
Workflows; methods and prompts become Skills; tools, permissions, integrations,
and Workkits become Connections; outputs become Artifacts or Evidence. Each Department is converted,
validated, tested, and installed atomically with external credentials disabled.

## Home lifecycle

`spielos init --dir PATH` creates a clean self-contained home with no installed
Departments. Open OpenCode or Codex and select the Director before chatting;
fresh state is injected automatically. After installing a newer SpielOS
release, `spielos update --dir PATH` replaces the runtime and host adapters
while preserving strategy, assets, installed Departments, configuration, and
`.spielos/` state. `spielos refresh` remains a compatibility alias.

The source checkout runs with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company COMMAND
```

`company/init_templates/` is the shipped product. Keep its runtime spine byte-identical with `company/`.
