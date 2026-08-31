---
name: migration-planning
description: Plan or execute safe migration of existing projects, files, websites, workflows, templates, agents, Departments, integrations, and assets into current SpielOS abstractions. Use for any source layout; planning never authorizes execution.
---

# SpielOS Migration Planning

Preserve the owner's useful system while translating and improving it for the
current SpielOS schema. A source may be an older SpielOS home or any collection
of repositories, files, workflows, prompts, templates, galleries, applications,
integrations, and assets.

## Preserve scope and authority

Separate three authorities:

1. read-only discovery;
2. writing a migration plan;
3. executing transformations, copying secrets, installing, deploying, or
   calling external services.

Authorization for one does not imply the next. If the owner asks only for a
plan, inspect read-only and write only the requested plan artifact. Do not copy,
move, rename, rewrite, delete, install, activate, publish, deploy, or test live
connections. Treat source projects as protected unless the owner explicitly
authorizes mutation.

Do not assume a named source exists. Resolve its exact path or URL first. When
it cannot be found, state that plainly and make source resolution the first
gate; never fabricate an inventory.

## Suggest migration without hijacking onboarding

When company state has no active Goal, make a short optional suggestion: if the
owner already has useful work elsewhere, it can be inventoried and migrated.
Then return to the owner's intent. Do not turn every fresh-home conversation
into a questionnaire or create a Goal merely to discuss migration.

Recognize ordinary owner language such as “my workflow is here,” “the templates
are in that folder,” or “our website is in another repo.” Ask only for the exact
source when it cannot be discovered safely.

## Build a lossless inventory before designing

Inventory every source item with path, hash, classification, sensitivity,
relationships, proposed destination, disposition, and acceptance check. Cover
website code and content, operational instructions, workflows, templates,
galleries, assets, integrations, automation, and environment-key references.

Every item must end as transformed, copied, provenance-merged, quarantined, or
explicitly excluded as generated material. Unknown and contradictory files are
visible blockers, not permission to guess or discard. Reconcile ledger entries
plus explicit exclusions to the complete source file count.

Inspect likely secret-bearing files without exposing values. Record key names
and consumers only. Never put a secret value in a plan, prompt, log, evidence,
artifact manifest, or tracked file.

## Translate into current abstractions

- Department or Workgroup becomes a Department package.
- Agent, Employee, or Worker becomes an Agent.
- Playbook or process becomes a Workflow.
- Prompt, method, or skill becomes a Skill.
- Tool, permission, integration, Workkit, or connection becomes a Connection.
- Output becomes an Artifact and, when evaluative, typed Evidence.
- A website or application remains a separate application migration unit.
- Foreign runtime files are replaced by the current spine, never merged into it.

Goals are owner-scoped migration data, not an automatic import.
If the owner excludes Goals, omit them completely—including active graph, run state,
and historical Goal records—and record that exclusion in acceptance.

## Improve, do not blindly copy

For each proposed Department, establish purpose, boundaries, relevant metrics,
version, provenance, Agents, Agent-owned Workflows, Skills, Connections,
artifacts, evidence, and approvals. Consolidate genuine duplication only while
retaining source traceability. Resolve contradictions deliberately. Split roles
when responsibilities or permissions differ.

For each Workflow, define accountable Agent, trigger, preconditions, inputs,
ordered worksteps, Skills, Connections, artifacts, evidence, approvals,
failure behavior, and upstream/downstream relationships. Preserve valuable
domain detail, examples, tone, templates, galleries, and assets.

Model every connection by service, purpose, consumers, environment-key names,
least-privilege scope, mutation risk, approval boundary, and safe validation.
Keep credentials disabled until their consuming unit passes its contracts.

## Plan applications separately

For a website or application, preserve source, routes, content, assets,
templates, galleries, SEO, analytics, redirects, integrations, manifests,
lockfiles, and deployment configuration. Exclude dependency folders, build
output, caches, foreign `.git`, foreign runtime/host folders, state databases,
and secret files. Merge manifests deliberately, install dependencies fresh,
and require build, route, asset, metadata, analytics, and form checks. Deployment
always remains a separate external approval.

## Execution shape

When execution is authorized, use a fresh destination and transform one
Department at a time. Validate each unit before activating the next. Keep the
application as its own unit. Produce conversion receipts that map every source
file to destination files and decisions. Stop on missing source identity,
unresolved secrets, unexplained omissions, contradictions, or failed evidence.

Use `company migration inspect --from PATH` and `company migration plan --from
PATH --out PLAN.json` when available for read-only assistance. Their output is
an input to the complete ledger and judgment process, not proof of completeness.

Completion requires source identity, 100% ledger reconciliation, abstraction
validation, relationship integrity, secret redaction, dry-run evidence, and a
reversible destination history. Never claim migration complete from file counts
or a successful build alone.
