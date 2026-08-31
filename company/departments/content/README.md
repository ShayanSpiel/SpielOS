# Content Department

Content owns the customer idea and copy. It reads the canonical strategy and copywriting skill, then hands the campaign Artifact to Design. It does not own templates, rendering, media, or brand strategy.

## Workflow contract

Campaign work runs:

`simulation -> human_reality -> discovery -> draft -> platform_edit -> quality_gate -> render_handoff -> approve -> dispatch`

- Simulation records the reader, situation, mechanism, consequence, proof, and discovery before any copy.
- Human reality preserves the scene: what the person checks, copies, switches between, waits for, fixes, and remembers.
- Discovery adds the derived insight without replacing or compressing the simulation or human reality.
- Draft requires the simulation, human reality, and discovery as separate inputs. Its first paragraph comes from the preserved scene.
- Platform edit receives the draft plus both scene artifacts. It may change length, pacing, and formatting, but not rewrite the argument into a generic hook, explanation, proof, and CTA sequence.
- The quality gate validates the campaign contract and passing eval reports. Design then renders without changing the copy's substance.
- Approval and Buffer dispatch keep their existing evidence and receipt contracts.

## Boundaries

- Canonical ICP, positioning, and voice live in `.agents/company/strategy/`.
- Copy method lives in `.agents/company/skills/copywriting/SKILL.md`; Persian language adaptation lives in `.agents/company/skills/translation-fa/SKILL.md`.
- `evals.py` contains criterion IDs, thresholds, and source references only.
- Templates, registry files, connections, public routes, artifact kinds, daily targets, and existing workflow names remain unchanged.
- Generated artifacts belong under `.spielos/artifacts/`.
