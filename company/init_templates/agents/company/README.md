# SpielOS operating contract

SpielOS has one durable company loop:

```
GOAL → OBSERVE → DECIDE → ACT → EVALUATE
```

The Goal runtime owns the adaptive control loop and scheduler. Goals, Resolution,
Workflows, WorkOrders, Evidence, and Memory own their persistence over one SQLite
database. Chat hosts are clients; closing a session does not discard state.

## Vocabulary

| Term | Meaning |
|---|---|
| Goal | Measurable company outcome owned by the runtime |
| Department | Installable Agent-owned capability |
| Workflow | Bounded playbook inside a Department |
| WorkOrder | Durable exact unit of work created by Resolution |
| Agent | Replaceable executor that performs a WorkOrder |
| Skill | Reusable method an Agent follows |
| Connection | Authorized access to an external or local system |
| Artifact | Output or evidence from a run |

## Universal vocabulary

The terms above are the public layers. The runtime owns the Goal loop; Resolution
owns execution; a Department supplies capability; an Agent executes a WorkOrder;
Skills and Connections are declared inputs; Artifacts are durable outputs.

Legacy vocabulary is accepted only at migration and persisted-state boundaries;
new prompts, packages, commands, and output use the canonical terms above.
`company overview` returns Goals, topology health,
Departments, Agents, assignments, artifacts, and friction in one read.

`company observatory` opens the read-only living-system view. The default canvas
places the Goal tree and support DAG above the active loop, Resolution work, and
the source-owned architecture layers. Focused views expose Workflows, Memory,
Evidence, code dependencies, and coherence findings. When a persisted home has
not yet migrated, the observer labels its historical state as an isolated
compatibility boundary; it never merges those records into clean-core state.

## Pursuit semantics and alignment

A Goal is one measurable outcome. `parent_id` forms the human organizational
tree; `supports` edges form a separate acyclic causal graph. There are no Goal
subclasses. Each Run is one adaptive OBSERVE → DECIDE → ACT → EVALUATE
iteration. ACT creates an Intervention; execution, creation, repair, retry, and
validation stay inside that Intervention's Resolution cycle.

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

Repairs and source changes are Resolution work beneath the active Goal they
serve. They retain Goal → Run → Intervention lineage and actual acceptance
evidence. If no relevant Goal is clear—or several are genuinely ambiguous—the
runtime asks the owner instead of inventing a technical Goal.

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
`company overview`; they are Resolution evidence, not hidden retries.

## Migration contract

Migration starts in a fresh home with `company migration inspect --from PATH`
and `company migration plan --from PATH --out PLAN.json`. The current runtime
schema is authority. Foreign runtime code is replaced, unknown files are
quarantined, historical state is archived, and only owner-selected Goals with
explicit lineage enter the new active graph. Foreign capability, executor,
playbook, method, access, and output aliases normalize at this boundary to
Department, Agent, Workflow, Skill, Connection, Artifact, or Evidence. Each Department is converted,
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
