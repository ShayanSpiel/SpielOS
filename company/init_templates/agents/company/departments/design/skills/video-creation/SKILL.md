---
name: video-creation
description: Turn an approved narration into a verified video rendition.
---

# Video creation

Read the approved campaign, selected template in `templates/registry.json`, and
`templates/video/narration.json`.

1. Use the complete approved narration; do not change its message.
2. Select a registered template that fits the story and respects batch rotation.
3. Generate one narrator for the whole video. If the provider changes, restart
   the video and record its provenance.
4. Measure speech, then set scene timing. Do not trim or speed spoken text.
5. Render a narration-only video and verify streams, timing, visible text, and
   a stable thumbnail.
6. Return `render_report` with campaign, batch, item, and asset identity.

The configuration and tools are the operational authority; this skill does not
repeat their settings.
