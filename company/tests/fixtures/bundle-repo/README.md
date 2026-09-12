# research_briefs Department — a portable SpielOS Department bundle

This folder is a complete Department bundle for
[SpielOS](https://spielos.xyz): the `research_briefs` Department (v1.0.0),
its full dependency closure (skills, capabilities, connections, installed
agents, strategy documents), and this onboarding README. Import it into a
SpielOS home and the Department is immediately live in the Goal loop.

## What is inside

| Path | Contents |
|---|---|
| `bundle.json` | manifest: identity, version, spine pin, closure file list |
| `departments/research_briefs/` | the Department declaration package |
| `skills/`, `capabilities/`, `connections/`, `strategy/` | the dependency closure |
| `agents/installed/` | installed Agent declarations the closure needs |

Everything installs into the six owner layers of your home
(`.agents/company/departments`, `skills`, `capabilities`, `connections`,
`strategy`, `agents/installed`). Your vendored spine, host adapters, and
settings are never touched, and re-importing only refreshes bundle-owned
files.

## Step 1 — get this folder onto your machine

Clone the repository (recommended), or download and unzip it:

```sh
git clone <this-repository-url> research_briefs-bundle
```

Any local folder works; the import reads the folder you cloned or
unzipped — nothing is fetched over the network at import time.

## Step 2 — one shell command imports it

From your SpielOS home (the folder that contains `.agents/` and
`.spielos/`), run the import once:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company import /absolute/path/to/this/folder
```

The command validates the manifest, the spine pin, the dependency
closure, and the declaration against your home's live contracts, then
installs the bundle into your owner layers and prints a receipt. It is
idempotent: running it again refreshes bundle-owned files only.

## Step 3 — or just paste this prompt to your Director

No command needed: paste the block for your host and the Director does
the import through the goal loop. The folder path is the only input.

### OpenCode

Run `/agents`, select the **Director** agent, and paste:

```text
Please install the research_briefs Department into my company from the bundle repository folder I placed at the path below. Import it through the goal loop: create one bounded goal for the import, run the import command against that folder path, and record the import receipt as evidence before completing the goal. The command to run is
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company import <ABSOLUTE_PATH_TO_THIS_FOLDER>
(pass the absolute path of the folder holding this README — the research_briefs bundle, version 1.0.0.) After the import, tell me which workflows the Department declares and what goal I should create to put it to work.
```

### Codex

Talk to the **Director** agent and paste the same prompt:

```text
Please install the research_briefs Department into my company from the bundle repository folder I placed at the path below. Import it through the goal loop: create one bounded goal for the import, run the import command against that folder path, and record the import receipt as evidence before completing the goal. The command to run is
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company import <ABSOLUTE_PATH_TO_THIS_FOLDER>
(pass the absolute path of the folder holding this README — the research_briefs bundle, version 1.0.0.) After the import, tell me which workflows the Department declares and what goal I should create to put it to work.
```

### Claude Code

Run `claude --agent director` (or just `claude`) and paste the same
prompt:

```text
Please install the research_briefs Department into my company from the bundle repository folder I placed at the path below. Import it through the goal loop: create one bounded goal for the import, run the import command against that folder path, and record the import receipt as evidence before completing the goal. The command to run is
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.agents python3 -B -m company import <ABSOLUTE_PATH_TO_THIS_FOLDER>
(pass the absolute path of the folder holding this README — the research_briefs bundle, version 1.0.0.) After the import, tell me which workflows the Department declares and what goal I should create to put it to work.
```

## After the import

- `company departments` lists `research_briefs` with its workflows.
- `company catalog` shows the workflows it declares.
- Create a goal on one of its metrics and the loop runs end to end:
  `company goal create --name "..." --owner research_briefs --metric <declared metric> --target ...`

If the import reports a spine pin mismatch, upgrade your home first
(`spielos update`) and re-import; the message names the exact repair.
