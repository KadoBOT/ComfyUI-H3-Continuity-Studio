# Scene maps per Studio clip — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, inline (the user forbids subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each Studio clip can carry an optional Scene Map with opening and end positions, linked across continuous clips, that feeds stills (map picture plus storyboard line) and video (blocking text, optional weak storyboard picture for Ref2VA).

**Architecture:** A new Python module `h3_continuity/scene_maps.py` owns the per-clip field: validation, linking (`resolve`), prompt parts and the section-aware insert, the virtual map picture, and the still reference. `scene_map.py` (the PR #87 node) gains frame-only wording helpers. A mirror module `web/h3c_scene_maps.mjs` owns linking and every edit in the browser, checked against Python through one shared fixture. The editor widget becomes a node-free component that the node and a new Studio focus page both mount.

**Tech Stack:** Python 3 (ComfyUI embedded), PIL, unittest; browser ES modules, `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-14-studio-scene-maps-design.md`

## Global Constraints

- Off by default. A clip without `scene_map`, or with `scene_map.on` false, behaves exactly as today: same prompt, slots and `layout_key`.
- Feature name `scene-map-1`, required when any box has `scene_map.on` true.
- Coordinates are 0–1 fractions of the map picture. The camera's place and aim are `x`, `y`, `tx`, `ty`. Look fields (`fov`, `height`, `label`, `color`) are shared by both states.
- The picture sent to any model shows the opening layout only. The one exception is a last-frame still, which shows the end layout.
- Map pictures are sent at 1 MP (`h3c_reference_megapixels` = 1.0, as the node does).
- Never more than `MAX_REF_IMAGES` (9) pictures per clip. The text still goes in when the picture cannot.
- Exact copy, video definition line: `@imageN is a storyboard reference for [Shot 1]: a top-down plan of this place defining the camera viewpoint and where each subject starts.`
- Exact copy, video retention line: `@imageN ([Shot 1] storyboard): weak_reference - only the camera viewpoint and where each subject starts are followed; the plan's view, symbols, arrow, labels and legend are not reproduced.`
- Exact copy, still line opening: `@stillK is a storyboard reference: a top-down plan of this place defining the camera viewpoint and where each subject stands; nothing from the plan is drawn.` followed by `scene_map.describe(...)`.
- Video map text only for fresh clips with no start frame whose base mode (without the map) is `t2va` or `ref2va`.
- Commits are local checkpoints on `feat/scene-map`. Never push unless the user asks.
- After any `web/` change, run `node tools/module_versions.mjs --write`.
- Tests: `$env:H3_PYTHON='D:\Projects\ComfyUI_windows_portable\python_embeded\python.exe'; $env:COMFY_ROOT='D:\Projects\ComfyUI_windows_portable\ComfyUI'; node tests/run.mjs`. A single Python file: `& $env:H3_PYTHON -m unittest tests.python.test_scene_maps -v`. A single JS file: `node --test tests/web/scene_maps.test.mjs`.

## Review Focus

1. A structured prompt that mentions `[Shot 1]` outside the description (for example in `subject_definitions`): the blocking text must land on the `[Shot 1]` line of `detailed_description` / `integrated_multimodal_description`, never on an earlier mention. Test in Task 3.
2. A three-clip continuous chain, where the middle clip marks an inherited marker "not in this clip": it is gone in clips 2 and 3, and still in clip 1. Test in Task 1 (fixture case `absent_propagates`) and Task 5 (same fixture).
3. A link that breaks because clip 2 gains a cut: clip 2 keeps the last borrowed positions from its local copy, nothing jumps. Test in Task 5 (`refreshChain` then a cut) and Task 1 (fixture case `broken_link_uses_copy`).
4. A Ref2VA clip that already sends 9 pictures with "Send map picture to video" on: no picture and no definition or retention lines, blocking text still present, and the preview reason says why. Test in Task 4.
5. The base map picture replaced in place under the same filename: the rendered map is rebuilt, not served stale. Test in Task 4 (`ensure` re-renders when the base mtime is newer).

---

### Task 1: Per-clip field, validation and linking (Python)

**Files:**
- Create: `h3_continuity/scene_maps.py`
- Modify: `h3_continuity/timeline.py` (`REQUIRES` line 39, `Timeline` dataclass, end of `parse` before `return parsed`)
- Create: `tests/fixtures/scene_maps/linking.json`
- Test: `tests/python/test_scene_maps.py`

**Interfaces:**
- Produces:
  - `FEATURE = 'scene-map-1'`
  - `validate(raw, n) -> dict | None`. `raw` is the box's `scene_map` value or None; `n` is the box number for messages. It returns a full dict with every key from the spec (`on`, `picture` (file dict or None), `width`, `height`, `markers`, `camera`, `opening`, `end`, `absent`, `legend`, `scale`, `video_picture`). It raises `ValueError` through `timeline._error`, with messages such as `box 2 scene map markers need unique ids`.
  - `Timeline.scene_maps: list`, one entry per box: the validated dict or None.
  - `source(timeline, index) -> int | None`: the adjacent previous clip (`previous_index(..., adjacent=True)`), when `index` is not fresh and that clip's map is on.
  - `resolve(timeline, index) -> dict | None`: None when the map is off. Otherwise `{'picture', 'width', 'height', 'opening', 'end', 'source', 'owners'}`.
    - `opening` and `end` are layouts that `scene_map.normalize` accepts unchanged (markers carry `x`/`y`).
    - `owners` maps each marker id to the clip index whose `markers` list defines it.

- [ ] **Step 1: Write the shared fixture `tests/fixtures/scene_maps/linking.json`**

A list of cases `{"name", "timeline": {...timeline JSON...}, "expect": [{"index", "source", "opening": {"camera": [x,y,tx,ty] | null, "markers": {id: [x,y]}}, "end": {...same...}, "markers": [ids in order]}]}`. Cases:
- `single_clip`: one clip, map on. Opening and end come from its own fields, and an end marker without a stored position equals its opening.
- `continuous_borrows`: two clips, clip 2 not cut. Clip 2's opening is clip 1's end, its markers are clip 1's plus its own addition `m9`, and `source` is 0.
- `cut_is_independent`: clip 2 has `cut: true`, so `source` is null and it uses its own opening.
- `absent_propagates`: three continuous clips, clip 2 `absent: ["m2"]`. `m2` is in clip 1 and missing from clips 2 and 3.
- `broken_link_uses_copy`: clip 2 has `cut: true` and its own `opening` equal to clip 1's old end, so the expected opening is the copy.
- `predecessor_off`: clip 1's map has `on: false`, so clip 2 does not borrow.

- [ ] **Step 2: Write the failing tests**

```python
class ResolveFixtureTest(unittest.TestCase):
    def test_python_resolve_matches_every_fixture_case(self):
        for case in json.loads(Path('tests/fixtures/scene_maps/linking.json').read_text()):
            parsed = timeline.parse(json.dumps(case['timeline']))
            for want in case['expect']:
                got = scene_maps.resolve(parsed, want['index'])
                self.assertEqual(got['source'], want['source'], case['name'])
                self.assertEqual([m['id'] for m in got['opening']['markers']], want['markers'], case['name'])
                self.assertEqual(positions(got['opening']), want['opening'], case['name'])
                self.assertEqual(positions(got['end']), want['end'], case['name'])

class ValidateTest(unittest.TestCase):
    def test_absent_field_is_none_and_off_map_needs_no_feature(self): ...   # parse ok, scene_maps == [None] / [{'on': False, ...}]
    def test_on_map_requires_feature(self): ...   # assertRaisesRegex(ValueError, 'scene-map-1')
    def test_duplicate_marker_ids_rejected(self): ...   # 'box 1 scene map markers need unique ids'
    def test_picture_must_be_local_file(self): ...   # {'type': 'input', 'filename': '../x.png'} rejected
    def test_resolved_layouts_survive_normalize(self):
        got = scene_maps.resolve(parsed, 0)
        self.assertEqual(scene_map.normalize(got['opening'])['markers'][0]['x'], got['opening']['markers'][0]['x'])
```

`positions(layout)` is a test helper returning `{"camera": [x,y,tx,ty] | None, "markers": {id: [x,y]}}`.

- [ ] **Step 3: Run to see them fail**

Run: `& $env:H3_PYTHON -m unittest tests.python.test_scene_maps -v`
Expected: FAIL with `ImportError: cannot import name 'scene_maps'`.

- [ ] **Step 4: Implement `validate`, `source`, `resolve` and wire `parse`**

- In `parse`, set `parsed.scene_maps = [scene_maps.validate(raw.get('scene_map'), n) for n, raw in enumerate(boxes, 1)]`. Then, if any is on and `FEATURE not in requires`, raise `box {n} has a scene map, which requires scene-map-1`, the same pattern as box-bound audio.
- Add `scene_maps.FEATURE` to `REQUIRES`.
- `resolve` follows the spec's linking rules:
  - With a source, `picture`, `width`, `height`, the camera look and the inherited markers come from `resolve(source)`. Drop the ids in `absent`, then append the clip's own markers whose ids are not inherited.
  - Inherited markers open at the source's end positions. Own markers open at the clip's `opening` positions.
  - The end camera and end positions come from the clip's `end`, falling back to the opening value.
  - Memoize per call chain with a dict passed down, rather than recomputing the chain.

- [ ] **Step 5: Run to see them pass**

Run: `& $env:H3_PYTHON -m unittest tests.python.test_scene_maps -v`
Expected: PASS.

- [ ] **Step 6: Commit** — `git add h3_continuity/scene_maps.py h3_continuity/timeline.py tests/fixtures/scene_maps tests/python/test_scene_maps.py; git commit -m "feat: per-clip scene map field and linking"`

---

### Task 2: Frame-only wording (Python, `scene_map.py`)

**Files:**
- Modify: `h3_continuity/scene_map.py` (`describe` lines 164–194)
- Test: `tests/python/test_scene_map.py` (add a class)

**Interfaces:**
- Produces:
  - `frame_text(layout, width, height, names) -> str`. `names` maps marker id to display name; a missing id falls back to `_name(marker)`. It returns `''` without a camera. Format: `A camera about 0.5 m above the ground with a 55 degree horizontal field of view.` then the same `In frame, from left to right: …` and `Out of frame: …` clauses `describe` builds, using `names`. It never mentions the map.
  - `motion_text(opening, end, width, height, names) -> str`, `''` when nothing moves. Rules:
    - Camera: compare the opening and end cameras in the opening camera's frame. Forward or back more than 2% of the map diagonal gives `The camera pushes in` / `pulls back`. Sideways gives `trucks left` / `trucks right`. A heading change of 5 degrees or more gives `pans left` / `pans right about N degrees`, N rounded to 5. Join the parts with `, ` and ` and `, ending in `.`.
    - Markers: positions are taken against the opening camera, from `view(...)`. A marker moves when its position changes by more than 2% of the map diagonal. Use `{name} moves from {spot} to {spot}` with the leading "on the"/"in the" stripped from the second spot (the existing `bare()` behaviour). If it is in frame only at the opening, `{name} leaves frame to the left/right` (by the sign of its end angle). If only at the end, `{name} enters from the left/right`.
  - `_spot(offset, distance, far) -> str`, factored out of `describe` (side, depth). `describe`'s output stays byte-identical.

- [ ] **Step 1: Write the failing tests**

```python
class FrameWordingTest(unittest.TestCase):
    def test_describe_is_unchanged(self):  # pin the current SHOT_22 describe() string verbatim
    def test_frame_text_names_and_never_mentions_the_map(self):
        text = scene_map.frame_text(normalize(SHOT_22), W, H, {})
        self.assertTrue(text.startswith('A camera about 0.5 m above the ground with a 55 degree horizontal field of view.'))
        self.assertNotIn('map', text)
        self.assertIn('STRAY on the far left', text)   # whatever SHOT_22 yields today in describe(); copy it
    def test_motion_text_shot_22_end_positions(self):
        end = moved(SHOT_22, STRAY=(800 / W, 470 / H), OUTCAST=(1030 / W, 500 / H))
        text = scene_map.motion_text(normalize(SHOT_22), normalize(end), W, H, {})
        self.assertIn('STRAY moves from', text); self.assertIn('OUTCAST moves from', text)
        self.assertNotIn('WOUNDED GRAZER', text)
    def test_motion_text_camera_pan(self):  # rotate the aim 30 degrees right: 'The camera pans right about 30 degrees.'
    def test_motion_text_leaving_frame(self):  # end position outside the cone: 'leaves frame to the right'
    def test_nothing_moves_is_empty(self):
```

- [ ] **Step 2: Run to see them fail** — `& $env:H3_PYTHON -m unittest tests.python.test_scene_map -v`. Expected: FAIL (`AttributeError: frame_text`).
- [ ] **Step 3: Implement `_spot`, `frame_text`, `motion_text`.**
- [ ] **Step 4: Run to see them pass**, plus the whole of `tests.python.test_scene_map`. Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: frame-only scene map wording for video prompts"`

---

### Task 3: Video prompt parts and the section-aware insert (Python)

**Files:**
- Modify: `h3_continuity/scene_maps.py`
- Modify: `h3_continuity/timeline.py` (`assemble_prompt` lines 1001–1006)
- Test: `tests/python/test_scene_maps.py`

**Interfaces:**
- Consumes: `resolve` (Task 1); `frame_text`, `motion_text` (Task 2); `timeline.box_slots`, `is_fresh`.
- Produces:
  - `names(timeline, index, resolved, prompt) -> dict`. For a marker with `entity`, use the `<Subject N>` key in `timeline.story[index]['cast']` that maps to it, when that label appears in `prompt`. Otherwise use the entity's name from `timeline.bible`. Otherwise the marker label.
  - `base_slots(timeline, index) -> Slots`: `box_slots` on a shallow copy of `timeline` whose `scene_maps` has None at `index`, so there is no recursion.
  - `video_parts(timeline, index) -> dict | None`: `{'blocking': str, 'definition': str, 'retention': str, 'slot': str, 'reason': str}`.
    - None when the map is off.
    - `blocking` is `frame_text(opening)` plus `motion_text(opening, end)`, joined by a space.
    - `definition` and `retention` are `''` unless `slot` is set (Task 4 sets slots; until then `slot` is always `''`).
    - When the gating fails, all text is `''` and `reason` is one of: `This clip has a start frame, which already shows the opening.`, `This clip continues the previous one.`, `This clip renders as FLF2VA.`, `The map has no camera, so the video gets no map text.`, `The map has no picture.`
  - `insert(prompt, parts) -> str`. Section headers are lines matching `^(\w+):\s*$`.
    - `blocking` goes at the end of the first line starting with `[Shot 1]` inside the `detailed_description` or `integrated_multimodal_description` section. Without one, it goes at the end of that section's body; with neither section, as a final paragraph.
    - `definition` is a new last line of the `subject_definitions` body, and `retention` a new last line of the `retention_analysis` body. Without those sections, each is a final paragraph.
    - Empty parts change nothing.
  - `assemble_prompt` returns `scene_maps.insert(<current result>, scene_maps.video_parts(timeline, index))` when `video_parts` is not None.

- [ ] **Step 1: Write the failing tests**

```python
SIX = ('subject_definitions:\n<Subject 1> is @image17, a woman.\n\nsummary:\nA standoff.\n\nretention_analysis:\n'
       '@image17: fully_preserved - identity.\n\ndetailed_description:\n[Shot 1] Low wide shot under the overpass.\n\n'
       'overall_soundscape:\nWind.\n\nnon_diegetic_music:\nNone.')

class InsertTest(unittest.TestCase):
    def test_blocking_lands_on_the_description_shot_line(self):
        out = scene_maps.insert(SIX.replace('a woman.', 'a woman seen in [Shot 1] reference.'), parts(blocking='B.'))
        self.assertIn('[Shot 1] Low wide shot under the overpass. B.', out)
        self.assertNotIn('reference. B.', out)
    def test_definition_and_retention_close_their_sections(self):
        out = scene_maps.insert(SIX, parts(definition='D.', retention='R.'))
        self.assertIn('a woman.\nD.\n\nsummary:', out); self.assertIn('identity.\nR.\n\ndetailed_description:', out)
    def test_t2va_format(self):  # 'integrated_multimodal_description:\n[Shot 1] X.' -> '[Shot 1] X. B.'
    def test_unstructured_prompt_gets_a_final_paragraph(self):  # 'Plain prompt.' -> 'Plain prompt.\n\nB.'
    def test_empty_parts_change_nothing(self):

class VideoPartsTest(unittest.TestCase):
    def test_off_map_leaves_prompt_and_layout_key_unchanged(self):   # same timeline with and without {'on': False}
    def test_fresh_ref2va_gets_blocking_text_in_assembled_prompt(self):
    def test_first_frame_clip_gets_reason_and_no_text(self):
    def test_continuing_clip_gets_reason_and_no_text(self):
    def test_cast_entity_marker_uses_subject_label(self):  # cast {'<Subject 1>': 'e1'}, marker entity 'e1' -> '<Subject 1> moves from'
```

- [ ] **Step 2: Run to see them fail.** Expected: FAIL (`AttributeError: insert`).
- [ ] **Step 3: Implement `names`, `base_slots`, `video_parts`, `insert`, and hook `assemble_prompt`.**
- [ ] **Step 4: Run `tests.python.test_scene_maps`, then the full suite** (`assemble_prompt` is shared). Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: scene map blocking text in clip video prompts"`

---

### Task 4: Map picture for Ref2VA video, preview route (Python)

**Files:**
- Modify: `h3_continuity/scene_maps.py`
- Modify: `h3_continuity/timeline.py` (call `scene_maps.attach(parsed)` as the last step of `parse`; add `value['scene_map']` in `layout_key` after the `flf_refmods` lines)
- Modify: `h3_continuity/studio_pictures.py` (`load`, `fingerprint`)
- Modify: `h3_continuity/routes.py` (register next to `scene_map.register(routes)`, line 420)
- Test: `tests/python/test_scene_maps.py`

**Interfaces:**
- Consumes: `resolve`, `base_slots`, `video_parts` (Tasks 1 and 3); `scene_map.render`, `scene_map.resize`; `MAX_REF_IMAGES`.
- Produces:
  - `attach(timeline) -> None`. A clip sends the picture when `video_picture` is on, the picture is set, the gating passes, `base_slots(...).mode == 'ref2va'` and `len(base_slots(...).image_inputs) < MAX_REF_IMAGES`.
    - Each sending clip, in box order, takes the next `imageN` above every existing picture slot and above 16.
    - It appends `{'slot', 'file': {'type': 'input', 'subfolder': 'h3c_scene_maps', 'filename': digest + '.png'}, 'title': 'Scene map', 'scene_map': {'box': id, 'layout': opening, 'picture': file}}` to `timeline.pictures`.
    - It sets `timeline.scene_map_slots = {index: slot}`.
    - `digest = sha1(json(opening layout, picture file, sort_keys)).hexdigest()[:20]`.
  - `video_parts` now fills `slot`, `definition` and `retention` (exact copy in Global Constraints) from `scene_map_slots`. When the picture was wanted but blocked by the limit, it sets `reason = 'This clip already sends 9 pictures, so the map goes in as text only.'`.
  - `ensure(picture) -> str`: the rendered file's path. It renders `scene_map.render(base, layout)` then `resize` to 1 MP when the file is missing or older than the base file. A missing base file raises `ValueError('H3 Timeline: box N uses a scene map picture (NAME), but the file is missing from ComfyUI\'s input folder')`, where N is the clip number and NAME the filename.
  - `studio_pictures.load` and `fingerprint` call `scene_maps.ensure(picture)` before `path(...)` for pictures carrying `scene_map`.
  - `layout_key`: `value['scene_map'] = digest` when the box sends a map picture.
  - Route `POST /h3c/scene-map/preview`, body `{"timeline": str, "box": id}`, returns `{"video": {"mode": str, "parts": {...}|null, "reason": str}, "stills": {"first": str, "last": str}}`. Stills come from Task 6's `still_line`; until Task 6, `stills` is `{}`.
    - A missing picture or parse error returns HTTP 400 `{"error": message}`.

- [ ] **Step 1: Write the failing tests**

```python
class PictureTest(unittest.TestCase):
    def test_ref2va_clip_with_switch_gets_next_slot_and_both_lines(self):
        parsed = timeline.parse(story(pictures=['image17', 'image18'], video_picture=True))
        self.assertEqual(parsed.scene_map_slots, {0: 'image19'})
        text = timeline.assemble_prompt(parsed, 0)
        self.assertIn('@image19 is a storyboard reference for [Shot 1]: a top-down plan of this place defining the camera '
                      'viewpoint and where each subject starts.', text)
        self.assertIn('@image19 ([Shot 1] storyboard): weak_reference - only the camera viewpoint', text)
        self.assertEqual(timeline.box_slots(parsed, 0).tags['image19'], '<Picture 3>')
    def test_t2va_clip_never_gets_the_picture(self):
    def test_nine_pictures_blocks_picture_keeps_text(self):  # reason == 'This clip already sends 9 pictures, ...'
    def test_switch_off_sends_no_picture(self):
    def test_layout_key_changes_when_opening_moves(self):
    def test_ensure_renders_once_and_rerenders_when_base_is_newer(self):  # temp input dir, os.utime the base
    def test_ensure_missing_base_names_clip_and_file(self):
    def test_preview_route_returns_parts_and_reason(self):  # call the handler with a fake request, as other route tests do
```

- [ ] **Step 2: Run to see them fail.** Expected: FAIL (`AttributeError: scene_map_slots`).
- [ ] **Step 3: Implement `attach`, `ensure`, the `studio_pictures` hooks, the `layout_key` entry and the preview route.** Before relying on it, confirm that the caller building the connected image pool for `plan_box` includes every `timeline.pictures` slot (search `plan_box(` callers). If it doesn't, add the map slots there.
- [ ] **Step 4: Run `tests.python.test_scene_maps` and the full suite.** Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: optional scene map picture for Ref2VA clips"`

---

### Task 5: Browser model and linking edits (JS)

**Files:**
- Create: `web/h3c_scene_maps.mjs`
- Modify: `web/h3c_timeline_model.mjs` (box normalize ~line 205, serialize ~line 261, `OWN_FEATURES` line 280, `requiredFeatures` line 283)
- Test: `tests/web/scene_maps.test.mjs` (reads `tests/fixtures/scene_maps/linking.json`)

**Interfaces:**
- Consumes: `isFresh` from `h3c_timeline_model.mjs`; `previousIndex`, `followingIndex`, `trackIndices` from `h3c_tracks.mjs`.
- Produces (all take `state`, a normalized timeline; edits mutate it and the caller commits for undo):
  - `FEATURE = 'scene-map-1'`
  - `normalizeSceneMap(raw) -> object | undefined`: the same defaults as Python `validate`, but it does not throw; bad parts are dropped.
  - `source(state, index) -> number | null` and `resolve(state, index) -> object | null`: the same results as Python on the shared fixture.
  - `enable(state, index)`:
    - An existing map just gets `on = true`.
    - With a source, it borrows and calls `copyBorrowed`.
    - Otherwise it copies the nearest earlier clip on the track (`trackIndices`) that has a map on: picture, size, camera look and markers, with `opening` set to that clip's resolved end positions and `end` empty.
    - Otherwise it starts empty with `picture: null`.
  - `disable(state, index)`: `on = false`, everything else kept.
  - `move(state, index, phase, target, point)`.
    - `phase` is `'opening'` or `'end'`. `target` is `{kind: 'marker', id}` or `{kind: 'camera'}` / `{kind: 'aim'}`. `point` is `{x, y}` for marker and camera, `{tx, ty}` for aim.
    - Opening edits of borrowed things write the source's `end`. All other edits write the clip's own phase.
    - It then calls `refreshChain(state, index)`.
  - `setLook(state, index, id, patch)`: writes the marker in its owner clip (`resolve(...).owners[id]`), then `refreshChain` from the owner.
  - `setAbsent(state, index, id, absent)`, `addMarker(state, index, marker, point)` (own marker; opening and end at `point`), `removeMarker(state, index, id)` (own marker only; inherited ones use `setAbsent`).
  - `copyBorrowed(state, index)`: writes the resolved borrowed values into the clip's own fields, as the spec's local copy.
  - `refreshChain(state, index)`: `copyBorrowed` for each following clip whose `source` is the previous one, until the chain ends.
  - `layoutFor(state, index, phase) -> object`: a `parseLayout`-compatible layout for the editor.
- Model changes:
  - Normalize and serialize keep `scene_map` (`normalizeSceneMap`).
  - `requiredFeatures` adds `FEATURE` when any box has `scene_map?.on`.
  - `OWN_FEATURES` includes it.

- [ ] **Step 1: Write the failing tests**

```js
test('resolve matches Python on every shared fixture case', () => {
  for (const c of JSON.parse(readFileSync('tests/fixtures/scene_maps/linking.json', 'utf8'))) {
    const state = model.parseState(JSON.stringify(c.timeline));
    for (const want of c.expect) {
      const got = maps.resolve(state, want.index);
      assert.equal(got.source, want.source, c.name);
      assert.deepEqual(positions(got.opening), want.opening, c.name);
      assert.deepEqual(positions(got.end), want.end, c.name);
    }
  }
});
test('moving a borrowed opening marker writes the previous clip end and refreshes the copy', ...);
test('a cut after refreshChain keeps the last borrowed opening', ...);   // Review Focus 3
test('setAbsent on clip 2 removes the marker from clips 2 and 3 only', ...);   // Review Focus 2
test('enable after a cut copies the nearest earlier map end positions', ...);
test('enable with no earlier map starts empty with no picture', ...);
test('scene_map survives normalize and serialize and adds scene-map-1 only when on', ...);
test('a timeline without scene_map serializes byte-identical to before', ...);
```

- [ ] **Step 2: Run to see them fail** — `node --test tests/web/scene_maps.test.mjs`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement `web/h3c_scene_maps.mjs` and the model hooks.**
- [ ] **Step 4: Run the JS file, then the full suite.** Expected: PASS.
- [ ] **Step 5: Re-stamp the module tags (`node tools/module_versions.mjs --write`) and commit** — `git commit -am "feat: scene map linking and edits in the Studio model"`

---

### Task 6: Stills get the clip's map (Python)

**Files:**
- Modify: `h3_continuity/scene_maps.py`
- Modify: `h3_continuity/stills.py` (`_prepare_pixels`, lines 698–720)
- Modify: `h3_continuity/routes.py` preview handler (fill `stills`)
- Test: `tests/python/test_scene_maps.py` (follow `tests/python/test_scene_map.py`'s use of `recipe` and `stills`)

**Interfaces:**
- Consumes: `resolve` (Task 1); `stills.import_image`, `stills.pin_image`; `scene_map.render`, `resize`, `describe`.
- Produces:
  - `still_layout(timeline, index, target) -> dict | None`: `end` when `target.get('kind') == 'last'`, otherwise `opening`. None when the map is off or has no picture.
  - `still_line(name, layout) -> str`: the exact copy in Global Constraints plus `' ' + scene_map.describe(layout, width, height)` when the map has a camera.
  - In `_prepare_pixels`, after `refs += _recipe_references(body)`:
    - When `still_layout` is not None, render it at 1 MP, then `import_image` and `pin_image`.
    - Append `{'slot': f'still{k}', 'kind': 'image', 'roles': ['blocking map: still{k}'], 'title': 'Scene map', 'scene_map': still_line('@still' + k, layout), **pin}`, where k is the number of recipe references plus 1. The existing loop then adds its line.

- [ ] **Step 1: Write the failing tests**

```python
class StillTest(unittest.TestCase):
    def test_first_frame_still_gets_opening_map_last_to_end(self):
        self.assertEqual(scene_maps.still_layout(parsed, 0, {'kind': 'first'}), scene_maps.resolve(parsed, 0)['opening'])
        self.assertEqual(scene_maps.still_layout(parsed, 0, {'kind': 'last'}), scene_maps.resolve(parsed, 0)['end'])
    def test_still_line_exact_copy(self):
        self.assertTrue(scene_maps.still_line('@still2', layout).startswith(
            '@still2 is a storyboard reference: a top-down plan of this place defining the camera viewpoint and where each '
            'subject stands; nothing from the plan is drawn. The camera stands'))
    def test_prepared_still_request_has_map_reference_last_at_one_megapixel(self):  # prepare(body) via the pixel recipe
    def test_map_off_still_request_unchanged(self):
```

- [ ] **Step 2: Run to see them fail.** Expected: FAIL (`AttributeError: still_layout`).
- [ ] **Step 3: Implement it and fill `stills` in the preview route.**
- [ ] **Step 4: Run `tests.python.test_scene_maps`, `tests.python.test_scene_map`, then the full suite.** Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat: clip scene maps in still requests"`

---

### Task 7: Node-free map editor component (JS)

**Files:**
- Create: `web/h3c_scene_map_editor.mjs`, holding the `SceneMapEditor` class, the STYLE and the helpers moved from `web/h3c_scene_map.js`
- Modify: `web/h3c_scene_map.js` (thin node wrapper)
- Test: existing `tests/web/scene_map_model.test.mjs` stays green; manual check below

**Interfaces:**
- Produces: `new SceneMapEditor(options)`, where `options` is:
  `{layout, image, onLayout(layout), onImage(name), linked() -> bool, background, ghost: layout|null, notice: string, height: number, decorate(markerPanel, marker) -> void, api}`.
  - `root` is the element. Methods: `setLayout(layout, {ghost, notice})`, `setImage(name)`, `draw()`, `destroy()`.
  - `api` is ComfyUI's `api` object, passed in so the module has no `../../scripts` import.
  - `decorate` lets the Studio add the "Not in this clip" and Cast controls to the marker panel.
  - `ghost` is drawn with `drawLayout(..., {editor: false})` at 35% alpha, under the live layout.
- `h3c_scene_map.js` keeps `registerExtension` and the widget plumbing. It builds options from the `layout` and `image` widgets and `node.inputs`, and its behaviour stays the same.

- [ ] **Step 1: Move the class and replace every `this.node` / widget access with the options callbacks.**
- [ ] **Step 2: Add `ghost`, `notice` and `decorate`.**
- [ ] **Step 3: Run the full suite and re-stamp tags.** Expected: PASS.
- [ ] **Step 4: Manual check** after restarting ComfyUI (queue empty first). An existing H3 Scene Map node loads its layout, drags markers, uploads a picture, and saves and reloads the workflow with the layout intact.
- [ ] **Step 5: Commit** — `git commit -am "refactor: scene map editor as a node-free component"`

---

### Task 8: Studio panel and map focus page (JS)

**Files:**
- Create: `web/h3c_scene_map_panel.mjs` (the inspector section body and the focus page content)
- Modify: `web/h3c_timeline_editor.mjs` (a `section('Scene map', …)` appended to `tabPanels.box` after `memoryDetails`, line ~778; refresh in the clip render)
- Modify: `web/h3c_studio.mjs` (`FOCUS` line 17 gains `'map'`; `this.pages.map` content; `focusTitle` text `Scene map · Clip N`)
- Test: `tests/web/scene_map_panel.test.mjs` for the pure parts

**Interfaces:**
- Consumes: Task 5 edits; Task 7 `SceneMapEditor`; route `POST /h3c/scene-map/preview` (Task 4 and Task 6).
- Produces:
  - `panelState(state, index, preview) -> {on, linkedTo: number|null, canSendPicture: bool, sendReason: string, multiShot: bool}`. It is pure and testable:
    - `canSendPicture` follows the preview: `video.mode === 'ref2va'` and no reason starting with `This clip already sends 9`.
    - `multiShot` is true when the clip prompt contains `[Shot 2]`.
  - Inspector section, off by default:
    - Toggling calls `enable` / `disable`, then `editor.commit()`.
    - The body shows a 16:9 preview canvas of the opening layout (`drawLayout`, `editor: false`) and an `Edit map` button that calls `studio.openFocus('map')`.
    - Below that: the "Send map picture to video" checkbox (disabled with `sendReason`), the `multiShot` note `The map applies to the first shot only.`, the still-recipe note `Only the MiniMax still recipe uses the map.` (shown when the recipe adapter is not `pixels`), and a read-only `Added to the prompt` block with the preview's video parts and still lines.
  - Focus page:
    - Opening / End tabs. On a linked clip the Opening tab notice is `Shared with clip N's end`.
    - `SceneMapEditor` with `ghost` set to the other phase, and `decorate` adding `Not in this clip` (inherited markers, calls `setAbsent`) and a Cast picker (entities from `state.bible.entities`, calls `setLook({entity})`).
    - `onLayout` maps the editor's changes to Task 5's `move` / `addMarker` / `removeMarker` / `setLook` by diffing marker ids and positions against `layoutFor`, then calls `editor.commit()`. The preview fetch is debounced 300 ms.
- Read-only timelines (`readOnly.length`) disable every control, as other sections do.

- [ ] **Step 1: Write the failing `panelState` tests** (linked clip, nine-picture reason, T2VA hides the switch, multi-shot note).
- [ ] **Step 2: Run to see them fail.** Expected: FAIL (module not found).
- [ ] **Step 3: Implement the panel, the focus page and the editor section.**
- [ ] **Step 4: Run the full suite and re-stamp tags.** Expected: PASS.
- [ ] **Step 5: Manual check** in the Studio after a restart:
  - Turn the map on for a clip, then undo and redo.
  - Open Edit map, place the camera and two markers, and edit both phases.
  - Add a continuous clip 2, turn its map on, and see it open where clip 1 ended.
  - Drag a marker on clip 2's Opening tab and confirm clip 1's End changed.
  - Turn on Cut for clip 2: nothing moves.
- [ ] **Step 6: Commit** — `git commit -am "feat: scene map section and editor page in the Studio"`

---

### Task 9: Docs, release notes and end-to-end check

**Files:**
- Modify: `README.md` (a Scene maps section under the Studio clip settings), `CHANGELOG.md` (Unreleased: scene maps per clip)
- Modify: the design doc's status line (implemented)

- [ ] **Step 1: Write the README section and the CHANGELOG entry.**
- [ ] **Step 2: Run the full suite.** Expected: every JS and Python test passes. Record the counts.
- [ ] **Step 3: End-to-end check (GPU skill: request, wait, free ComfyUI VRAM, finish).**
  - Rebuild the shot 22 test story with a Studio map in place of the hand-made `image23` and "Send map picture to video" on. Confirm the preview's video parts match the passing render's lines.
  - Hand the story to the user to render.
  - Build the two-clip continuous story for the user, with clip 2 opening where clip 1 ends.
- [ ] **Step 4: Commit** — `git commit -am "docs: scene maps per Studio clip"`. Ask the user before pushing to [PR #87](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio/pull/87) or tagging a release.
