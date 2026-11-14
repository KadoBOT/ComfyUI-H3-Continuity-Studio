# Scene maps per Studio clip

Status: implemented on `feat/scene-map` (plan `docs/superpowers/plans/2026-11-14-studio-scene-maps.md`). Approved 2026-11-14 (user: "Approved"), including the seven proposals: `scene-map-1` requirement, borrow with local copy, editor in the Viewer pane, Cast-linked markers, end layout on last-frame stills, the video mode table with no T2VA upgrade, and section-aware first-shot text. The "end here" test passed in the user's own Studio render.

## Intent and confirmed decisions

Each Studio clip can optionally carry a top-down Scene Map (the `H3C_SceneMap` editor from PR #87): a map picture, markers for subjects and props, and an arrow-only camera whose tip is the lens. The goal is continuity: every clip remembers where things were when the previous clip ended.

Confirmed by the user:

- Off by default, per clip.
- Every marker and the camera have an opening position and an end position.
- Continuous clips (no cut): clip N's end is clip N+1's opening, and the reverse. Editing either side edits the same positions.
- After a cut, turning the map on copies the previous map's end positions; from then on the clip is independent.
- Ref2VA keeps the option of receiving the map picture. It is a per-clip choice, off by default.
- The map is sent at 1 MP.

Settled by testing (shot 22, Strays):

- In a properly structured Ref2VA prompt, the map picture never leaks when it is anchored as a storyboard with `weak_reference`. Spike videos C and D and the user's Studio render all came out clean.
- Drawing end positions on the picture (rings and trails) made H3 duplicate a subject. So the picture shows opening positions only. End positions and camera movement reach the model as words.

## Approaches

1. One stored copy, borrowed across continuous joins (selected). A continuing clip reads its opening from the previous clip's end and writes edits back there. Positions cannot drift apart.
2. Each clip stores both states and the Studio keeps neighbours in sync on every edit. Rejected: every structural edit (move, delete, reorder, cut toggle, undo) would need a sync hook, and missing one silently breaks continuity.
3. One map per scene with keyframes on the film time. Rejected: overlapping tracks and cuts make "scene" ambiguous, and it hides the per-clip control the user asked for.

## Data model

A new optional box field, `scene_map`. It is absent when the clip has never had a map, and it is kept when switched off so the work is not lost.

```json
"scene_map": {
  "on": true,
  "picture": {"type": "input", "subfolder": "maps", "filename": "overpass.png"},
  "width": 2000, "height": 1123,
  "markers": [{"id": "m1", "label": "STRAY", "text": "", "icon": "person", "color": "#e8a33d", "size": 1,
               "legend": true, "entity": "e1"}],
  "camera": {"fov": 55, "height": 0.5, "label": "CAMERA", "color": "#ffffff"},
  "opening": {"camera": {"x": 0.684, "y": 0.826, "tx": 0.44, "ty": 0.392}, "markers": {"m1": [0.367, 0.57]}},
  "end": {"camera": {"x": 0.684, "y": 0.826, "tx": 0.44, "ty": 0.392}, "markers": {"m1": [0.4, 0.419]}},
  "absent": ["m3"],
  "legend": {"show": true, "position": "bottom-left"},
  "scale": 1,
  "video_picture": false
}
```

- `markers` holds identity and look; `opening` and `end` hold positions only. Coordinates are 0–1 fractions of the map picture, as in the node. The camera's look (fov, height, label, colour) is shared; only its place and aim (`x`, `y`, `tx`, `ty`) differ between opening and end.
- Building the layout for one state (marker positions merged into the marker list) gives exactly what `scene_map.normalize` reads today, so `view`, `describe`, `render` and the editor are reused unchanged.
- `entity` optionally links a marker to a Cast entity, so the prompt can call it by that clip's `<Subject N>` label.
- `absent` lists markers carried in from the previous clip that are not in this one ("not in this clip").
Compatibility: a timeline with any `scene_map.on` adds `scene-map-1` to `requires`. Older versions then refuse the file instead of silently dropping maps on save, the same policy as `timeline-tracks-1`. Python `Box` and the browser model's box normalizer both whitelist the field (`timeline.py` parse and serialize; `h3c_timeline_model.mjs` normalize).

## Linking rules

A clip borrows when `previous_index(timeline, index)` returns an adjacent clip on the same track, the clip is not fresh (no cut), and that clip's map is on.

- The borrowing clip's opening is the previous clip's `end`. It inherits the previous picture and markers, minus its own `absent` list, plus markers it added itself.
- Moving an inherited marker or the camera at the opening writes the previous clip's `end`. Editing an inherited marker's look writes the clip that owns it.
- While linked, the borrowing clip keeps a local copy of everything it borrows (picture, size, camera look, marker looks, opening positions). The copy is refreshed after every map edit, for the edited clip and every borrowing clip after it, so a later break falls back to the last state seen, not a stale one. Only the browser writes these copies; Python reads the linked values while the link holds.
- Markers the clip added itself keep their opening in the clip's own `opening`.
- When the link breaks (cut turned on, previous clip deleted, moved or its map turned off), the clip uses its own `opening` copy. Nothing jumps, and no structural hook is needed.
- Turning the map on: a continuing clip with a mapped predecessor borrows. Otherwise the clip copies the end positions, picture and markers of the nearest earlier clip on the track that has a map. With no earlier map it starts empty and asks for a picture.
- Undo and history work unchanged because everything lives in the timeline JSON.

## Clip panel

A new switch section "Scene map" sits in the clip inspector with the other switch sections ("Visual memory", "Exact length"). It is off by default. On reveals:

- A small preview of the opening layout and an "Edit map" button. The full Scene Map editor (the PR #87 widget, reused as a component rather than a node widget) opens in the Viewer pane, which has the room the 640 px editor needs, and closes back to the video.
- In the editor: Opening and End tabs, with faint ghosts of the other state for reference. On a borrowing clip the Opening tab says "Shared with clip N's end".
- A "Not in this clip" toggle on inherited markers, and a Cast link picker per marker.
- "Send map picture to video", shown only when the clip already renders as fresh Ref2VA from its own pictures, off by default. The map never turns a T2VA clip into Ref2VA, because that would demand a different prompt format. If the clip already sends 9 pictures the switch is disabled, with the reason.
- A read-only "Added to the prompt" preview of the exact text the Studio inserts for stills and for video.

## Stills

When the clip's map is on, still requests add the rendered map as an extra reference, after every other reference so it is never `<Picture 1>`.

- A first-frame still uses the opening layout. A last-frame still uses the end layout, the one place end positions appear as markers, since a still is a single moment.
- The reference role is `blocking map` (already in `image_recipe.REFERENCE_USE`), at 1 MP. The prompt line moves to the storyboard wording proven in the test: "`@stillN` is a storyboard reference: a top-down plan of this place defining the camera viewpoint and where each subject stands; nothing from the plan is drawn."
- The render is pinned through `stills.import_image` and `pin_image`, so it is content-addressed like any other still reference.
- The map on a node graph (PR #87 path) keeps working unchanged.
- This applies to the pixel still recipe (MiniMax image), the Studio's H3 still path. Graph-adapter still recipes do not get the map, and the panel says so.

## Video

What the clip receives depends on how it renders:

| Clip renders as | Map text | Map picture |
| --- | --- | --- |
| Fresh Ref2VA | yes | only with "Send map picture to video" |
| Fresh T2VA | yes | no |
| FLF2VA / I2VA (has a start frame) | no | no |
| Continuing clip (carried frames) | no | no |

A start frame already shows the opening, so repeating it adds nothing. The editor still keeps those clips' positions for linking and stills.

Map text, built from the existing `scene_map.view` and `describe`:

- Camera: height, lens width, and what is in frame left to right and near to far at the opening. If the end camera differs, the move in plain words (pushes in, trucks left, pans right about 30 degrees). Height and lens are shared by both states, so they never move.
- Motion: each marker whose end differs, described from the opening camera. Example: "STRAY edges from the far left towards the centre background". A marker with an `entity` is named by that clip's `<Subject N>` label. A marker entering or leaving frame is said so.
- Markers that do not move are named once in the opening line, not repeated.

Where the text goes:

- Six-section Ref2VA prompt: the blocking text goes at the end of the `[Shot 1]` paragraph in `detailed_description`.
- With the map picture, two more lines go in. One closes `subject_definitions`: "`@imageN` is a storyboard reference for [Shot 1]: a top-down plan of this place defining the camera viewpoint and where each subject starts." The other closes `retention_analysis`: "`@imageN` ([Shot 1] storyboard): weak_reference - only the camera viewpoint and where each subject starts are followed; the plan's view, symbols, arrow, labels and legend are not reproduced."
- T2VA `integrated_multimodal_description`: the blocking text goes at the end of the `[Shot 1]` paragraph.
- Unstructured prompt: a final paragraph.
- The map applies to the clip's first shot only. Multi-shot clips get no text for later shots, and the panel says so.

The insert happens in `assemble_prompt`, next to `reference_assets.native_prompt`. It is section-aware (one line per section) rather than appended after `non_diegetic_music` the way native asset lines are today.

Map picture transport: when sent, the parsed timeline gains one virtual Studio picture per such clip. Its slot is the next free `imageN` after all user pictures, assigned at parse. It is hidden from the Pictures list and shown in that clip's reference strip labelled "Map". Because the inserted text mentions `@imageN`, `box_slots`, `studio_pictures.used` and the cache fingerprint pick it up with no special case. The file is rendered on demand into `input/h3c_scene_maps/<digest>.png`, keyed by the opening layout and the base picture, and rendered again when the base picture is newer than it. Because the map takes the highest slot, it never renumbers the clip's other pictures, and it only joins clips that are already Ref2VA. So the browser does not mirror the slot. The panel's "Added to the prompt" preview and the switch's disabled reason come from a server route that runs the same Python.

## Errors and limits

- Missing map picture file: stills and video fail with the clip number and filename, like other Studio pictures.
- Map on without a camera: stills get the picture and the storyboard line without a viewpoint sentence. Video gets no map text, since positions in frame need a camera, and the panel warns.
- 9-picture limit: the map picture is never added past `MAX_REF_IMAGES`. The text still goes in.

## Out of scope

- Editing maps through agent/MCP tools; they keep the field intact.
- Drawing paths or keyframes between opening and end.
- Maps on audio or text lanes.

## Verification

- Python: normalize and round-trip `scene_map`; the `requires` flag; borrowing and break fallback; text for each prompt format; slot assignment and the 9-picture limit; mode table rows; still references for first and last frames.
- JS: model normalize; borrow/write-back in the editor; mirrored slot and mode; panel visibility rules.
- Full suite (`node tests/run.mjs`) green; module version tags re-stamped.
- Manual: rebuild the shot 22 story with a Studio map instead of the hand-made `image23`. Render once with "Send map picture to video" on and compare against the user's passing render. Then a two-clip continuous case to check that clip 2 opens where clip 1 ended.

## Release

Lands on `feat/scene-map` (PR #87, now based on `main` after 1.0.0) as a minor release, with CHANGELOG notes. Merge and tagging happen only when the user asks.
