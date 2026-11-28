"""Tests for upgraded check_frames and story_check metrics:
- 4.5 L* lightness threshold and adjacent-box luma step
- Symmetric corner-vs-edge vignette and vignette step detection
- Smooth-region high-frequency grain/crackle spike detection
- Native-FPS 1-step seam freeze and exit-vs-entry motion speed ratio
- Multi-track rules.previous_index lookup and Vision QC screen-FX / exposure instructions
"""

from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

from h3_continuity import check_frames, media, story_check, timeline as rules

H, W = 160, 288


def _rgb(luma):
    return np.repeat(np.clip(luma, 0, 255).astype(np.uint8)[..., None], 3, axis=2)


def _flat(level=140.0):
    return _rgb(np.full((H, W), level))


def _gradient():
    y, x = np.mgrid[0:H, 0:W]
    return _rgb(60.0 + 0.4 * x + 0.35 * y)


def _vignetted(base=185.0, strength=0.35):
    y, x = np.mgrid[0:H, 0:W]
    nx = (x - (W - 1) / 2.0) / ((W - 1) / 2.0)
    ny = (y - (H - 1) / 2.0) / ((H - 1) / 2.0)
    r2 = nx * nx + ny * ny
    return _rgb(base * (1.0 - strength * np.clip(r2 / 2.0, 0.0, 1.0)))


def _single_corner_object(base=160.0):
    img = np.full((H, W), base)
    img[:H // 4, :W // 4] = 20.0
    return _rgb(img)


def _centered_edge_lamp(base=140.0):
    img = np.full((H, W), base)
    img[:H // 6, W // 3:2 * W // 3] = 235.0
    return _rgb(img)


def _interior_corridor(base=190.0):
    """Bright doorway center flanked by uniform dark vertical side walls (must NOT trigger radial vignette)."""
    img = np.full((H, W), base)
    img[:, :W // 4] = 35.0
    img[:, 3 * W // 4:] = 35.0
    return _rgb(img)


def _crisp_edges():
    img = np.full((H, W), 80.0)
    img[:, W // 2:] = 200.0
    img[H // 2:, :] = 140.0
    return _rgb(img)


def _crackled(base=140.0, sigma=12.0, seed=7):
    rng = np.random.default_rng(seed)
    return _rgb(np.full((H, W), base) + rng.normal(0.0, sigma, (H, W)))


def _sliding_frames(count, step_px=4, seed=1):
    rng = np.random.default_rng(seed)
    span = W + count * max(step_px, 1) + 16
    canvas = rng.integers(0, 255, (H, span), dtype=np.uint8)
    return [np.repeat(canvas[:, i * step_px:i * step_px + W, None], 3, axis=2) for i in range(count)]


class LightnessAndAdjacentLumaTest(unittest.TestCase):
    def test_lightness_step_lowered_to_4_5(self):
        self.assertEqual(check_frames.LIGHTNESS_STEP, 4.5)
        base = np.array([50.0, 0.0, 0.0])
        self.assertEqual(check_frames.drift_words(np.array([53.0, 0.0, 0.0]), base), "")
        self.assertIn("brighter", check_frames.drift_words(np.array([55.0, 0.0, 0.0]), base))
        self.assertIn("darker", check_frames.drift_words(np.array([45.0, 0.0, 0.0]), base))

    def test_adjacent_luma_step_detects_local_brightness_jump(self):
        step = check_frames.adjacent_luma_step([_flat(120.0)], [_flat(150.0)])
        self.assertGreater(step, check_frames.LIGHTNESS_STEP)
        small = check_frames.adjacent_luma_step([_flat(120.0)], [_flat(122.0)])
        self.assertLess(abs(small), check_frames.LIGHTNESS_STEP)


class VignetteAndCrackleTest(unittest.TestCase):
    def test_vignette_rejects_flat_gradients_single_corner_and_center_lamp(self):
        for name, frame in (
            ("flat", _flat()),
            ("linear_gradient", _gradient()),
            ("single_corner_object", _single_corner_object()),
            ("centered_edge_lamp", _centered_edge_lamp()),
            ("interior_corridor", _interior_corridor()),
        ):
            with self.subTest(case=name):
                self.assertEqual(check_frames.vignette_score(frame), 0.0)

    def test_vignette_detects_symmetric_corner_darkening_and_step(self):
        clean = _flat(185.0)
        vig = _vignetted(base=185.0, strength=0.45)
        score = check_frames.vignette_score(vig)
        self.assertGreater(score, check_frames.VIGNETTE_THRESHOLD)
        step = check_frames.vignette_step([clean], [vig])
        self.assertGreater(step, check_frames.VIGNETTE_STEP)

    def test_crackle_detects_smooth_area_grain_without_flagging_crisp_edges(self):
        for name, frame in (("flat", _flat()), ("gradient", _gradient()), ("crisp_edges", _crisp_edges())):
            with self.subTest(case=name):
                self.assertLess(check_frames.crackle_score(frame), 0.002)
        noisy = _crackled(sigma=10.0)
        self.assertGreater(check_frames.crackle_score(noisy), check_frames.CRACKLE_THRESHOLD)

        # 3x upscaled grain clumps (~3000px wide) still score above threshold via resolution normalization.
        clumps = _crackled(sigma=10.0, seed=11).repeat(4, axis=0).repeat(4, axis=1)  # 640x1152 -> test wider 3x
        upscaled = _crackled(sigma=10.0, seed=11).repeat(3, axis=0).repeat(4, axis=1)  # 480x1152 (> 1024px)
        self.assertGreater(check_frames.crackle_score(upscaled), check_frames.CRACKLE_THRESHOLD)
        self.assertGreater(check_frames.crackle_score(clumps), check_frames.CRACKLE_THRESHOLD)


class NativeFpsFreezeAndSpeedRatioTest(unittest.TestCase):
    def test_seam_freeze_detects_single_step_tail_seam_and_head_duplicates(self):
        seq = _sliding_frames(12, step_px=4, seed=3)
        smooth = check_frames.seam_freeze(seq[:6], seq[6:])
        self.assertFalse(smooth["frozen"])

        # Tail last-frame duplicate (mirrors 48fps RTX frame-generation freeze on final frame).
        tail_dup = list(seq[:5]) + [seq[4]]
        res_tail = check_frames.seam_freeze(tail_dup, seq[5:11])
        self.assertTrue(res_tail["frozen"])
        self.assertTrue(res_tail["tail_duplicate"])

        # Low per-frame step at 48fps (0.7 raw MAD/frame -> 1.4 normalized 24fps MAD) still catches duplicate tail!
        subtle = [_rgb(np.full((H, W), 120.0) + np.sin(np.linspace(0, 12, W))[None, :] * 12.0 + 0.7 * i) for i in range(6)]
        subtle_tail = list(subtle[:5]) + [subtle[4].copy()]
        res_48 = check_frames.seam_freeze(subtle_tail, subtle, fps=48)
        self.assertTrue(res_48["frozen"])
        self.assertTrue(res_48["tail_duplicate"])

        # Exact duplicate across the seam.
        res_seam = check_frames.seam_freeze(seq[:6], [seq[5]] + seq[6:11])
        self.assertTrue(res_seam["frozen"])
        self.assertTrue(res_seam["seam_duplicate"])

        # Static shots must never false-positive.
        still = _flat(120.0)
        self.assertFalse(check_frames.seam_freeze([still] * 6, [still] * 6)["frozen"])

    def test_motion_speed_ratio_detects_speed_discontinuity_and_ignores_pure_exposure_ramps(self):
        # Same speed across seam -> ratio near 1.0, unflagged.
        steady = _sliding_frames(16, step_px=3, seed=5)
        ok = check_frames.motion_speed_ratio(steady[:8], steady[8:], before_fps=24, after_fps=24)
        self.assertFalse(ok["flagged"])
        self.assertGreater(ok["ratio"], 0.7)
        self.assertLess(ok["ratio"], 1.4)

        # Sharp acceleration across seam (slow spatial texture shift -> fast spatial texture shift).
        y, x = np.mgrid[0:H, 0:W]
        slow_side = [_rgb(128.0 + 40.0 * np.sin(0.08 * (x + 1.0 * i))) for i in range(8)]
        fast_side = [_rgb(128.0 + 40.0 * np.sin(0.08 * (x + 4.5 * i))) for i in range(8)]
        jump = check_frames.motion_speed_ratio(slow_side, fast_side, before_fps=48, after_fps=48)
        self.assertTrue(jump["flagged"])
        self.assertGreaterEqual(jump["ratio"], 2.5)

        # Pure exposure ramp on a stationary frame must NOT inflate spatial motion speed!
        ramp_before = [_rgb(128.0 + 40.0 * np.sin(0.08 * (x + 2.0 * i))) for i in range(8)]
        ramp_after = [_rgb(128.0 + 40.0 * np.sin(0.08 * (x + 2.0 * i)) + 4.0 * i) for i in range(8)]
        ramp_res = check_frames.motion_speed_ratio(ramp_before, ramp_after, before_fps=48, after_fps=48)
        self.assertFalse(ramp_res["flagged"])
        self.assertAlmostEqual(ramp_res["ratio"], 1.0, delta=0.15)

        # Same physical speed at 24fps (2 px/frame) vs 48fps (1 px/frame) normalizes to ratio ~1.0!
        fps24 = [_rgb(128.0 + 40.0 * np.sin(0.08 * (x + 2.0 * i))) for i in range(8)]
        fps48 = [_rgb(128.0 + 40.0 * np.sin(0.08 * (x + 1.0 * i))) for i in range(8)]
        norm = check_frames.motion_speed_ratio(fps24, fps48, before_fps=24, after_fps=48)
        self.assertFalse(norm["flagged"])
        self.assertAlmostEqual(norm["ratio"], 1.0, delta=0.15)

        # 48fps post-seam luma ramp over 8 frames (~167ms) is captured by adjacent_luma_step(fps=48).
        before_l = [_flat(110.0)] * 4
        after_ramp = [_flat(110.0 + 3.5 * i) for i in range(10)]
        self.assertGreater(check_frames.adjacent_luma_step(before_l, after_ramp, fps=48), check_frames.LIGHTNESS_STEP)

    def test_mixed_resolution_and_tiny_frames_do_not_crash_seam_freeze_or_block_steps(self):
        # Pass 2 upscaled (320x576) -> Pass 1 native (160x288) mixed-resolution continuation.
        hi_h, hi_w = 320, 576
        hi_tail = [np.repeat(np.full((hi_h, hi_w, 1), 100 + 3 * i, dtype=np.uint8), 3, axis=2) for i in range(6)]
        lo_head = [np.repeat(np.full((H, W, 1), 118 + 3 * i, dtype=np.uint8), 3, axis=2) for i in range(6)]
        res = check_frames.seam_freeze(hi_tail, lo_head)
        self.assertFalse(res["frozen"])
        self.assertFalse(np.isnan(res["seam_diff"]))

        # Reverse order (smaller -> larger) with exact seam duplicate across resolution change.
        dup_hi = [np.repeat(np.full((hi_h, hi_w, 1), 133, dtype=np.uint8), 3, axis=2)] + [
            np.repeat(np.full((hi_h, hi_w, 1), 133 + 4 * (i + 1), dtype=np.uint8), 3, axis=2) for i in range(5)
        ]
        res_dup = check_frames.seam_freeze(lo_head, dup_hi)
        self.assertTrue(res_dup["frozen"])
        self.assertTrue(res_dup["seam_duplicate"])

        # Tiny-height frame (h < fw // 240) must not crash or produce NaN.
        tiny = [np.full((2, 480, 3), 50 * i, dtype=np.uint8) for i in range(4)]
        steps = check_frames._block_steps(tiny)
        self.assertEqual(len(steps), 3)
        self.assertTrue(np.all(np.isfinite(steps)))


class StoryCheckIntegrationTest(unittest.TestCase):
    def test_vision_qc_instruction_and_request_flag_screen_fx_and_exposure_jumps(self):
        self.assertIn("unrequested screen FX", story_check.CHECK_INSTRUCTION)
        self.assertIn("vignette", story_check.CHECK_INSTRUCTION)
        self.assertIn("exposure", story_check.CHECK_INSTRUCTION)
        self.assertNotIn("Don't report camera moves, framing, composition, motion, blur or artefacts", story_check.CHECK_INSTRUCTION)

        tl = rules.Timeline(
            prompt="",
            boxes=[
                rules.Box(id="b1", frames=48, prompt="", cut=False, seed=1, first="", last="", new_scene=False),
                rules.Box(id="b2", frames=48, prompt="", cut=False, seed=2, first="", last="", new_scene=False),
            ],
        )
        raw = [
            {
                "id": "b1",
                "source": {
                    "reply": {
                        "terminal_state": {
                            "setting": "Courtyard",
                            "lighting": "Even overcast daylight",
                            "positions": "Mira center",
                            "camera_motion": "Steady tracking shot",
                            "subject_motion": "Walking steadily right",
                            "props": "Red umbrella",
                        }
                    }
                },
            },
            {"id": "b2", "schedule": {"entities": [], "place": None}},
        ]
        ctx = SimpleNamespace(timeline=tl, raw=raw, bible={"entities": []}, pictures={}, urls={}, notes=[])
        messages, _, allowed, _ = story_check.request(ctx, 1, [(0, 10)], [_flat()], None)
        self.assertIn("fx", allowed)
        self.assertIn("join", allowed)
        self.assertEqual(messages[0]["content"], story_check.CHECK_INSTRUCTION)
        parsed = story_check.parse('{"problems": [{"about": "fx", "what": "Heavy dark vignette in all four corners.", "shot": 0}]}', allowed, 0)
        self.assertEqual(parsed[0]["about"], "fx")

    def test_holds_and_continuity_metrics_use_previous_index_and_native_fps(self):
        # Multi-track timeline: track A has b1 -> b3 (adjacent), track B has b2 between them in list order!
        b1 = rules.Box(id="b1", frames=10, prompt="", cut=False, seed=1, first="", last="", new_scene=False)
        b2 = rules.Box(id="b2", frames=10, prompt="", cut=True, seed=2, first="", last="", new_scene=True)
        b3 = rules.Box(id="b3", frames=10, prompt="", cut=False, seed=3, first="", last="", new_scene=False)
        tl = rules.Timeline(
            prompt="",
            boxes=[b1, b2, b3],
            tracks=[{"id": "t1"}, {"id": "t2"}],
            placements={
                "b1": {"track": "t1", "start": 0, "end": 10},
                "b2": {"track": "t2", "start": 0, "end": 10},
                "b3": {"track": "t1", "start": 10, "end": 20},
            },
        )
        self.assertEqual(rules.previous_index(tl, 2), 0)

        # b1 (48fps, 20 frames) has slow spatial motion and ends with a 1-frame duplicate at native FPS (index 18 == 19);
        # b3 (48fps, 20 frames) is brighter (+8 L*), vignetted, and moves 4x faster spatially!
        y, x = np.mgrid[0:H, 0:W]
        nx = (x - (W - 1) / 2.0) / ((W - 1) / 2.0)
        ny = (y - (H - 1) / 2.0) / ((H - 1) / 2.0)
        vig_mask = 1.0 - 0.45 * np.clip((nx * nx + ny * ny) / 2.0, 0.0, 1.0)
        b1_frames = [_rgb(100.0 + 30.0 * np.sin(0.35 * (x + 0.5 * i))) for i in range(19)]
        b1_frames.append(b1_frames[-1].copy())  # native 48fps last-frame duplicate!
        b3_frames = [_rgb((185.0 + 30.0 * np.sin(0.35 * (x + 2.2 * i))) * vig_mask) for i in range(20)]

        entries = {
            "b1": {"video": {"file": "b1.mp4", "fps": 48, "frames": 20}, "played": 10, "context_frames": 0},
            "b2": {"video": {"file": "b2.mp4", "fps": 48, "frames": 20}, "played": 10, "context_frames": 0},
            "b3": {"video": {"file": "b3.mp4", "fps": 48, "frames": 20}, "played": 10, "context_frames": 5},
        }
        videos = {"b1.mp4": b1_frames, "b2.mp4": [_flat(10.0)] * 20, "b3.mp4": b3_frames}

        def fake_read(path, indices):
            name = path.replace("\\", "/").split("/")[-1]
            return {idx: videos[name][idx] for idx in indices}

        ctx = SimpleNamespace(folder="seq", timeline=tl, rendered=entries)
        with mock.patch.object(media, "read_frames", side_effect=fake_read):
            holds = story_check._holds(ctx, 2, entries["b3"])
            metrics = story_check._continuity_metrics(ctx, 2, entries["b3"], [b3_frames[5], b3_frames[15]])

        # Native-FPS 1-step duplicate at the join was caught even though 24fps downsampling skips odd frames!
        self.assertTrue(any(h.get("join") and h.get("native_fps") for h in holds), holds)
        self.assertEqual(metrics["previous_box"], "b1")
        self.assertGreater(metrics["vignette"], check_frames.VIGNETTE_THRESHOLD)
        self.assertGreater(metrics["vignette_step"], check_frames.VIGNETTE_STEP)
        self.assertGreater(metrics["adjacent_luma_step"], check_frames.LIGHTNESS_STEP)
        self.assertTrue(metrics["seam_freeze"]["frozen"])
        self.assertTrue(metrics["speed_ratio"]["flagged"])
        self.assertTrue(any("1-step native-FPS freeze" in w for w in metrics["warnings"]))
        self.assertTrue(any("vignette" in w for w in metrics["warnings"]))
        self.assertTrue(any("exposure jumped" in w for w in metrics["warnings"]))


if __name__ == "__main__":
    unittest.main()
