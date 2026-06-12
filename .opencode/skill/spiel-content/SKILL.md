# Spiel Content — Content Engine Skill

Loads the content pipeline methodology for drafting, gating, and publishing.
Use when the user says /post, "draft", "write a post", or any content creation request.

## Voice

- Lowercase i
- Short sentences, fast pacing
- Hook in first 2 lines
- Reader (ICP) is the subject
- Specific numbers
- Named reader ("founders", "builders", "operators")
- Landing line: thought, not summary

## Pipeline

1. `bash scripts/pipeline.sh post-start [topic]`
2. Read concepts/voice-and-gates.md, concepts/icp-offer.md, concepts/funnel-and-matrix.md
3. Load session from content/sessions/ or create brief
4. Run 8-step Compiler → core_insight + 6 meanings → select one
5. Draft to content/queue/ using templates/
6. `bash scripts/engine.py gates content/queue/<file>`
7. Iterate if needed

## Gates

### Mechanical (16 checks — run `scripts/engine.py gates`)
- Char count, hook presence, em-dash rule, word repeat
- Architecture leak, audience named, lesson surfaced
- Generic statement, project as subject, closing
- Frontmatter complete, dollar in note, strategy void
- ICP present, banner, grounded reference

### Creative (4-check + 10-gate — LLM judges)
- Reader's world is the subject
- Tension in first 2 lines
- Named reader present
- Last line is landing
- One ICP, problem before solution, specificity
- No architecture leaks, reader is hero, lesson surfaced
- Engagement ask, one meaning axis, no generic statements
- Grounded references

## Compiler (8-step)

1. Load ICP world
2. Simulate ICP reality
3. Load session as evidence
4. Map session → ICP world
5. Extract 6 meanings (systemic, behavioral, philosophical, contrarian, leverage, human)
6. Select one meaning axis
7. Extract single core insight
8. Generate content

## Anti-patterns

- Session as subject
- Tool-centric writing
- Architecture leaks
- Generic platitudes
- Missing reader grounding
