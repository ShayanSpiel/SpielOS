"""Videography Department — clean migrated declaration.

Owns two video trust models:
1. ``record-demo`` — authentic humanized browser capture of delivered workflows
2. ``remotion-motion-film`` — SpielOS Film System (Onda hard cut):
   BRIEF → WRITE → APPROVE → STORYBOARD → APPROVE FRAMES → BUILD
   → SOUND → PREVIEW → EVAL → FIX → FINAL. Motion comes ONLY from the
   installed Onda catalog (70 components + 18 transitions); look comes
   ONLY from SpielOS tokens/surfaces.

2026-09-04 (Onda hard cut):
- Collapsed the 13-step state machine to the 11-step abstract flow.
- Motion is Onda only: scene specs validate entrance/transition slugs
  against the Onda catalog (src/onda/catalog.ts) at validate time.
- Evals collapsed to storyboard-frame check, preview visual eval,
  final AV/technical gate.
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


_REMOTION = "departments/videography/remotion"
_SKILL = ("videography",)


class VideographyDepartment:
    """Declarative videography capability; execution belongs to GoalRuntime."""

    department_id = "videography"
    id = "videography"
    version = "3.0.0"
    description = (
        "Owns two video trust models: (1) authentic humanized browser demos "
        "of delivered Client Delivery workflows via pipeline/, and "
        "(2) coded Remotion films via the SpielOS Film System (Onda hard "
        "cut) — Onda catalog motion, SpielOS tokens, FilmFromSpec + "
        "TransitionSeries. Design's flat HTML brand-motion shorts stay separate."
    )
    agent_ids = ("videography-specialist", "videography-operator")
    production_ready = True

    workflows = (
        Workflow(
            "record-demo",
            "Resolve a delivered order, author a humanistic scenario, run a "
            "real humanized browser session, render the capture to MP4, and "
            "file evidence.",
            (
                _step("resolve", "videography-specialist",
                      "Resolve the delivered order from the client-delivery "
                      "registry and identify the provider/flow to demo. "
                      "A stage (not delivered) is never demoed.",
                      evidence_kind="resolved_order",
                      skill_ids=_SKILL,
                      requirements={"requires_delivered": True}),
                _step("author_scenario", "videography-specialist",
                      "Author or select a humanistic scenario JSON under "
                      "pipeline/scenarios/ (typed, validated steps; new demo "
                      "types are new scenario files, never new recorder code). "
                      "Record {'demo_scenario': {...}} as evidence.",
                      evidence_kind="demo_scenario",
                      skill_ids=_SKILL),
                _step("record", "videography-operator",
                      "Run the scenario in a real browser with "
                      "pipeline/recorder.py (humanized driver, seeded timing, "
                      "visible cursor, video capture) into "
                      ".spielos/artifacts/videography/. Capture the raw webm "
                      "+ steps.json timeline.",
                      skill_ids=_SKILL,
                      approval_key="record_browser_session",
                      requirements={"produces": ["webm", "steps_json"]}),
                _step("render", "videography-operator",
                      "Render the webm to a polished h264 MP4 with "
                      "pipeline/render.py (or postprod compose for narrated "
                      "showcases).",
                      skill_ids=_SKILL),
                _step("verify", "videography-operator",
                      "Verify the deliverable: webm + mp4 + steps.json exist, "
                      "every scenario step ran without failure, ffprobe "
                      "confirms h264 at intended duration, and the scenario "
                      "resolved a real delivered order. Record evidence "
                      "{'showcase_video': {...}, 'showcase_videos': <int>}.",
                      evidence_kind="showcase_video",
                      skill_ids=_SKILL,
                      requirements={"evidence_contract": [
                          "raw webm exists",
                          "rendered mp4 exists (h264, intended duration)",
                          "steps.json shows all steps ran",
                          "scenario resolved a real delivered order"]}),
            ),
            department_id="videography",
        ),
        Workflow(
            "remotion-motion-film",
            "Onda-first SpielOS Film System: brief → write → human idea "
            "approval → storyboard → human frame approval → build (SpielOS "
            "visuals + Onda motion only) → sound → preview → eval → fix → "
            "final render. Directors output Film DSL JSON only; every "
            "entrance/transition is an Onda slug from the installed catalog.",
            (
                _step("brief", "videography-specialist",
                      "Create productions/<id>/ under remotion/src/"
                      "productions/. Fill brief.json only (purpose, audience, "
                      "proposition, duration, platform, aspect_ratio, "
                      "narration/music allowed, assets, references). State = "
                      "BRIEF. Nothing visual is built yet. Record "
                      "{'motion_brief': brief.json}.",
                      evidence_kind="motion_brief",
                      skill_ids=_SKILL,
                      requirements={"state": "BRIEF", "path": f"{_REMOTION}/src/productions"}),
                _step("write", "videography-specialist",
                      "State WRITE. Choose exactly one production mode "
                      "(NARRATED|MUSIC_LED|SOUND_DESIGN|HYBRID) and explain "
                      "why. Write the scenario + narration (if allowed) + a "
                      "scene-sequence draft using ONLY registered archetypes "
                      "(Logo|Statement|Metric|Title|Diagram|UIFocus|Payoff). "
                      "Write draft scenes.json + creative-plan.md. Record "
                      "{'idea': {...}}.",
                      evidence_kind="idea",
                      skill_ids=_SKILL,
                      requirements={"state": "WRITE",
                                    "archetypes_only": True,
                                    "director_outputs_data_only": True}),
                _step("approve_idea", "videography-specialist",
                      "State AWAITING_IDEA_APPROVAL. Present the idea, "
                      "narration, scene sequence, theme sequence, and music "
                      "direction for human approval. Do not implement. Park "
                      "until approved (key idea_lock).",
                      evidence_kind="idea_pending",
                      skill_ids=_SKILL,
                      approval_key="idea_lock",
                      requirements={"state": "AWAITING_IDEA_APPROVAL"}),
                _step("storyboard", "videography-specialist",
                      "State STORYBOARD. Per scene, choose from approved "
                      "libraries ONLY: type · theme · background (6 SpielOS "
                      "surfaces) · text/SVG · Onda entrance slug · camera "
                      "slug · Onda transition slug · semantic SFX ids. "
                      "Write locked scenes.json. Director never touches CSS "
                      "and never invents motion. Run validate:spec — must "
                      "pass. Record {'storyboard': scenes.json}.",
                      evidence_kind="storyboard",
                      skill_ids=_SKILL,
                      requirements={"state": "STORYBOARD",
                                    "gate": "validate:spec",
                                    "onda_slugs_only": True}),
                _step("approve_frames", "videography-specialist",
                      "State AWAITING_FRAME_APPROVAL. Render static keyframes "
                      "(START/HERO/END per scene via remotion still) into "
                      "productions/<id>/previews/. Present the contact sheet "
                      "for human approval. Park until approved (key "
                      "frame_lock).",
                      evidence_kind="frames_pending",
                      skill_ids=_SKILL,
                      approval_key="frame_lock",
                      requirements={"state": "AWAITING_FRAME_APPROVAL",
                                    "produces": ["contact_sheet"]}),
                _step("build", "videography-operator",
                      "State BUILDING. On approval, assemble each approved "
                      "scene with SpielOS content components + Onda motion "
                      "ONLY (entrance/transition/camera via FilmFromSpec + "
                      "TransitionSeries). No hand-authored springs. Invalid "
                      "Onda slugs throw at validate time. Record "
                      "{'scenes_built': true}.",
                      skill_ids=_SKILL,
                      requirements={"state": "BUILDING",
                                    "onda_only": True}),
                _step("sound", "videography-operator",
                      "State SOUND. Mix narration/music/SFX from the asset "
                      "library; semantic cues only (src/audio + manifest). "
                      "Narration wins in NARRATED/HYBRID. Silence is allowed. "
                      "Record {'audio_mix': {...}}.",
                      evidence_kind="audio_mix",
                      skill_ids=_SKILL,
                      requirements={"state": "SOUND",
                                    "registry_only": True}),
                _step("preview", "videography-operator",
                      "State PREVIEW. Render a low-quality Remotion preview "
                      "of the full film (FilmFromSpec, default props = locked "
                      "spec). File preview + keyframe contact sheet under "
                      "productions/<id>/previews/. Record {'preview': {...}}.",
                      evidence_kind="preview",
                      skill_ids=_SKILL,
                      requirements={"state": "PREVIEW",
                                    "produces": ["preview_mp4"]}),
                _step("eval", "videography-specialist",
                      "State EVAL. Two evals only: (1) storyboard-frame "
                      "check — every motion id is an Onda slug, brand budget "
                      "holds, spec validates; (2) preview visual eval — "
                      "critic scores rendered frames (Composition/Hierarchy/"
                      "Spacing/Typography/Brand/Restraint/Continuity/Polish), "
                      "requiring 90+ and zero hard failures "
                      "(src/evals/*). Failures send the failing scenes to "
                      "FIX — never the whole film. Record evals.",
                      evidence_kind="eval",
                      skill_ids=_SKILL,
                      requirements={"state": "EVAL",
                                    "min_score": 90,
                                    "gates": ["storyboard-eval", "preview-eval"]}),
                _step("fix", "videography-operator",
                      "State FIX. Rebuild failing scenes only, using the same "
                      "approved pick lists (Onda motion, SpielOS surfaces). "
                      "Re-run preview + eval until the failing scene passes.",
                      skill_ids=_SKILL,
                      requirements={"state": "FIX",
                                    "onda_only": True}),
                _step("final_render", "videography-operator",
                      "State FINAL then DONE. From remotion/: render "
                      "FilmFromSpec to .spielos/artifacts/videography/<id>/ "
                      "with qt-safe h264 (render:proof). Write "
                      "render-report.json + poster. Run final AV/technical "
                      "gate (resolution/fps/pixel-format/duration/file "
                      "presence). Record {'motion_film': {...}, "
                      "'motion_films': <int>}.",
                      evidence_kind="motion_film",
                      skill_ids=_SKILL,
                      requirements={"state": "FINAL",
                                    "produces": ["mp4", "poster", "render_report"],
                                    "evidence_contract": [
                                        "rendered mp4 exists (h264, qt-safe)",
                                        "render-report.json filed",
                                        "idea was human-approved (idea_lock)",
                                        "frames were human-approved (frame_lock)",
                                        "storyboard + preview evals passed"]}),
            ),
            department_id="videography",
        ),
    )

    evidence_metrics = {
        "showcase_videos": ("showcase_video",),
        "demo_scenarios": ("demo_scenario",),
        "motion_films": ("motion_film",),
        "creative_plans": ("storyboard",),
    }

    goal_schema = {
        "metrics": ["showcase_videos", "demo_scenarios", "motion_films"],
        "config": {
            "workflow": {"enum": ["record-demo", "remotion-motion-film"]},
            "required_count": {"type": "integer"},
        },
    }

    workflow_agents = {
        "record-demo": "videography-specialist",
        "remotion-motion-film": "videography-specialist",
    }