"""Design Department — clean migrated declaration (legacy v3.4.0 → clean core).

Migration notes (2026-09-03):
- Legacy validation functions (rotation rules, template fit, render
  reports) moved to ``design/gates.py`` as pure functions over the shared
  ``departments/campaign_contract.py``.
- Templates (registry, social, video), system CSS, presets, and the three
  video eval suites ported in place — the gallery is the source of truth.
- The ``video-producer`` agent is shared with the content department
  (already migrated); ``designer`` is new here.
"""

from __future__ import annotations

from ...workflows import Workflow, WorkflowStep


def _step(step_id: str, agent_id: str, instruction: str, *,
          evidence_kind: str | None = None, approval_key: str | None = None,
          skill_ids: tuple[str, ...] = (), connection_ids: tuple[str, ...] = (),
          requirements: dict | None = None) -> WorkflowStep:
    return WorkflowStep(
        id=step_id, agent_id=agent_id, instruction=instruction,
        evidence_kind=evidence_kind, approval_key=approval_key,
        skill_ids=skill_ids, connection_ids=connection_ids,
        requirements=requirements or {})


class DesignDepartment:
    """Declarative design capability; execution belongs to GoalRuntime."""

    department_id = "design"
    id = "design"
    version = "3.5.0"
    description = (
        "Consumes a shared campaign Artifact and returns verified renditions "
        "whose spoken text, displayed copy, components, icons, labels, "
        "timing, and evidence remain controlled by that one campaign "
        "identity."
    )
    agent_ids = ("designer", "video-producer")
    production_ready = True

    workflows = (
        Workflow(
            "social-visual",
            "Render a focused platform-ready social graphic.",
            (
                _step("idea_lock", "designer",
                      "Lock the one idea and its reader moment for the graphic.",
                      skill_ids=("spielos-ui",)),
                _step("brief", "designer",
                      "Write the design brief (template archetype, copy "
                      "slots, semantic tokens).",
                      evidence_kind="design_brief",
                      skill_ids=("spielos-ui",)),
                _step("compose", "designer",
                      "Compose the visual from a registered archetype in the "
                      "templates registry (never legacy fallback).",
                      skill_ids=("spielos-ui",)),
                _step("render", "designer",
                      "Render the platform-ready asset at its size preset.",
                      evidence_kind="approved_design",
                      skill_ids=("spielos-ui",)),
                _step("qa", "designer",
                      "Visual QA against the design system and record "
                      "evidence {'approved_design': {...}}.",
                      skill_ids=("spielos-ui",)),
            ),
            department_id="design",
        ),
        Workflow(
            "rendition-pack",
            "Render every typed campaign rendition without owning or "
            "duplicating campaign strategy.",
            (
                _step("accept_design_order", "designer",
                      "Accept the design order via design/gates.py "
                      "accept_design_order (strategy-phase Artifact, "
                      "rotation rules enforced: registry membership, no "
                      "batch repeats, round-robin balance, bounded cell "
                      "balance).",
                      evidence_kind="design_order",
                      skill_ids=("spielos-ui",),
                      requirements={"gate": "gates.accept_design_order"}),
                _step("compose", "designer",
                      "Compose every item/platform rendition from its "
                      "declared template.",
                      skill_ids=("spielos-ui",)),
                _step("render_sizes", "designer",
                      "Render every rendition at its platform size preset "
                      "(threads-portrait / youtube-shorts) and record the "
                      "render report via gates.render_report.",
                      evidence_kind="render_report",
                      skill_ids=("spielos-ui",)),
                _step("visual_qa", "designer",
                      "Visual QA each asset; quarantined archetypes are "
                      "rejected in strict mode.",
                      skill_ids=("spielos-ui",)),
                _step("handoff", "designer",
                      "Hand the typed render report to content/analytics on "
                      "the campaign identity.",
                      skill_ids=("spielos-ui",)),
            ),
            department_id="design",
        ),
        Workflow(
            "video-render",
            "Render and verify a focused design-system-aligned video.",
            (
                _step("idea_lock", "video-producer",
                      "Lock the video's one idea.",
                      skill_ids=("videography",)),
                _step("brief", "video-producer",
                      "Write the video brief (persona, scenes, duration "
                      "target).",
                      skill_ids=("videography",)),
                _step("script", "video-producer",
                      "Write one complete narration script before "
                      "scene-splitting (scene_control_version 1.1).",
                      skill_ids=("videography", "copywriting")),
                _step("animate", "video-producer",
                      "Animate scenes from the registered video archetypes "
                      "with delivery intents.",
                      skill_ids=("videography",)),
                _step("render", "video-producer",
                      "Render the video and record evidence "
                      "{'video_render': {...}}.",
                      evidence_kind="video_render",
                      skill_ids=("videography",)),
                _step("audio_mix", "video-producer",
                      "Mix narration via the TTS fallback chain (Gemini → "
                      "Mistral x2 → Cartesia → ElevenLabs).",
                      skill_ids=("videography",),
                      connection_ids=("tts-voice",)),
                _step("qa", "video-producer",
                      "QA against the video eval suites (cta-link, "
                      "text-sync, media-qa).",
                      skill_ids=("videography",)),
            ),
            department_id="design",
        ),
        Workflow(
            "video-order",
            "Take a video order end-to-end: intake request, lock the One "
            "Idea, generate one-persona narration, derive readable scene "
            "dwell and total duration from measured speech, render a "
            "stable hook thumbnail, verify audible narration and "
            "provenance, and deliver video/thumbnail/QA together beneath "
            "the campaign batch Artifact.",
            (
                _step("intake", "video-producer",
                      "Take the video order and its campaign batch context.",
                      skill_ids=("videography",)),
                _step("idea_lock", "video-producer",
                      "Lock the One Idea.",
                      skill_ids=("videography",)),
                _step("scenario_script", "video-producer",
                      "Author the scenario and one complete narration "
                      "script (one persona, scene_control_version 1.1).",
                      skill_ids=("videography", "copywriting")),
                _step("tts_chain", "video-producer",
                      "Synthesize narration through the TTS fallback chain.",
                      connection_ids=("tts-voice",),
                      skill_ids=("videography",)),
                _step("narration_mix", "video-producer",
                      "Mix narration; derive scene dwell and total duration "
                      "from measured speech.",
                      skill_ids=("videography",),
                      connection_ids=("tts-voice",)),
                _step("render", "video-producer",
                      "Render the video and the stable hook thumbnail.",
                      evidence_kind="video_render",
                      skill_ids=("videography",)),
                _step("qa", "video-producer",
                      "QA: audible narration, provenance, CTA link card, "
                      "text sync (eval suites video-cta-link, "
                      "video-text-sync, video-media-qa).",
                      skill_ids=("videography",)),
                _step("deliverable", "video-producer",
                      "Deliver video/thumbnail/QA together beneath the "
                      "campaign batch Artifact.",
                      skill_ids=("videography",)),
            ),
            department_id="design",
        ),
    )

    eval_suites = ("video-cta-link", "video-text-sync", "video-media-qa")

    evidence_metrics = {
        "approved_designs": ("approved_design",),
        "rendition_count": ("render_report",),
        "video_renders": ("video_render",),
        "video_orders": ("video_render",),
    }

    goal_schema = {
        "metrics": ["approved_designs", "rendition_count", "video_renders",
                     "video_orders"],
        "config": {
            "workflow": {"enum": ["social-visual", "rendition-pack",
                                  "video-render", "video-order"]},
            "required_count": {"type": "integer"},
        },
    }

    workflow_agents = {
        "social-visual": "designer",
        "rendition-pack": "designer",
        "video-render": "video-producer",
        "video-order": "video-producer",
    }
