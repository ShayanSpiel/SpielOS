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
| Workgroup | Installable worker-owned capability |
| Workflow | Bounded playbook inside a Workgroup |
| Worker | Executor that performs one declared workflow |
| Skill | Reusable method a Worker follows |
| Connection | Authorized access to an external or local system |
| Artifact | Output or evidence from a run |

## Universal vocabulary

The terms above are the only public layers. The runtime owns the loop; a Workgroup supplies a capability; a Worker executes its assigned Workflow; Skills and Connections are declared inputs; Artifacts are the durable outputs.

## Pursuit semantics and alignment

A primary Goal is a durable measurable outcome. A supporting Goal is an active bottleneck. A system-improvement Goal is a bounded technical change that enables or protects an active outcome. A run, batch, task, and guardrail are not Goals. Technical acceptance proves only technical readiness, never market success.

## Workgroup contract

Workgroups are declarative packages under `workgroups/<id>/`. A Workgroup declares its metrics, Workers, and Worker workflows. A workflow declares its worksteps, evidence, skills, Connections, and explicit approval points. The shared interpreter advances the one company loop; Workgroups and Workers never create a second loop.

Install into a chosen home only after validation:

```sh
spielos workgroup validate --file workgroup.json
spielos workgroup install --file workgroup.json --dir /chosen/home
```

## Safety and system improvement

External actions always park for approval. Generated material is not business evidence. Technical-only, invalid, or contaminated evidence cannot support market conclusions.

Reusable Memory is optional and evidence-backed. It is recorded only when a run explicitly marks a claim reusable, names valid evidence, and states where it applies. Company-wide sharing is opt-in and topic-bound. Owner instructions are separate explicit directives. Strategy lives in `strategy/` and is changed only by deliberate source edits.

Source changes use a bounded system-improvement Goal with an explicit problem, allowed files, and acceptance commands. The executor records actual acceptance evidence before the change is complete.

## Home lifecycle

`spielos init --dir PATH` creates a clean self-contained home with no installed Workgroups. `spielos refresh --dir PATH` updates the runtime and host adapters while preserving strategy, assets, installed Workgroups, and `.spielos/` state.

The source checkout runs with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m company COMMAND
```

`company/init_templates/` is the shipped product. Keep its runtime spine byte-identical with `company/`.
