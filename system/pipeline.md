# Pipeline

The content pipeline is a 12-state machine, executed by 8 roles, coordinated by **MD**.

```
                        ┌──── human pause (FORMAT_WIZARD)
                        │
                        ▼
IDLE → SESSION_CAPTURE → COMPILE → SELECT ─→ MD ─→ DRAFTING → BANNER
                                                              │
                                                              ▼
                              IDLE ←─ MD (held)  ←─ PUBLISH_REVIEW
                                ▲                                │
                                │ human pause                    ▼
                                └──── IDLE  ←── MD (rejected)  PUBLISHING
                                                                │
                                                                ▼
                                                       ANALYZING_POST
                                                                │
                                                                ▼
                                                       COMPLETE_POST
                                                                │
                                                                ▼
                                                              IDLE
```

## The roles, in order

| # | State | Role | Type | Output |
|---|---|---|---|---|
| 0 | IDLE | **MD** | LLM | empty brief |
| 1 | SESSION_CAPTURE | **Researcher** | LLM + tool | `## researcher` |
| 2 | COMPILE | **Strategist** | LLM | `## strategist.core_insight` + 6 axes |
| 3 | SELECT | **Strategist** | LLM | `## strategist.template_selection` |
| 4 | FORMAT_WIZARD | **MD** (human) | LLM + human | `formats: [...]` |
| 5 | DRAFTING | **Copywriter** | LLM | `## copywriter` + draft files |
| 6 | BANNER | **Designer** | LLM + `tools/designer.py` | `## designer` + PNG files |
| 7 | GATE_CHECK | **Editor** | LLM + `tools/editor.py` | `## editor.verdict` |
| 8 | PUBLISH_REVIEW | **MD** (human) | LLM + human | `## publisher.posted` (when publish) |
| 9 | PUBLISHING | **Publisher** | LLM + `tools/publisher/*.py` | `## publisher` |
| 10 | ANALYZING_POST | **Analyst** | LLM + `tools/analyst.py` | `## analyst` |
| 11 | COMPLETE_POST | **MD** | LLM | `.brief.md` archived |

---

## Hand-off graph

```
MD ──starts──→ Researcher ──reads session log + ICP──→ Strategist
                                                        │
                                            reads templates + corpus
                                                        │
                                                        ▼
                                                     Copywriter
                                                        │
                                                      writes drafts
                                                        │
                                                        ▼
                                                     Designer
                                                        │
                                                   calls designer.py
                                                        │
                                                        ▼
                                                      Editor
                                                        │
                                                   calls editor.py
                                                        │
                                                        ▼
                                                       MD
                                                        │
                                                  human reviews
                                                        │
                                                        ▼
                                                    Publisher
                                                        │
                                                  calls publisher
                                                        │
                                                        ▼
                                                     Analyst
                                                        │
                                                   calls analyst
                                                        │
                                                        ▼
                                                       MD
                                                        │
                                                  archives brief
                                                        │
                                                        ▼
                                                      IDLE
```

---

## File I/O per state

| State | Reads | Writes |
|---|---|---|
| IDLE | (nothing) | `content/.brief.md` (skeleton) |
| SESSION_CAPTURE | `content/sessions/*.md` OR `topic text` | `## researcher` |
| COMPILE | `## researcher`, `system/prompts/compiler.md`, `strategy/icp.md` | `## strategist.core_insight` + `## strategist.meanings` |
| SELECT | `## strategist`, `templates/registry/viral-templates.yaml` | `## strategist.template_selection` |
| FORMAT_WIZARD | `## strategist` | `formats: [...]` |
| DRAFTING | `## strategist`, `## researcher`, `strategy/voice.md`, `strategy/corpus.md`, `templates/<platform>.md` | `## copywriter` + `content/queue/*.md` |
| BANNER | `## copywriter` | `## designer` + `assets/banners/*.png` + `banner:` frontmatter |
| GATE_CHECK | drafts in `content/queue/` | `## editor` + `gates:` frontmatter |
| PUBLISH_REVIEW | drafts + `## editor` | `publish_decisions` |
| PUBLISHING | `publish_decisions` | `## publisher` + `content/posted/*.md` |
| ANALYZING_POST | `## publisher.posted` | `## analyst` + `templates/registry/performance.json` |
| COMPLETE_POST | `content/.brief.md` | rename to `content/.brief/YYYY-MM-DD-NNN.md` |

---

## Where the deterministic parts run

- `tools/researcher.py` — synthesizes a session log from the opencode DB when `/post empty` finds no session.
- `tools/designer.py` — renders PNG banners (Playwright + system Chrome).
- `tools/editor.py` — runs the 15 mechanical gates against each draft.
- `tools/publisher/buffer.py` — multi-platform fan-out (X + LinkedIn + Threads).
- `tools/publisher/twitter.py` — direct X API fallback.
- `tools/publisher/linkedin.py` — direct LinkedIn UGC API fallback.
- `tools/publisher/blog.sh` — GH Pages deploy.
- `tools/analyst.py` — pulls Buffer engagement, updates perf.json, re-ranks viral-templates.yaml.

All other work is the LLM, reading the brief and writing to the brief.
