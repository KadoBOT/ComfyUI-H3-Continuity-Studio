"""Tests for continuing-box carry-through endings, structured exit state, pacing under-fill,
clean-frame screen-FX hygiene, audio crackle restrictions, camera compiler fixes, and prompt linting."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from h3_continuity import (
    h3_prompt_compile as compiler,
    h3_prompt_ir as prompt_ir,
    h3_prompt_validate as validate,
    prompt_fields,
    still_prompt_preparation,
    story_audio,
    story_bible_write,
    story_fast,
    story_idea_refs,
    story_instructions,
    story_prompts,
    story_stages,
    timeline as rules,
)


def _context(frames=102, carried=0, mode="T2VA", refs=(), first="", last="", image_guidance=()):
    slots = rules.Slots(
        "ref2va" if mode == "Ref2VA" else "t2va",
        list(refs),
        [],
        first,
        last,
        {name: f"<Picture {i}>" for i, name in enumerate(refs, 1)},
    )
    return prompt_ir.PromptContext(mode, slots, frames, carried, tuple(image_guidance))


def _reply(
    *,
    style="Live-action modern digital cinematography, clean full-frame image, even illumination.",
    ending_state="Mira steps onto the sunlit curb",
    continues_next=False,
    shots=None,
    terminal_state=None,
    soundscape="Quiet wind.",
    music="N/A",
):
    if shots is None:
        shot = {
            "start_ms": 0,
            "cut": False,
            "visible_people": ["Mira"],
            "subjects": [],
            "composition": "Medium wide shot of Mira walking along the sidewalk in even morning daylight.",
            "actions": [
                {
                    "start_ms": 0,
                    "end_ms": 4250,
                    "description": "Mira walks steadily forward along the sidewalk toward the crosswalk.",
                    "sound": "Quiet footsteps.",
                }
            ],
            "camera": "The camera tracks steadily alongside Mira at a smooth walking pace.",
            "dialogue": [],
        }
        if ending_state:
            shot["ending_state"] = ending_state
        if continues_next:
            shot["continues_next"] = True
        shots = [shot]
    if terminal_state is None:
        terminal_state = {
            "setting": "City sidewalk beside a quiet crosswalk",
            "lighting": "Even morning overcast daylight, neutral 5600K, moderate exposure",
            "positions": "Mira mid-stride on the right edge of the sidewalk facing right",
            "camera_motion": "Medium wide tracking shot moving right at steady walking speed",
            "subject_motion": "Mira walking steadily right at a natural walking cadence",
            "props": "Canvas tote slung over her left shoulder",
        }
    return {
        "subject_updates": [],
        "style": style,
        "shots": shots,
        "overall_soundscape": soundscape,
        "non_diegetic_music": music,
        "audio_references": [],
        "terminal_state": terminal_state,
    }


def _story_ctx(boxes, *, guide="", idea="A woman walks down a quiet street.", shared="", regenerate=False):
    tl_boxes = [
        rules.Box(
            id=b.id,
            frames=b.frames,
            prompt=b.prompt,
            cut=b.fresh if i > 0 else False,
            seed=i + 1,
            first="",
            last="",
            new_scene=b.new_scene,
        )
        for i, b in enumerate(boxes)
    ]
    tl = rules.Timeline(prompt=shared, boxes=tl_boxes)
    return SimpleNamespace(
        idea=idea,
        guide=guide,
        shared=shared,
        context_frames=39,
        timeline=tl,
        boxes=boxes,
        references=[],
        descriptions={},
        regenerate=regenerate,
        renderer="video",
        image_model="",
        template=None,
        pictures=False,
        idea_images=[],
        idea_descriptions={},
        idea_references={},
        label=lambda name: f"@{name}",
    )


class ContinuingBoxEndingTest(unittest.TestCase):
    def test_continuing_box_emits_carry_through_target_not_freeze_tail(self):
        ctx_ir = _context(frames=102, carried=0)
        box1 = story_prompts.StoryBox("b1", 1, 102, 0, True, "", "", "", "write")
        box2 = story_prompts.StoryBox("b2", 2, 72, 39, False, "", "", "", "write")
        ctx = _story_ctx([box1, box2])
        reply = _reply(ending_state="Mira steps onto the sunlit curb", continues_next=True)
        text, _ = story_fast.compile_prompt(reply, ctx, None, 0, ctx_ir, {})
        self.assertIn(
            "By 00:04.250, reach Mira steps onto the sunlit curb while maintaining steady ongoing motion and camera pace; do not pause or stop early.",
            text,
        )
        self.assertNotIn("Keep that reached state; do not begin a later action.", text)

    def test_cut_final_and_explicit_hold_keep_reached_state_tail(self):
        ctx_ir = _context(frames=102, carried=0)
        box1 = story_prompts.StoryBox("b1", 1, 102, 0, True, "", "", "", "write")
        box2_cut = story_prompts.StoryBox("b2", 2, 72, 0, True, "", "", "", "write")
        box2_cont = story_prompts.StoryBox("b2", 2, 72, 39, False, "", "", "", "write")
        cut_text, _ = story_fast.compile_prompt(
            _reply(ending_state="Mira steps onto the sunlit curb"),
            _story_ctx([box1, box2_cut]),
            None,
            0,
            ctx_ir,
            {},
        )
        self.assertIn("By 00:04.250, end this action with: Mira steps onto the sunlit curb. Keep that reached state; do not begin a later action.", cut_text)

        hold_text, _ = story_fast.compile_prompt(
            _reply(ending_state="Mira holds still by the doorway.", continues_next=True),
            _story_ctx([box1, box2_cont]),
            None,
            0,
            ctx_ir,
            {},
            continues_next=True,
        )
        self.assertIn("Keep that reached state; do not begin a later action.", hold_text)
        self.assertNotIn("do not pause or stop early", hold_text)

        # Final box (no next box) also keeps reached-state tail.
        final_text, _ = story_fast.compile_prompt(
            _reply(ending_state="Mira reaches the bus stop"),
            _story_ctx([box1]),
            None,
            0,
            ctx_ir,
            {},
        )
        self.assertIn("Keep that reached state; do not begin a later action.", final_text)

    def test_stages_freeze_expand_and_validate_source_round_trip_continues_next(self):
        plan_stages = [{"duration_ms": 4000, "cut": False, "action": "Mira walks along the path.", "dialogue": []}]
        frozen = story_stages.freeze(plan_stages, 102, 0, {}, ending="Mira reaches the gate", continues_next=True)
        self.assertTrue(frozen["stage_1"]["continues_next"])
        stage_reply = {
            "subject_updates": [],
            "style": "Live-action modern digital cinematography, clean full-frame image.",
            "overall_soundscape": [],
            "non_diegetic_music": {"instruments": [], "tempo": "moderate", "level": "normal"},
            "audio_references": [],
            "terminal_state": _reply()["terminal_state"],
            "stages": {
                "stage_1": {
                    "visible_people": ["Mira"],
                    "subjects": [],
                    "composition": "Medium wide shot of Mira walking.",
                    "camera": "The camera tracks steadily.",
                    "action": {"sound": []},
                    "dialogue": {},
                }
            },
        }
        expanded = story_stages.expand(stage_reply, frozen)
        self.assertTrue(expanded["shots"][0]["continues_next"])
        story_stages.validate_source(expanded, frozen, 102, 0)

        tampered = json.loads(json.dumps(expanded))
        tampered["shots"][0]["continues_next"] = False
        with self.assertRaisesRegex(ValueError, "continuation flag"):
            story_stages.validate_source(tampered, frozen, 102, 0)

    def test_legacy_saved_source_without_extended_terminal_state_or_continues_next_still_compiles(self):
        legacy_reply = _reply(
            ending_state="Mira reaches the gate",
            terminal_state={"setting": "Quiet garden path", "positions": "Mira at the gate", "props": "Brass key"},
        )
        bible = {"entities": [], "next": 1, "style": {"look": "Live-action modern digital cinematography."}}
        source = {
            "reply": legacy_reply,
            "frame": {
                "mode": "T2VA",
                "slots": {"mode": "t2va", "references": [], "audios": [], "first": "", "last": ""},
                "frames": 102,
                "carried": 0,
                "schedule": {"entities": [], "place": None},
                "left_out": [],
                "audio": [],
                "wording": {},
            },
        }
        schema = story_bible_write.source_schema(source, bible, ["b1"], 0)
        validate.shape(legacy_reply, schema)
        text, _ = story_bible_write.compile_source(source, bible, ["b1"], 0)
        self.assertIn("Keep that reached state; do not begin a later action.", text)

        source_cont = json.loads(json.dumps(source))
        source_cont["frame"]["continues_next"] = True
        text_cont, _ = story_bible_write.compile_source(source_cont, bible, ["b1", "b2"], 0)
        self.assertIn("while maintaining steady ongoing motion and camera pace; do not pause or stop early.", text_cont)


class ExitStateCarryAndCompilerTest(unittest.TestCase):
    def test_normal_write_story_carries_structured_exit_state_and_duration_into_next_box(self):
        box1 = story_prompts.StoryBox("b1", 1, 102, 0, True, "", "", "", "write")
        box2 = story_prompts.StoryBox("b2", 2, 72, 39, False, "", "", "", "write")
        ctx = _story_ctx([box1, box2], regenerate=False)
        plan = SimpleNamespace(
            title="Walk",
            sheet="Sheet",
            beats=[
                SimpleNamespace(beat="Mira walks toward the corner.", on_screen=["Mira"], ends="Mira at the corner."),
                SimpleNamespace(beat="Mira turns the corner.", on_screen=["Mira"], ends="Mira down the alley."),
            ],
        )
        ctx_ir_1 = _context(frames=102, carried=0)
        _, details_1 = story_fast.compile_prompt(_reply(continues_next=True), ctx, plan, 0, ctx_ir_1, {})
        self.assertIn("lighting", details_1["terminal_state"])
        self.assertIn("camera_motion", details_1["terminal_state"])
        self.assertIn("subject_motion", details_1["terminal_state"])
        self.assertEqual(details_1["terminal_state"]["new_ms"], 4250)

        # Box 1 prompt tells writer next box continues seamlessly.
        msg1 = story_fast.messages(ctx, plan, 0, {}, ctx_ir_1, {}, {})[1]["content"]
        self.assertIn("Next box continues seamlessly", msg1)
        self.assertIn("do not brake to a pause", msg1)

        # Box 2 receives Box 1's exit lighting, camera_motion, subject_motion, and duration even with regenerate=False.
        ctx_ir_2 = _context(frames=111, carried=39)
        msg2 = story_fast.messages(ctx, plan, 1, {}, ctx_ir_2, {}, {"b1": details_1})[1]["content"]
        self.assertIn("4250 ms new time", msg2)
        self.assertIn("Even morning overcast daylight, neutral 5600K, moderate exposure", msg2)
        self.assertIn("Medium wide tracking shot moving right at steady walking speed", msg2)
        self.assertIn("Mira walking steadily right at a natural walking cadence", msg2)

        # Bible continuity log _ending includes the new structured exit fields too.
        log_tail = story_bible_write._ending(_reply())
        self.assertIn("Even morning overcast daylight", log_tail)
        self.assertIn("Medium wide tracking shot", log_tail)
        self.assertIn("Mira walking steadily right", log_tail)

    def test_h3_prompt_compile_continuation_and_camera_not_dropped(self):
        self.assertIn("lighting", compiler.CONTINUATION)
        self.assertIn("exposure", compiler.CONTINUATION)
        self.assertIn("camera speed", compiler.CONTINUATION)
        self.assertIn("clean frame surface", compiler.CONTINUATION)

        ctx_ir = _context(frames=102, carried=39)
        data = {
            "style": "Live-action modern digital cinematography, clean full-frame image.",
            "speakers": [],
            "shots": [
                {
                    "number": 1,
                    "cut": False,
                    "start_ms": 0,
                    "composition": "Medium shot of a woman facing the camera in even daylight.",
                    "actions": ["She glances directly toward the camera while stepping forward."],
                    "references": [],
                    "camera": {"type": "Push In", "amplitude": "small", "speed": "slow"},
                    "dialogue": [],
                    "diegetic_audio": [],
                }
            ],
            "overall_soundscape": "Quiet street.",
            "non_diegetic_music": "N/A",
        }
        prompt = compiler.compile_prompt(data, ctx_ir)
        self.assertIn(compiler.CONTINUATION, prompt)
        self.assertIn("The camera pushes in with small amplitude at slow speed.", prompt)

        # When prose already moves the camera without stating speed/amplitude, structured speed/amplitude still lands.
        data["shots"][0]["actions"] = ["The camera tracks her as she walks past the storefront."]
        data["shots"][0]["camera"] = {"type": "Tracking Shot", "amplitude": "large", "speed": "slow"}
        prompt2 = compiler.compile_prompt(data, ctx_ir)
        self.assertIn("with large amplitude at slow speed.", prompt2)

    def test_story_stages_underfill_safeguard(self):
        short_stage = [{"duration_ms": 1000, "cut": False, "action": "Mira raises her hand.", "dialogue": []}]
        with self.assertRaisesRegex(ValueError, "stretching a brief move into slow motion"):
            story_stages.freeze(short_stage, 102, 0, {})

        # Explicit holds are still permitted in long boxes.
        hold_stage = [{"duration_ms": 1000, "cut": False, "action": "Mira holds still beside the window.", "dialogue": []}]
        frozen_hold = story_stages.freeze(hold_stage, 102, 0, {})
        self.assertEqual(frozen_hold["stage_1"]["end_frame"], 102)

        # Adequately filled stages pass normally.
        natural_stage = [{"duration_ms": 3000, "cut": False, "action": "Mira crosses the courtyard.", "dialogue": []}]
        frozen_ok = story_stages.freeze(natural_stage, 102, 0, {})
        self.assertEqual(frozen_ok["stage_1"]["end_frame"], 102)

    def test_from_saved_fallback_scales_to_box_frames_and_freezes_without_underfill_crash(self):
        legacy = story_stages.from_saved("Mira walks across the quiet room.", None, "", frames=102)
        frozen = story_stages.freeze(legacy, 102, 0, {})
        self.assertEqual(frozen["stage_1"]["end_frame"], 102)

        # Multi-line legacy fallback with dialogue also scales to box frames cleanly.
        legacy_dlg = story_stages.from_saved(
            "Mira speaks twice.", None, "<d>[English] Hello.</d> <d>[English] Goodbye.</d>", frames=120
        )
        frozen_dlg = story_stages.freeze(legacy_dlg, 120, 0, {})
        self.assertEqual(frozen_dlg["stage_2"]["end_frame"], 120)

    def test_planner_instructions_have_natural_speed_continuity_and_no_forced_light_change(self):
        plan_text = story_instructions.planner(planning=True, styled=False)
        self.assertNotIn("handheld 35 mm", plan_text)
        self.assertNotIn("framing, expression or light", plan_text)
        self.assertIn("natural real-world speed", plan_text)
        self.assertIn("Keep lighting and exposure consistent across same-scene boxes", plan_text)
        self.assertIn("clean full-frame image", plan_text)
        self.assertIn("even edge-to-edge illumination", story_prompts.H3_WRITING_RULES)


class ScreenFxHygieneAudioAndLinterTest(unittest.TestCase):
    def test_audio_crackling_restricted_to_fire_electronic_machinery(self):
        self.assertEqual(
            story_audio.effects([{"kind": "fire", "level": "quiet", "quality": "crackling"}]),
            "Quiet fire crackling.",
        )
        self.assertEqual(
            story_audio.effects([{"kind": "electronic", "level": "faint", "quality": "crackling"}]),
            "Faint crackling electronic tones.",
        )
        self.assertEqual(
            story_audio.effects([{"kind": "machinery", "level": "normal", "quality": "crackling"}]),
            "Crackling mechanical sounds.",
        )
        for bad_kind in ("room_tone", "wind", "rain", "fabric"):
            with self.subTest(kind=bad_kind), self.assertRaisesRegex(ValueError, 'Audio quality "crackling"'):
                story_audio.effects([{"kind": bad_kind, "level": "quiet", "quality": "crackling"}])

    def test_idea_refs_still_prep_and_music_video_template_enforce_clean_frame_hygiene(self):
        self.assertIn("vignetting", story_idea_refs.GUIDANCE)
        self.assertIn("film grain", story_idea_refs.GUIDANCE)
        self.assertIn("overlays", story_idea_refs.PLANNING)
        self.assertIn("Preserve the scene's established lighting, exposure", still_prompt_preparation.DEFAULT_INSTRUCTIONS)
        self.assertIn("no\nvignette", still_prompt_preparation.DEFAULT_INSTRUCTIONS)
        self.assertNotIn("Enrich expression, composition, texture, light and color", still_prompt_preparation.DEFAULT_INSTRUCTIONS)

        template_text = (Path(__file__).resolve().parents[2] / "examples" / "templates" / "music-video.md").read_text(encoding="utf-8")
        self.assertNotIn("A change of texture", template_text)
        self.assertNotIn("brighter light", template_text)
        self.assertNotIn("the light is lower", template_text)
        self.assertIn("Keep lighting and exposure consistent", template_text)

    def test_screen_fx_linter_catches_unsolicited_fx_and_respects_allowlist_and_negation(self):
        htfu_style = "Live-action 35mm anamorphic cinematography with subtle film grain and soft lens flare."
        warnings = validate.lint_screen_fx(htfu_style)
        tokens = {item["token"] for item in warnings}
        self.assertEqual(tokens, {"35mm", "anamorphic", "grain", "lens flare"})

        # Explicit user request bypasses matching tokens while still catching unrequested ones.
        filtered = validate.lint_screen_fx(
            htfu_style + " Heavy vignette and VHS overlay.",
            allowed_context="Shoot on 35mm anamorphic with film grain.",
        )
        self.assertEqual({item["token"] for item in filtered}, {"lens flare", "vignette", "VHS", "overlay"})

        # Negated clean-frame guardrails (including compiled image_guidance and multiline rules) must not false-positive.
        clean = (
            "Live-action modern digital cinematography, clean full-frame image with even illumination, "
            "no vignette, film grain, crackle, scratches, lens flare, or overlays. Quiet fire crackling."
        )
        self.assertEqual(validate.lint_screen_fx(clean), [])
        compiled_guidance = (
            "<Subject 2> is visual guidance from @image17: Match warm palette. "
            "Do not reproduce the source images, their layouts, depicted people, objects, text, "
            "borders, vignetting, film grain, crackle, lens flares or overlays."
        )
        self.assertEqual(validate.lint_screen_fx(compiled_guidance), [])
        self.assertEqual(validate.lint_screen_fx(story_prompts.H3_WRITING_RULES), [])
        self.assertEqual(validate.lint_screen_fx(still_prompt_preparation.DEFAULT_INSTRUCTIONS), [])
        self.assertEqual(validate.lint_screen_fx(story_idea_refs.GUIDANCE), [])

        # Comma splice after "No music," must still flag real FX triggers.
        self.assertEqual(
            {w["token"] for w in validate.lint_screen_fx("No music, 35mm film grain and heavy vignette.")},
            {"35mm", "grain", "vignette"},
        )

        # Non-fire crackle IS flagged.
        self.assertEqual(
            [w["token"] for w in validate.lint_screen_fx("Subtle vinyl crackle and vintage CRT flicker.")],
            ["crackle", "vintage", "CRT", "flicker"],
        )

    def test_continuation_pair_linter_avoids_lighting_false_positives_on_wardrobe_and_props(self):
        prev_prompt = (
            "subject_definitions:\n<Subject 1> is Mira with dark hair wearing a dark coat.\n\n"
            "detailed_description:\nClean modern digital cinematography, even overcast daylight.\n"
            "[Shot 1] Medium shot of <Subject 1> in her dark coat walking steadily along the sidewalk."
        )
        next_prompt = (
            "subject_definitions:\n<Subject 1> is Mira with dark hair holding a bright red umbrella.\n\n"
            "detailed_description:\nClean modern digital cinematography, even overcast daylight.\n"
            "[Shot 1] Medium shot of <Subject 1> holding a bright red umbrella while walking steadily."
        )
        self.assertEqual(
            validate.lint_continuation_pair(prev_prompt, next_prompt, same_scene=True, continuous=True),
            [],
        )

    def test_prompt_fields_request_uses_track_previous_box_on_multitrack_timeline(self):
        # Real serialized multi-track Timeline JSON: track/start/frames live on each box, requires timeline-tracks-1.
        timeline = json.dumps({
            "version": 1,
            "requires": ["timeline-tracks-1"],
            "tracks": [
                {"id": "t1", "kind": "video", "name": "Main"},
                {"id": "t2", "kind": "video", "name": "Cutaway"},
            ],
            "boxes": [
                {"id": "b1", "frames": 48, "exact": True, "seed": 1, "track": "t1", "start": 0,
                 "prompt": "detailed_description:\n[Shot 1] Wide shot walking slowly in warm sunlight."},
                {"id": "b2", "frames": 48, "exact": True, "seed": 2, "track": "t2", "start": 0,
                 "prompt": "detailed_description:\n[Shot 1] Medium shot in even daylight."},
                {"id": "b3", "frames": 48, "exact": True, "seed": 3, "track": "t1", "start": 48,
                 "cut": False, "new_scene": False,
                 "prompt": "detailed_description:\n[Shot 1] Tight close-up sprinting fast in cool fluorescent light."},
            ],
        })
        # b3's predecessor on track t1 is b1 (not b2!), so framing, speed, and lighting drift are caught.
        view = prompt_fields.request({"timeline": timeline, "box": "b3"})
        codes = {item["code"] for item in view["warnings"]}
        self.assertEqual(codes, {"continuation_framing_jump", "continuation_speed_flip", "lighting_drift"})

        # Out-of-order boxes[] where index 0 starts at 48 after index 1 starting at 0 on the same track.
        out_of_order = json.dumps({
            "version": 1,
            "requires": ["timeline-tracks-1"],
            "tracks": [{"id": "t1", "kind": "video", "name": "Main"}],
            "boxes": [
                {"id": "b_later", "frames": 48, "exact": True, "seed": 2, "track": "t1", "start": 48,
                 "cut": False, "new_scene": False,
                 "prompt": "detailed_description:\n[Shot 1] Tight close-up sprinting fast in cool fluorescent light."},
                {"id": "b_first", "frames": 48, "exact": True, "seed": 1, "track": "t1", "start": 0,
                 "prompt": "detailed_description:\n[Shot 1] Wide shot walking slowly in warm sunlight."},
            ],
        })
        ooo_codes = {item["code"] for item in prompt_fields.request({"timeline": out_of_order, "box": "b_later"})["warnings"]}
        self.assertEqual(ooo_codes, {"continuation_framing_jump", "continuation_speed_flip", "lighting_drift"})

        # Gapped clips on the same track (b1 [0,48), b2 [60,108)) have no adjacent predecessor -> no pair warnings.
        gapped = json.dumps({
            "version": 1,
            "requires": ["timeline-tracks-1"],
            "tracks": [{"id": "t1", "kind": "video", "name": "Main"}],
            "boxes": [
                {"id": "b1", "frames": 48, "exact": True, "seed": 1, "track": "t1", "start": 0,
                 "prompt": "detailed_description:\n[Shot 1] Wide shot walking slowly in warm sunlight."},
                {"id": "b2", "frames": 48, "exact": True, "seed": 2, "track": "t1", "start": 60,
                 "cut": False, "new_scene": False,
                 "prompt": "detailed_description:\n[Shot 1] Tight close-up sprinting fast in cool fluorescent light."},
            ],
        })
        self.assertEqual(prompt_fields.request({"timeline": gapped, "box": "b2"})["warnings"], [])

    def test_opening_cue_framing_preserves_opening_not_destination_or_pull_out(self):
        cu_prev = "detailed_description:\n[Shot 1] Close-up on Mira's face."
        cu_to_wide = "detailed_description:\n[Shot 1]\nComposition: Close-up on Mira's face as the camera pulls out to a wide shot."
        cu_pull_out = "detailed_description:\n[Shot 1]\nComposition: Close-up on her face as the camera pulls out."
        self.assertEqual(validate.lint_continuation_pair(cu_prev, cu_to_wide, same_scene=True, continuous=True), [])
        self.assertEqual(validate.lint_continuation_pair(cu_prev, cu_pull_out, same_scene=True, continuous=True), [])

        wide_prev = "detailed_description:\n[Shot 1] Wide shot of the courtyard."
        wide_to_cu = "detailed_description:\n[Shot 1]\nComposition: Wide shot of the courtyard pushing in into a close-up."
        self.assertEqual(validate.lint_continuation_pair(wide_prev, wide_to_cu, same_scene=True, continuous=True), [])

    def test_bible_compile_source_forwards_allowed_context_for_guided_fx(self):
        bible = {"entities": [], "next": 1, "style": {"look": "Live-action 35mm anamorphic with subtle film grain."}}
        source = {
            "reply": _reply(style="Live-action 35mm anamorphic with subtle film grain."),
            "frame": {
                "mode": "T2VA",
                "slots": {"mode": "t2va", "references": [], "audios": [], "first": "", "last": ""},
                "frames": 102,
                "carried": 0,
                "schedule": {"entities": [], "place": None},
                "left_out": [],
                "audio": [],
                "wording": {},
            },
        }
        unsolicited_notes = []
        story_bible_write.compile_source(source, bible, ["b1"], 0, notes=unsolicited_notes)
        self.assertTrue(any("35mm" in note for note in unsolicited_notes))

        guided_notes = []
        story_bible_write.compile_source(
            source, bible, ["b1"], 0, notes=guided_notes,
            allowed_context="Shoot on 35mm anamorphic film with subtle film grain.",
        )
        self.assertFalse(any("Unsolicited screen-FX" in note for note in guided_notes))

    def test_continuation_pair_linter_catches_framing_speed_and_lighting_contradictions(self):
        prev_prompt = (
            "detailed_description:\n"
            "Clean modern digital cinematography, warm golden sunlight.\n"
            "[Shot 1] Wide shot pulling out as Mira walks slowly across the sunlit plaza."
        )
        bad_next = (
            "detailed_description:\n"
            "Clean modern digital cinematography, cool blue fluorescent lighting.\n"
            "[Shot 1] Tight close-up as Mira sprints rapidly past the door."
        )
        warnings = validate.lint_continuation_pair(prev_prompt, bad_next, same_scene=True, continuous=True)
        codes = {item["code"] for item in warnings}
        self.assertEqual(codes, {"continuation_framing_jump", "continuation_speed_flip", "lighting_drift"})

        # A cut within the same scene allows framing and speed changes, but still catches lighting drift.
        cut_warnings = validate.lint_continuation_pair(prev_prompt, bad_next, same_scene=True, continuous=False)
        self.assertEqual([w["code"] for w in cut_warnings], ["lighting_drift"])

        # A new scene cut allows lighting change too.
        self.assertEqual(
            validate.lint_continuation_pair(prev_prompt, bad_next, same_scene=False, continuous=False),
            [],
        )

        # Real Heavy Things Fall Up calibration: wide/pull-out -> "tight golden-lit framing" caught;
        # smooth push-in destination ("into an intimate close-up") and pull-out from "Initial state: Close-up" do not FP.
        b033 = "detailed_description:\n[Shot 1] Wide shot pulling out across the golden street."
        b034 = "detailed_description:\n[Shot 1] Holding a tight golden-lit framing on her face."
        self.assertIn(
            "continuation_framing_jump",
            {w["code"] for w in validate.lint_continuation_pair(b033, b034, same_scene=True, continuous=True)},
        )
        b011 = "detailed_description:\n[Shot 1] The camera pulls out steadily across the room."
        b012 = "detailed_description:\n[Shot 1] The camera pushes in gently into an intimate close-up."
        b013 = "detailed_description:\n[Shot 1] The camera pulls out gently.\nInitial state: Close-up on her hands."
        self.assertNotIn(
            "continuation_framing_jump",
            {w["code"] for w in validate.lint_continuation_pair(b011, b012, same_scene=True, continuous=True)},
        )
        self.assertNotIn(
            "continuation_framing_jump",
            {w["code"] for w in validate.lint_continuation_pair(b012, b013, same_scene=True, continuous=True)},
        )

    def test_prompt_fields_inspect_and_request_surface_lint_warnings_preserving_summary(self):
        timeline = json.dumps({
            "version": 1,
            "boxes": [
                {
                    "id": "b1",
                    "prompt": "detailed_description:\n[Shot 1] Wide shot in warm tungsten light, walking slowly.",
                },
                {
                    "id": "b2",
                    "cut": False,
                    "new_scene": False,
                    "prompt": "detailed_description:\n35mm film grain.\n[Shot 1] Tight close-up in cool overcast light, sprinting fast.",
                },
            ],
        })
        view = prompt_fields.request({"timeline": timeline, "box": "b2"})
        self.assertEqual(
            set(view["summary"]),
            {"shots", "cues", "advanced_cues", "dialogue", "unstructured_text"},
        )
        codes = {item["code"] for item in view["warnings"]}
        self.assertIn("unsolicited_screen_fx", codes)
        self.assertIn("continuation_framing_jump", codes)
        self.assertIn("continuation_speed_flip", codes)
        self.assertIn("lighting_drift", codes)

    def test_compile_prompt_reports_unsolicited_fx_warnings_and_bypasses_guided_fx(self):
        ctx_ir = _context(frames=102, carried=0)
        box = story_prompts.StoryBox("b1", 1, 102, 0, True, "", "", "", "write")
        notes = []
        story_fast.compile_prompt(
            _reply(style="Live-action 35mm anamorphic with subtle film grain."),
            _story_ctx([box], guide="Keep a clean modern look."),
            None,
            0,
            ctx_ir,
            {},
            notes=notes,
        )
        self.assertTrue(any("35mm" in note for note in notes))
        self.assertTrue(any("grain" in note for note in notes))

        allowed_notes = []
        story_fast.compile_prompt(
            _reply(style="Live-action 35mm anamorphic with subtle film grain."),
            _story_ctx([box], guide="Shoot on 35mm anamorphic film with grain."),
            None,
            0,
            ctx_ir,
            {},
            notes=allowed_notes,
        )
        self.assertFalse(any("Unsolicited screen-FX" in note for note in allowed_notes))


if __name__ == "__main__":
    unittest.main()
