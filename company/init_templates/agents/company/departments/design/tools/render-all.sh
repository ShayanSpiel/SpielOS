#!/bin/bash
# render-all.sh — Full SpielOS motion pipeline:
#   narration (Gemini TTS, ONE pinned voice, measured scene_timing)
#   → narration-only mix → base render → merge → poster/CTA.
#
# Usage:
#   bash scripts/render-all.sh b          # Scenario B, landscape + portrait, 30fps
#   bash scripts/render-all.sh c 30       # Scenario C, explicit fps
#   bash scripts/render-all.sh b 30 1080x1920,1920x1080  # explicit aspects
#
# Outputs land in .spielos/artifacts/design-restoration-polish-20260810/.
# This is the review-sample pipeline; nothing here publishes externally.
#
# Owner contract (2026-08-11): ONE narration voice (pinned in narration.json
# `voice_selection`, enforced by tts-gemini.js and mix-audio.js), scene
# windows derived from MEASURED spoken clip durations (speech first, then
# scenes — templates read narration.json scene_timing themselves), and a
# NARRATION-ONLY mix: no music bed, no duck bus.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIO="${1:-b}"
FPS="${2:-30}"
ASPECTS="${3:-landscape portrait}"

ART="$ROOT/.spielos/artifacts/design-restoration-polish-20260810"
mkdir -p "$ART/video" "$ART/graphics"

echo "╔══════════════════════════════════════════╗"
echo "║   SpielOS Motion Pipeline — $SCENARIO @ ${FPS}fps   ║"
echo "╚══════════════════════════════════════════╝"

# 1) Narration: Gemini 2.5 Flash TTS with the pinned master voice. The
#    generator purges stale clips for the scenario, measures each spoken
#    take, and writes the schedule into narration.json (scene_timing) +
#    .voice-manifest.json. No per-call voice overrides, no atempo, no cuts.
if [ "$SKIP_TTS" != "1" ]; then
  node "$SCRIPT_DIR/tts-gemini.js" "$SCENARIO"
fi

# 2) Narration-only mix (aspect-independent, 15s): no music bed. Refuses to
#    run without measured scene_timing or if the voice provenance mismatches.
node "$SCRIPT_DIR/mix-audio.js" "$SCENARIO" "$ART/video/.mix-$SCENARIO.m4a"

# 3) CTA frame time: 0.45s after the last scene starts (fallback 13.2s).
CTA_SEC=$(python3 -c "
import json
d = json.load(open('$ROOT/.agents/company/departments/design/templates/video/narration.json'))
scenes = d.get('scene_timing', {}).get('$SCENARIO', {}).get('scenes', [])
print(min(scenes[-1]['start'] + 0.45, 14.6) if scenes else 13.2)
")

for ASPECT in $ASPECTS; do
  case "$ASPECT" in
    landscape) LABEL=16x9 ;;
    portrait)  LABEL=9x16 ;;
    square)    LABEL=1x1 ;;
    story)     LABEL=4x5 ;;
    *) echo "Unknown aspect $ASPECT"; exit 1 ;;
  esac
  NAME="spielos-$( [ "$SCENARIO" = "b" ] && echo before-after || echo build-it )-flat-polish-$LABEL"
  echo ""
  echo "━━━ $ASPECT ($LABEL) ━━━"

  node "$SCRIPT_DIR/render-video.js" "$SCENARIO" "$ASPECT" "$FPS" "$ART/video/$NAME-base.mp4"

  ffmpeg -y -v error -i "$ART/video/$NAME-base.mp4" -i "$ART/video/.mix-$SCENARIO.m4a" \
    -c:v copy -c:a aac -b:a 192k -shortest "$ART/video/$NAME-voiced.mp4"
  # Poster at 0.6s so the first scene is visibly composed (frame 0 is the
  # dark pre-timing frame), CTA frame per the measured schedule.
  ffmpeg -y -v error -ss 0.6 -i "$ART/video/$NAME-base.mp4" -frames:v 1 "$ART/video/$NAME-poster.jpg"
  ffmpeg -y -v error -i "$ART/video/$NAME-base.mp4" -ss "$CTA_SEC" -frames:v 1 "$ART/video/$NAME-cta.jpg"
  echo "  voiced + poster + cta → $ART/video"
done

echo ""
echo "  Done. Deliverables in $ART/video"
