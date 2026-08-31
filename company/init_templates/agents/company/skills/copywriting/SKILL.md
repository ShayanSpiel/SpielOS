---
name: copywriting
description: Generate and adapt business content from structured context, evidence, goals, and output constraints.
---

# Copywriting

Read relevant context from:

- `.agents/company/strategy/icp.md`
- `.agents/company/strategy/positioning.md`
- `.agents/company/strategy/voice.md`

Generate from:

**state + task + evidence + constraints + output → content**

Rules:

- Unknown stays unknown.
- Inference stays inference.
- Hypothetical stays hypothetical.
- Never invent people, scenes, customers, quotes, metrics, results, events, tools, or capabilities.
- Never generate a fictional world to reason from.
- Use only context relevant to the task.
- Select the claims and relationships needed to accomplish the goal.
- Let structure emerge from the subject, audience, mode, and artifact.
- Do not force hooks, stories, CTAs, problem/solution formulas, or platform formulas.
- Platform changes presentation, not truth.
- Use concrete language only when concrete information exists.
- Preserve one main idea unless the task requires more.
- Video scenario = what is seen.
- Narration = what is said.
- Demo narration must follow demonstrated behavior.
- Case studies require verified evidence.

Optimize for:

**truth → task → audience → coherence → clarity → voice → platform → brevity**

Before returning:

- remove unsupported specificity
- verify claims against evidence
- verify claim strength did not increase
- verify no unknown was silently filled
- remove filler and repetition

Return finished content unless structured output is requested.
