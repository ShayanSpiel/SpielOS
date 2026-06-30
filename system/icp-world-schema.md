# ICP World Schema

`content/.icp-world.json` is the deterministic output of the ICP World
Simulator. It is written by `tools/simulator.py write` and consumed by
the Strategist (to write the brief) and the Editor's `grounding_check`
gate (to verify the brief is grounded).

**Writer:** `tools/simulator.py write` (atomic, vault-resolved)
**Reader:** `team/strategist.md` (writes the brief), `tools/editor.py` (validates the brief)
**Reset:** `tools/post.py` deletes the file at the top of `main()` so
every `/post` run starts with a clean simulator.

## Shape

```json
{
  "reader": "One specific ICP, identity-rich, with their situation and identity tension.",
  "belief": "The OLD mental model. What the ICP currently believes. Lifted from audience.md 'stuck because' + source evidence.",
  "pain": "A vivid scene with the 5 elements: time anchor, specific action, specific failure, internal monologue, wrong attribution. The cost of the Belief.",
  "point": "The NEW mental model. Contradicts Belief. Blends offer.md 'Why it is different'.",
  "proof": [
    "<fact 1: ICP-world proof, with numbers/names/dates>",
    "<fact 2>",
    "<fact 3>"
  ],
  "meaning": "One sentence, first-person, ICP's own register. The aha. The post's close.",
  "example_pattern": "Example N (rhetorical shape — e.g. 'Example 5 (contrarian: not X but Y)')",
  "axis": "systemic | behavioral | philosophical | contrarian | leverage | human",
  "created_at": "ISO 8601 timestamp. Set by the script on write.",
  "source": "Relative path to the source (session log in session mode, topic text in topic mode). Set by the script from content/current.md frontmatter."
}
```

## Field ownership

| Field | Source | Validation |
|---|---|---|
| `reader` | `strategy/audience.md` 7 dimensions | non-empty string ≤ 1500 chars |
| `belief` | audience.md "stuck because" + source evidence | non-empty string ≤ 1500 chars |
| `pain` | source → translated to ICP language + 5-element scene | non-empty string ≤ 1500 chars |
| `point` | audience.md + offer.md "Why it is different" | non-empty string ≤ 1500 chars |
| `proof` | source 5 signal fields + offer.md "Proof" | list of 1-5 non-empty strings |
| `meaning` | 6-axis synthesis, ICP's first-person voice | non-empty string ≤ 1500 chars |
| `example_pattern` | matched to Belief→Point shape from `strategy/examples.md` | non-empty string |
| `axis` | one of: systemic, behavioral, philosophical, contrarian, leverage, human | non-empty string |
| `created_at` | set by script on write | ISO 8601 |
| `source` | set by script from `content/current.md` frontmatter | relative path or "" |

## Validation rules

`tools/simulator.py write` validates before writing. The script refuses
to write if any of these fail:

- `reader` is a non-empty string ≤ 1500 chars
- `belief` is a non-empty string ≤ 1500 chars
- `pain` is a non-empty string ≤ 1500 chars
- `point` is a non-empty string ≤ 1500 chars
- `proof` is a list of 1-5 non-empty strings
- `meaning` is a non-empty string ≤ 1500 chars
- `example_pattern` is a non-empty string ≤ 500 chars
- `axis` is one of: `systemic`, `behavioral`, `philosophical`, `contrarian`, `leverage`, `human`

`tools/simulator.py check` re-validates an existing file. The Editor's
`grounding_check` gate calls this internally to refuse briefs whose
simulator output is missing or incomplete.

## How the Strategist uses it

After `tools/simulator.py write` succeeds, the Strategist:

1. Reads the 6 fields from `content/.icp-world.json`
2. Writes them to `## Strategy` in `content/current.md`
3. Adds the Writer Instructions (`example_pattern`, `volume`, `formats`)
4. Advances to `draft`

The brief in `## Strategy` is the 6 fields + Writer Instructions. The
simulator output in `.icp-world.json` is the auditable record. Both
exist; the brief is what the Writer reads, the simulator output is what
the Editor validates.

## What this is NOT

This is **not** the brief. The brief is in `content/current.md` as
`## Strategy`. The simulator's output is the *evidence* the brief
lifts from. The brief's 6 fields (`reader`, `pain`, `belief`, `point`,
`proof`, `meaning`) are the simulator's output, formatted for the
Writer. The 2 metadata fields (`example_pattern`, `axis`) are
writer-instructions the Strategist lifts into the brief's Writer
Instructions section.

The internal labels (none in this schema — they're gone) are NEVER used
in the brief or in any draft. The `banned.regex` list in
`system/rules.yaml` enforces this in drafts.

## Topic mode

Topic mode runs the simulator identically. The source is the topic
text (provided via `/post "text"` or `/post @file:./path`), not the
session log. The simulator translates the topic into ICP language and
produces the 6 fields. The volume dial (set by the Strategist in
`## Strategy.volume`) controls how heavily the Writer leans on the
simulator's output:

- Session mode: pain=4, belief=4, point=5, proof=4, meaning=3
- Topic mode: pain=2, belief=2, point=5, proof=4, meaning=4

The user can override the per-mode defaults in `## Strategy.volume` per-run.
