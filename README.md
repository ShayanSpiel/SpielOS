# SpielOS

**A markdown-driven marketing team that lives in your IDE.**

SpielOS turns one `/post` command into platform-native content for X, LinkedIn, and your blog. The team — Managing Director, Strategist, Researcher, Copywriter, Editor, Designer, Publisher, Analyst — is just `.md` files. The deterministic parts (banner design, publishing, quality gates) are tiny Python tools. Everything else is LLM-orchestrated markdown.

```
/post empty    →    builds 1 brief + 1 banner + 1 X post + 1 LinkedIn post
/post topic    →    ships an announcement without a session
```

---

## Install

One command. Any Mac/Linux. Any IDE.

```bash
curl -fsSL https://spielos.xyz/install.sh | bash
```

The installer drops a local dashboard at `http://localhost:7331`, walks you through 10 steps (Welcome → Brand → Identity → ICP → Positioning → Offer → Funnel → Voice → Methodology → Connect), writes 8 strategy files + your brand tokens, and prints `DONE!`.

Brew:

```bash
brew install spielos/tap/spiel
```

---

## After install

```bash
spiel /post empty                 # use today's session log
spiel /post "Just shipped v2"     # topic mode — ship an announcement
spiel /post @file:./notes.md      # topic mode from a file
```

The MD subagent picks the right next role, hands off via `.brief.md`, and chains the full pipeline: Researcher → Strategist → Copywriter → Designer (banner) → Editor (gates) → Publisher (Buffer) → Analyst (engagement). You get two human pauses — pick platforms, pick publish/hold/reject per draft.

Works in **opencode**, **Claude Code**, **Cursor**, and any **MCP**-compatible agent.

---

## The team

| Role | Type | Owns |
|---|---|---|
| **MD** | LLM agent | State machine, handoffs, human checkpoints |
| **Strategist** | LLM agent | Compiler, axis selection, template ranking |
| **Researcher** | LLM + tool | Session synthesis, archetype classification |
| **Copywriter** | LLM agent | Drafts, voice register, soft-gate self-check |
| **Editor** | LLM + tool | 15 mechanical gates + 14 soft gates |
| **Designer** | LLM + tool | Banner tokens, render PNG via Playwright |
| **Publisher** | LLM + tool | Buffer / X / LinkedIn / blog dispatch |
| **Analyst** | LLM + tool | Engagement pull, perf re-rank |

The state machine is one markdown table. The brief is one markdown file with role-stamped sections. No central Python orchestrator.

---

## Project structure

```
spielos/
├── team/                  # 8 role .md files (the marketing team)
├── system/                # state machine, brief schema, identity, gates, rules
│   ├── state-machine.md   # the 12-state table (single source of truth)
│   ├── brief-schema.md    # .brief.md template
│   ├── gates.md           # 15 mechanical + 14 soft gates
│   ├── rules.yaml         # mechanical config values
│   └── prompts/           # LLM-facing text per role
├── strategy/              # the 8 knowledge files (filled by wizard)
├── templates/             # X, LinkedIn, blog, session-log output shapes
├── tools/                 # deterministic tools (one per role)
│   ├── editor.py          # 15 mechanical gates (CLI)
│   ├── designer.py        # banner gen (Playwright)
│   ├── publisher/         # Buffer / X / LinkedIn / blog
│   ├── researcher.py      # session synthesis from opencode DB
│   └── analyst.py         # engagement pull + re-rank
├── content/               # sessions/, queue/, posted/, rejected/
├── install/               # install.sh, brew formula, local dashboard
│   └── wizard/            # the localhost:7331 setup wizard
├── adapters/              # auto-gen per-IDE agent files
├── bin/spiel              # the shim
└── README.md              # you are here
```

---

## Why a marketing team, not a state machine

A founder's content problem is not a content problem. It's an identity-friction problem — they have to switch from **builder mode** to **creator mode**, and the switch is what kills consistency.

A marketing team doesn't switch modes. Strategists think, copywriters write, designers make banners, publishers ship, analysts read the numbers. The builder never has to be the creator — they just have to be the MD who delegates.

SpielOS gives you 7 specialists, one handoff file, and one command. You stay a builder. The team ships the post.

---

## License

MIT
