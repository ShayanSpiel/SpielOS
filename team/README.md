# Team

The marketing team. One `.md` file per role. Each role is a subagent that:

1. Reads the previous role's section in `.brief.md` (the handoff file).
2. Reads its own playbook files (listed in each role's frontmatter).
3. Writes its own section in `.brief.md`.
4. Appends the next state to `## state_history`.
5. Returns.

MD is special — it owns the state machine, runs the human checkpoints, and chains the other 7.

## Roster

| Role | File | Owns |
|---|---|---|
| **MD** | [`md.md`](./md.md) | State machine, handoffs, human checkpoints, IDLE/COMPLETE_POST |
| **Strategist** | [`strategist.md`](./strategist.md) | Compiler, axis selection, template ranking (COMPILE, SELECT) |
| **Researcher** | [`researcher.md`](./researcher.md) | Session synthesis, archetype classification (SESSION_CAPTURE) |
| **Copywriter** | [`copywriter.md`](./copywriter.md) | Drafts, voice register, soft-gate self-check (DRAFTING) |
| **Editor** | [`editor.md`](./editor.md) | 15 mechanical gates + 14 soft gates (GATE_CHECK) |
| **Designer** | [`designer.md`](./designer.md) | Banner tokens, render PNG via `tools/designer.py` (BANNER) |
| **Publisher** | [`publisher.md`](./publisher.md) | Buffer / X / LinkedIn / blog dispatch (PUBLISHING) |
| **Analyst** | [`analyst.md`](./analyst.md) | Engagement pull, perf re-rank (ANALYZING_POST) |

## Hand-off order

```
IDLE
  ↓
Researcher    (SESSION_CAPTURE)
  ↓
Strategist    (COMPILE)
  ↓
Strategist    (SELECT)
  ↓
MD            (FORMAT_WIZARD, human)
  ↓
Copywriter    (DRAFTING)
  ↓
Designer      (BANNER)
  ↓
Editor        (GATE_CHECK)
  ↓
MD            (PUBLISH_REVIEW, human)
  ↓
Publisher     (PUBLISHING)
  ↓
Analyst       (ANALYZING_POST)
  ↓
MD            (COMPLETE_POST)
  ↓
IDLE
```

## Communication protocol

Every role reads the previous role's section in `.brief.md` and writes its own. There is no other communication channel.

The state machine in `system/state-machine.md` is the single source of truth for the order. MD reads it; nobody else needs to.

## Why a team, not a state machine

A founder's content problem is an identity-friction problem. They have to switch from builder mode to creator mode. The switch is what kills consistency.

A marketing team doesn't switch modes. Strategists think, copywriters write, designers make banners, publishers ship, analysts read the numbers. The MD delegates. The builder stays a builder.
