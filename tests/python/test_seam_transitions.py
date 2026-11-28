"""Tests for continuation seam transitions: 48fps midpoint restoration, overlap crossfading, exposure matching,
HDR preservation, motion-adaptive continuation_guide, join_prompts scope, seam_checks, and stale/protection alerts."""

import datetime
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import av
import numpy as np
import torch

from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()

from h3_continuity import box_checks, latents, media, nodes, seam_checks, store, timeline as rules, timeline_node, timing  # noqa: E402
from tests.python.helpers import box, document  # noqa: E402


def moving_bar_frames(count, size=32, speed=1.0, base=0.35, gain=1.0, offset=0.0):
    """Smoothly translating bright vertical bar on a textured gray background, in [0, 1] float32."""
    xs = torch.linspace(0.0, 1.0, size).view(1, 1, size, 1)
    ys = torch.linspace(0.0, 1.0, size).view(1, size, 1, 1)
    t = (torch.arange(count, dtype=torch.float32) * speed + offset).view(count, 1, 1, 1)
    center = 0.2 + 0.015 * t
    bar = torch.exp(-((xs - center) / 0.08) ** 2) * 0.45
    bg = base + 0.06 * torch.sin(2.0 * np.pi * ys)
    rgb = torch.stack([bg + bar, bg + 0.8 * bar, bg + 0.5 * bar], dim=-1).squeeze(-2)
    return (rgb * gain).clamp(0.0, 1.0)


def interpolate_2x(native_frames, *, mode="rtx"):
    """Synthesize 2x interpolated 48fps frames:
    - mode='rtx': 2N frames (repeating frame N-1 at index 2N-1, matching RTXVideoFrameGeneration)
    - mode='rife': 2N-1 frames (exact inter-frame midpoints only, matching RIFE 2x)"""
    out = []
    n = native_frames.shape[0]
    for i in range(n):
        out.append(native_frames[i])
        if i + 1 < n:
            out.append(0.5 * (native_frames[i] + native_frames[i + 1]))
        elif mode == "rtx":
            out.append(native_frames[i].clone())
    return torch.stack(out, dim=0)


def decode_all_rgb24(path):
    with av.open(path) as container:
        stream = container.streams.video[0]
        return [frame.to_ndarray(format="rgb24") for frame in container.decode(stream)]


def describe_video(path):
    with av.open(path) as container:
        stream = container.streams.video[0]
        count = sum(1 for _ in container.decode(stream))
        return {
            "codec": stream.codec_context.name,
            "tag": stream.codec_tag,
            "pix_fmt": stream.codec_context.pix_fmt,
            "transfer": stream.codec_context.color_trc,
            "color_space": media.video_stream_color_space(stream) or "sRGB",
            "rate": stream.average_rate,
            "frames": count,
        }


class OverlapSeamBlendingTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="h3c-seam-blend-")
        patcher = mock.patch("h3_continuity.timeline_api.service.authorize_sequence", lambda *a, **kw: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def _write_two_48fps_segments(self, mode="rtx", color_space="sRGB", codec="H.264"):
        # Box A: 22 native frames (0..21). Box B: carries 5 native frames (17..21) + adds 17 new (22..38).
        native_full = moving_bar_frames(39, size=48, speed=1.5, offset=-8.0)
        a_48 = interpolate_2x(native_full[:22], mode=mode)
        b_48 = interpolate_2x(native_full[17:39], mode=mode)

        entry_a = {"index": 1, "stem": store.stem(1), "frames": 22, "context_frames": 0,
                   "audio_sample_rate": 8000, "timeline": {"box": "a"}}
        entry_b = {"index": 2, "stem": store.stem(2), "frames": 22, "context_frames": 5,
                   "audio_sample_rate": 8000, "timeline": {"box": "b"}}
        notes_a, notes_b = [], []
        wave_a = torch.full((1, timing.sample_at_frame(22, 8000)), 0.1)
        wave_b = torch.full((1, timing.sample_at_frame(22, 8000)), 0.2)
        nodes._write_video(self.folder, entry_a, a_48, 48.0, 12, wave_a, 8000, notes_a, color_space, codec)
        nodes._write_video(self.folder, entry_b, b_48, 48.0, 12, wave_b, 8000, notes_b, color_space, codec)
        store.save_segment(self.folder, entry_a, torch.zeros(1, 24, 7, 2, 2), torch.zeros(1, 32, 2, 37), wave_a)
        store.save_segment(self.folder, entry_b, torch.zeros(1, 24, 7, 2, 2), torch.zeros(1, 32, 2, 37), wave_b)
        manifest = {"version": 1, "name": "seq", "segments": [entry_a, entry_b], "takes": []}
        store.write_manifest(self.folder, manifest)
        return manifest, entry_a, entry_b, native_full

    def test_48fps_rtx_restores_midpoint_removes_duplicate_tail_and_preserves_frame_count(self):
        manifest, entry_a, entry_b, _ = self._write_two_48fps_segments(mode="rtx")
        self.assertTrue(store.has_overlap_video(self.folder, entry_b))
        self.assertEqual(entry_b["video"]["overlap"]["frames"], 8)
        self.assertGreater(entry_a["exit_motion"], media.EXIT_MOTION_THRESHOLD)

        # Raw segment A indeed ends with the RTX duplicate frame before full-video blending.
        seg_a_frames = decode_all_rgb24(os.path.join(self.folder, entry_a["video"]["file"]))
        seg_b_frames = decode_all_rgb24(os.path.join(self.folder, entry_b["video"]["file"]))
        raw_check = seam_checks.video_join(seg_a_frames, seg_b_frames)
        self.assertTrue(raw_check["duplicate_tail"])

        note = nodes.rebuild_full_video(self.folder, "seq", manifest, 12)
        self.assertIn("Full video:", note)
        full_path = os.path.join(self.folder, "seq_full.mp4")
        info = describe_video(full_path)
        # Exact frame count: 22*2 + 17*2 = 78 frames at 48 fps.
        self.assertEqual(info["frames"], 78)
        self.assertEqual(info["rate"], 48)

        full_frames = decode_all_rgb24(full_path)
        blended_check = seam_checks.video_join(full_frames[:44], full_frames[44:])
        self.assertFalse(blended_check["duplicate_tail"], blended_check)
        self.assertFalse(blended_check["seam_freeze"], blended_check)
        # Frame 43 (replaced tail) must now step smoothly between frame 42 and frame 44 instead of freezing.
        step_42_43 = float(np.abs(full_frames[43].astype(np.float64) - full_frames[42].astype(np.float64)).mean())
        step_43_44 = float(np.abs(full_frames[44].astype(np.float64) - full_frames[43].astype(np.float64)).mean())
        self.assertGreater(step_42_43, 0.4)
        self.assertLess(blended_check["join_pop_ratio"], 2.0)
        self.assertAlmostEqual(step_42_43, step_43_44, delta=1.5)

    def test_48fps_rife_2n_minus_1_restores_midpoint_and_preserves_frame_count(self):
        manifest, entry_a, entry_b, _ = self._write_two_48fps_segments(mode="rife")
        self.assertTrue(store.has_overlap_video(self.folder, entry_b))
        note = nodes.rebuild_full_video(self.folder, "seq", manifest, 12)
        self.assertIn("Full video:", note)
        full_path = os.path.join(self.folder, "seq_full.mp4")
        self.assertEqual(describe_video(full_path)["frames"], 78)
        full_frames = decode_all_rgb24(full_path)
        blended_check = seam_checks.video_join(full_frames[:44], full_frames[44:])
        self.assertFalse(blended_check["duplicate_tail"], blended_check)
        self.assertFalse(blended_check["seam_freeze"], blended_check)
        self.assertLess(blended_check["join_pop_ratio"], 2.0)

    def test_48fps_hdr_hevc_preserves_10bit_hlg_and_pq_metadata_with_midpoint_fix(self):
        for space, expected_trc in (("HDR", 18), ("HDR PQ", 16)):
            with self.subTest(color_space=space):
                sub = tempfile.mkdtemp(prefix=f"h3c-hdr-{expected_trc}-")
                try:
                    old = self.folder
                    self.folder = sub
                    manifest, _, _, _ = self._write_two_48fps_segments(mode="rtx", color_space=space, codec="HEVC")
                    note = nodes.rebuild_full_video(self.folder, "seq", manifest, 12)
                    self.assertIn("Full video:", note)
                    full_path = os.path.join(self.folder, "seq_full.mp4")
                    info = describe_video(full_path)
                    self.assertEqual(info["codec"], "hevc")
                    self.assertEqual(info["tag"], "hvc1")
                    self.assertEqual(info["pix_fmt"], "yuv420p10le")
                    self.assertEqual(info["color_space"], space)
                    self.assertEqual(info["transfer"], expected_trc)
                    self.assertEqual(info["frames"], 78)
                    full_frames = decode_all_rgb24(full_path)
                    self.assertFalse(seam_checks.video_join(full_frames[:44], full_frames[44:])["duplicate_tail"])
                finally:
                    self.folder = old
                    shutil.rmtree(sub, ignore_errors=True)

    def test_24fps_overlap_crossfade_and_bounded_exposure_matching_decay(self):
        # Box A: 22 frames (gain 1.0). Box B: 5 carried + 34 new = 39 frames, Pass-2 exposure +10% brighter.
        base = moving_bar_frames(56, size=48, speed=0.8, base=0.40)
        seg_a_img = base[:22]
        seg_b_img = (base[17:56] * 1.10).clamp(0.0, 1.0)

        entry_a = {"index": 1, "stem": store.stem(1), "frames": 22, "context_frames": 0, "timeline": {"box": "a"}}
        entry_b = {"index": 2, "stem": store.stem(2), "frames": 39, "context_frames": 5, "timeline": {"box": "b"}}
        nodes._write_video(self.folder, entry_a, seg_a_img, 24.0, 10, None, None, [])
        nodes._write_video(self.folder, entry_b, seg_b_img, 24.0, 10, None, None, [])
        manifest = {"version": 1, "name": "seq", "segments": [entry_a, entry_b], "takes": []}
        store.write_manifest(self.folder, manifest)

        # Raw concat jump is ~+11 luma levels; seam blending + exposure matching should suppress it cleanly.
        raw_a = decode_all_rgb24(os.path.join(self.folder, entry_a["video"]["file"]))
        raw_b = decode_all_rgb24(os.path.join(self.folder, entry_b["video"]["file"]))
        raw_step = abs(seam_checks.video_join(raw_a, raw_b)["boundary_luma_step"])
        self.assertGreater(raw_step, 7.0)

        note = nodes.rebuild_full_video(self.folder, "seq", manifest, 10)
        self.assertIn("Blended 1 continuation seam", note)
        full_path = os.path.join(self.folder, "seq_full.mp4")
        full = decode_all_rgb24(full_path)
        self.assertEqual(len(full), 22 + 34)
        blended_step = abs(seam_checks.video_join(full[:22], full[22:])["boundary_luma_step"])
        self.assertLess(blended_step, 2.5)

        # Exposure gain decays smoothly back to 1.0 by the end of Box B (after 24-frame decay window).
        end_full_luma = float(full[-1].mean())
        end_raw_b_luma = float(raw_b[-1].mean())
        self.assertAlmostEqual(end_full_luma, end_raw_b_luma, delta=2.0)

    def test_exposure_gain_is_clamped_and_stale_overlap_is_skipped(self):
        # Clamping test: +40% brightness mismatch on same scene -> gain clamped to 0.88 (not 1/1.4=0.71).
        tail = [np.full((16, 16, 3), 0.50, dtype=np.float32) for _ in range(4)]
        overlap = np.full((4, 16, 16, 3), 0.70, dtype=np.float32)
        _, gain, applied = media._blend_continuation_seam(tail, overlap, k=1, hdr=False)
        self.assertTrue(applied)
        self.assertAlmostEqual(gain, media.OVERLAP_EXPOSURE_GAIN_MIN, places=4)

        # Stale overlap test: completely mismatched RGB channels (red vs blue) -> skipped, zero ghosting!
        red_tail = [np.stack([np.full((16, 16), 0.8), np.zeros((16, 16)), np.zeros((16, 16))], axis=-1).astype(np.float32)
                    for _ in range(4)]
        blue_ov = np.stack([np.zeros((4, 16, 16)), np.zeros((4, 16, 16)), np.full((4, 16, 16), 0.8)], axis=-1).astype(np.float32)
        out, gain_stale, applied_stale = media._blend_continuation_seam(red_tail, blue_ov, k=1, hdr=False)
        self.assertFalse(applied_stale)
        self.assertEqual(gain_stale, 1.0)
        self.assertTrue(np.array_equal(out[-1], red_tail[-1]))

    def test_overlap_sidecar_archives_with_segment_and_packet_copy_kept_without_overlap(self):
        manifest, _, entry_b, _ = self._write_two_48fps_segments(mode="rtx")
        ov_path = store.overlap_video_path(self.folder, entry_b)
        self.assertTrue(os.path.isfile(ov_path))
        store.archive_box(self.folder, manifest, "b", datetime.datetime(2026, 11, 28, 12, 0, 0))
        self.assertFalse(os.path.exists(ov_path))
        take_dir = os.path.join(self.folder, manifest["takes"][-1]["folder"])
        self.assertIn(os.path.basename(ov_path), os.listdir(take_dir))

        # Two cuts with no overlap sidecar still join via fast packet copy.
        p1 = os.path.join(self.folder, "cut1.mp4")
        p2 = os.path.join(self.folder, "cut2.mp4")
        media.write_segment_video(p1, moving_bar_frames(12, size=16), 24, 16)
        media.write_segment_video(p2, moving_bar_frames(12, size=16), 24, 16)
        _, note = media.build_full_video(os.path.join(self.folder, "cuts.mp4"), [p1, p2], None, 16)
        self.assertNotIn("re-encoded", note)
        self.assertNotIn("Blended", note)

    def test_missing_optional_overlap_sidecar_does_not_abort_full_video_build(self):
        manifest, _, entry_b, _ = self._write_two_48fps_segments(mode="rtx")
        ov_path = store.overlap_video_path(self.folder, entry_b)
        fp_with_overlap = store.full_video_fingerprint(self.folder, manifest)
        self.assertIsNotNone(fp_with_overlap)
        os.remove(ov_path)
        fp_without_overlap = store.full_video_fingerprint(self.folder, manifest)
        self.assertIsNotNone(fp_without_overlap)
        self.assertNotEqual(fp_with_overlap, fp_without_overlap)
        note = nodes.rebuild_full_video(self.folder, "seq", manifest, 12)
        self.assertIn("Full video:", note)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "seq_full.mp4")))

    def test_skipped_stale_overlap_reports_accurate_note_not_encoding_mismatch(self):
        p1 = os.path.join(self.folder, "a.mp4")
        p2 = os.path.join(self.folder, "b.mp4")
        ov = os.path.join(self.folder, "b_overlap.mp4")
        red = torch.zeros(12, 32, 32, 3)
        red[..., 0] = 0.8
        blue = torch.zeros(12, 32, 32, 3)
        blue[..., 2] = 0.8
        media.write_segment_video(p1, red, 24, 12)
        media.write_segment_video(p2, red, 24, 12)
        media.write_segment_video(ov, blue[:4], 24, 10)
        written, note = media.build_full_video(
            os.path.join(self.folder, "stale_full.mp4"), [p1, p2], None, 12,
            seams=[None, {"overlap": ov, "fps": 24.0, "color_space": "sRGB"}],
        )
        self.assertIsNotNone(written)
        self.assertNotIn("Segment encodings differ", note)
        self.assertIn("Skipped mismatched continuation seam overlap", note)

    def test_frame_to_rgb_preserves_bt709_on_unspecified_colorspace_srgb(self):
        from h3_continuity import color
        pure_green = np.zeros((16, 16, 3), dtype=np.uint8)
        pure_green[..., 1] = 202
        frame = av.VideoFrame.from_ndarray(pure_green, format="rgb24").reformat(
            format="yuv420p", dst_colorspace="itu709"
        )
        # Simulate a legacy sRGB clip whose stream left colorspace unspecified (2).
        frame.colorspace = 2
        rgb = media._frame_to_rgb(frame, "sRGB", "sRGB", 16, 16, color)
        mean_rgb = (rgb.mean(axis=(0, 1)) * 255.0).tolist()
        self.assertLess(mean_rgb[0], 5.0)
        self.assertAlmostEqual(mean_rgb[1], 202.0, delta=4.0)
        self.assertLess(mean_rgb[2], 5.0)


class MotionAdaptiveGuideTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="h3c-guide-")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_auto_guide_disables_on_moving_exit_and_enables_on_static_exit(self):
        moving_entry = {"stem": "seg_0001", "exit_motion": 4.2}
        mild_entry = {"stem": "seg_0003", "exit_motion": 2.7}
        static_entry = {"stem": "seg_0002", "exit_motion": 0.3}

        use, note = timeline_node.resolve_continuation_guide("auto", self.folder, moving_entry, box_mode="ref2va")
        self.assertFalse(use)
        self.assertIn("auto-disabled", note)

        # Mild ambient motion (e.g. 2.7 < 3.5) and all t2va continuations keep the visual anchor guide.
        use, _ = timeline_node.resolve_continuation_guide("auto", self.folder, mild_entry, box_mode="ref2va")
        self.assertTrue(use)
        use_t2va, note_t2va = timeline_node.resolve_continuation_guide("auto", self.folder, moving_entry, box_mode="t2va")
        self.assertTrue(use_t2va)
        self.assertIn("t2va", note_t2va)

        use, note = timeline_node.resolve_continuation_guide("auto", self.folder, static_entry, box_mode="ref2va")
        self.assertTrue(use)
        self.assertIn("auto-enabled", note)

        self.assertEqual(timeline_node.resolve_continuation_guide(True, self.folder, moving_entry)[0], True)
        self.assertEqual(timeline_node.resolve_continuation_guide(False, self.folder, static_entry)[0], False)

    def test_auto_guide_falls_back_to_reading_video_tail_when_metadata_absent(self):
        # Fast moving clip without exit_motion metadata
        mv_path = os.path.join(self.folder, "seg_0001.mp4")
        media.write_segment_video(mv_path, moving_bar_frames(12, size=48, speed=7.0), 24, 12)
        mv_entry = {"stem": "seg_0001", "video": {"file": "seg_0001.mp4", "fps": 24.0, "frames": 12}}
        self.assertFalse(timeline_node.resolve_continuation_guide("auto", self.folder, mv_entry, box_mode="ref2va")[0])

        # Static clip without exit_motion metadata
        st_path = os.path.join(self.folder, "seg_0002.mp4")
        static_frames = moving_bar_frames(1, size=48).repeat(12, 1, 1, 1)
        media.write_segment_video(st_path, static_frames, 24, 12)
        st_entry = {"stem": "seg_0002", "video": {"file": "seg_0002.mp4", "fps": 24.0, "frames": 12}}
        self.assertTrue(timeline_node.resolve_continuation_guide("auto", self.folder, st_entry)[0])

    def test_save_segment_warns_when_guide_frames_unwired_on_interpolated_clip(self):
        seq = nodes.SequenceRef("seq", self.folder, 1, None, None, None)
        seg = nodes.SegmentPlan(seq, 0, 0, 22, (2, 2), None, None, timeline={"box": "a"}, box_order=["a"])
        video = torch.zeros(1, 24, timing.tokens_for_frames(22), 2, 2)
        audio = torch.zeros(1, 32, 2, timing.ticks_for_frames(22))
        imgs_48 = interpolate_2x(moving_bar_frames(22, size=32), mode="rtx")
        with mock.patch.object(latents, "split_h3_latent", return_value=(video, audio)), \
                mock.patch("h3_continuity.timeline_api.service.authorize_sequence", return_value=None):
            out = nodes.H3C_SaveSegment.execute(seg, {}, 48.0, False, 16, images=imgs_48)
        self.assertIn("guide_frames is not connected", out.args[0])

        # Wiring guide_frames clears the warning and records native 24fps exit_motion.
        guide_24 = moving_bar_frames(22, size=32, speed=2.0)
        with mock.patch.object(latents, "split_h3_latent", return_value=(video, audio)), \
                mock.patch("h3_continuity.timeline_api.service.authorize_sequence", return_value=None):
            out_with_guide = nodes.H3C_SaveSegment.execute(seg, {}, 48.0, False, 16, images=imgs_48, guide_frames=guide_24)
        self.assertNotIn("guide_frames is not connected", out_with_guide.args[0])
        entry = store.load_manifest(self.folder)["segments"][0]
        self.assertTrue(store.has_guide_frame(self.folder, entry))
        self.assertGreater(entry["exit_motion"], media.EXIT_MOTION_THRESHOLD)


class JoinPromptsScopeTest(unittest.TestCase):
    def test_shared_prompt_inserts_at_clip_header_before_shot_one(self):
        shared = "Clean full-frame digital image, no vignette."
        structured = (
            "integrated_multimodal_description:\n"
            "[Shot 1] Wide shot on Mara.\n"
            "[Shot 2] At 00:02.000, cut to close-up.\n\n"
            "overall_soundscape: Quiet street.\n\n"
            "non_diegetic_music: None."
        )
        joined = rules.join_prompts(shared, structured)
        self.assertIn(f"integrated_multimodal_description:\n{shared}\n[Shot 1] Wide shot on Mara.", joined)
        self.assertNotIn(f"[Shot 1] {shared}", joined)

    def test_alignment_header_mention_of_shot_one_is_not_corrupted(self):
        shared = "Steady overcast daylight."
        structured = (
            "For the target video, at 0.00 seconds into the target video, @image1 (from [Shot 1]) is fully referenced.\n\n"
            "integrated_multimodal_description:\n"
            "[Shot 1] Mara walks across the roof.\n"
            "[Shot 2] She turns toward the sky.\n\n"
            "overall_soundscape: Wind.\n\n"
            "non_diegetic_music: None."
        )
        joined = rules.join_prompts(shared, structured)
        self.assertTrue(joined.startswith("For the target video, at 0.00 seconds into the target video, @image1 (from [Shot 1])"))
        self.assertIn(f"integrated_multimodal_description:\n{shared}\n[Shot 1] Mara walks", joined)

    def test_single_line_integrated_multimodal_description_puts_shared_before_shot_one(self):
        shared = "Clean full-frame digital image, no vignette."
        single_line = (
            "integrated_multimodal_description: [Shot 1] Wide shot on Mara.\n"
            "[Shot 2] At 00:02.000, cut to close-up.\n\n"
            "overall_soundscape: Quiet street.\n\n"
            "non_diegetic_music: None."
        )
        joined = rules.join_prompts(shared, single_line)
        self.assertTrue(joined.startswith(f"integrated_multimodal_description: {shared}\n[Shot 1] Wide shot on Mara."), joined)

        with_align = (
            "For the target video, at 0.00 seconds into the target video, @image1 (from [Shot 1]) is fully referenced.\n\n"
            + single_line
        )
        joined_align = rules.join_prompts(shared, with_align)
        self.assertTrue(joined_align.startswith("For the target video, at 0.00 seconds into the target video, @image1 (from [Shot 1])"))
        self.assertIn(f"integrated_multimodal_description: {shared}\n[Shot 1] Wide shot on Mara.", joined_align)

    def test_plain_prompt_still_joins_with_blank_line(self):
        self.assertEqual(rules.join_prompts("Shared.", "Box prompt."), "Shared.\n\nBox prompt.")


class SeamChecksMetricsTest(unittest.TestCase):
    def test_video_join_catches_sawtooth_luma_ramp_duplicate_tail_speed_and_vignette(self):
        # 1. Sawtooth 4-frame luma ramp (like b005->b006: 57 -> 62.5 -> 67 -> 72.5 -> 78.8)
        before = np.stack([np.full((32, 32, 3), 57.0, dtype=np.float64)] * 6, axis=0)
        after = np.stack([
            np.full((32, 32, 3), 62.5),
            np.full((32, 32, 3), 67.0),
            np.full((32, 32, 3), 72.5),
            np.full((32, 32, 3), 78.8),
            np.full((32, 32, 3), 78.8),
        ], axis=0)
        res = seam_checks.video_join(before, after)
        self.assertEqual(res["status"], "ok")
        self.assertAlmostEqual(res["boundary_luma_step"], 5.5, places=2)
        self.assertAlmostEqual(res["ramp_luma_step"], 21.8, places=2)
        self.assertEqual(len(res["ramp_luma_profile"]), 4)

        # 2. 1-step RTX duplicate tail + pop spike
        mv = (moving_bar_frames(14, size=32, speed=2.0).numpy() * 255.0).astype(np.uint8)
        before_dup = np.concatenate([mv[:6], mv[5:6]], axis=0)  # frozen duplicate at tail
        after_cont = mv[7:13]  # skipped frame 6 midpoint
        dup_res = seam_checks.video_join(before_dup, after_cont)
        self.assertTrue(dup_res["duplicate_tail"])
        self.assertTrue(dup_res["seam_freeze"])
        self.assertGreater(dup_res["join_pop_ratio"], 1.5)

        # 3. Speed jump ratio (Box B moving 3x faster than Box A)
        slow = (moving_bar_frames(10, size=48, speed=0.8).numpy() * 255.0).astype(np.uint8)
        fast = (moving_bar_frames(10, size=48, speed=2.4, offset=8.0).numpy() * 255.0).astype(np.uint8)
        spd = seam_checks.video_join(slow, fast)
        self.assertGreater(spd["speed_ratio"], 2.0)

        # 4. Vignette delta (darkened 4 corners in Box B, zero on vertical gradient)
        clean = np.full((6, 32, 32, 3), 180.0, dtype=np.float64)
        vignetted = clean.copy()
        vignetted[:, :4, :4, :] = 120.0
        vignetted[:, :4, -4:, :] = 120.0
        vignetted[:, -4:, :4, :] = 120.0
        vignetted[:, -4:, -4:, :] = 120.0
        vig = seam_checks.video_join(clean, vignetted)
        self.assertAlmostEqual(vig["before_vignette"], 0.0, places=2)
        self.assertAlmostEqual(vig["after_vignette"], 60.0, places=2)
        self.assertAlmostEqual(vig["vignette_delta"], 60.0, places=2)

        # Pure vertical gradient (bright sky top, dark floor bottom) must NOT register as vignette.
        grad = np.broadcast_to(np.linspace(220.0, 60.0, 32).reshape(1, 32, 1, 1), (4, 32, 32, 3)).copy()
        self.assertAlmostEqual(seam_checks._vignette_drop(grad), 0.0, places=2)

    def test_video_join_48fps_scales_ramp_window_to_full_167ms_ramp(self):
        # Simulate Pass 2 48fps b005->b006 sawtooth ramp across 7 frames: 57 -> 60 -> 62.5 -> 65 -> 68 -> 71 -> 74 -> 76.1
        before = np.stack([np.full((32, 32, 3), 57, dtype=np.uint8)] * 6, axis=0)
        levels = [60, 62, 65, 68, 71, 74, 76, 76, 76]
        after = np.stack([np.full((32, 32, 3), v, dtype=np.uint8) for v in levels], axis=0)
        res_24 = seam_checks.video_join(before, after, fps=24.0)
        res_48 = seam_checks.video_join(before, after, fps=48.0)
        self.assertEqual(len(res_24["ramp_luma_profile"]), 4)
        self.assertAlmostEqual(res_24["ramp_luma_step"], 11.0, places=2)
        self.assertEqual(len(res_48["ramp_luma_profile"]), 8)
        self.assertAlmostEqual(res_48["ramp_luma_step"], 19.0, places=2)

    def test_latent_overlap_mismatch(self):
        a = torch.randn(1, 24, 32, 4, 4)
        b_match = torch.cat([a[:, :, -12:], torch.randn(1, 24, 20, 4, 4)], dim=2)
        b_stale = torch.randn(1, 24, 32, 4, 4)

        ok = seam_checks.latent_overlap_mismatch(a, b_match, 12)
        self.assertEqual(ok["status"], "ok")
        self.assertAlmostEqual(ok["overlap_mad"], 0.0, places=5)
        self.assertFalse(ok["stale"])

        stale = seam_checks.latent_overlap_mismatch(a, b_stale, 12)
        self.assertEqual(stale["status"], "ok")
        self.assertGreater(stale["overlap_mad"], 0.5)
        self.assertTrue(stale["stale"])


class StaleAndMixedProtectionStatusTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="h3c-seam-status-")
        self.boxes = [box("a", 107), box("b", 102), box("c", 102)]
        self.parsed = rules.parse(json.dumps(document(self.boxes)))

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def _entry(self, idx, box_id, *, context, created, video_tensor, prot=False, carried_from=None, ending=0, video_meta=None):
        tl = {"box": box_id, "layout": rules.layout_key(self.parsed, idx - 1, 39),
              "settings": rules.box_settings(context == 0, "t2va", 64, 64, 39, True, "match")}
        if prot:
            tl["degradation_protection"] = {"method": "tail_anchor", "strength": 0.7}
        if ending:
            tl["ending_context_frames"] = ending
        entry = {"index": idx, "stem": store.stem(idx), "frames": 141 if context else 107,
                 "context_frames": context, "latent_width": 64, "latent_height": 64,
                 "created": created, "timeline": tl}
        if carried_from:
            entry["carried_from"] = carried_from
        if video_meta:
            entry["video"] = video_meta
        store.save_segment(self.folder, entry, video_tensor,
                           torch.zeros(1, 32, 2, timing.ticks_for_frames(entry["frames"])), None)
        return entry

    def test_stale_latent_overlap_flags_outdated_and_seam_warning(self):
        lat_a_new = torch.ones(1, 24, 32, 4, 4)
        lat_b_old = torch.zeros(1, 24, 42, 4, 4)  # carried [:12] is 0, while A[-12:] is 1 -> MAD=1.0
        a = self._entry(1, "a", context=0, created="2026-11-27T09:00:00", video_tensor=lat_a_new)
        b = self._entry(2, "b", context=39, created="2026-11-26T14:30:00", video_tensor=lat_b_old,
                        carried_from="2026-11-26T14:00:00")
        entries = {1: a, 2: b}
        known = {"width": 64, "height": 64, "context_frames": 39, "carry_audio": True, "ref_image_size": "match"}
        is_done, reasons = timeline_node.status_test(self.parsed, self.folder, entries, known, 39)
        self.assertTrue(is_done(0, a))
        self.assertFalse(is_done(1, b))
        self.assertIn("carried overlap does not match", reasons[1])

        manifest = {"version": 1, "name": "seq", "segments": [a, b], "takes": []}
        status = timeline_node._status("seq", self.folder, self.parsed, manifest, is_done, reasons, known=known)
        self.assertEqual(status["boxes"][1]["status"], "outdated")
        kinds = [w["kind"] for w in status["boxes"][1]["seam_warnings"]]
        self.assertIn("stale_continuation", kinds)
        self.assertGreater(status["boxes"][1]["seam_warnings"][0]["overlap_mad"], 0.9)

    def test_build_ending_regeneration_with_matching_latents_is_not_flagged_stale(self):
        shared_overlap = torch.full((1, 24, 12, 4, 4), 0.5)
        lat_a_regen = torch.cat([torch.zeros(1, 24, 20, 4, 4), shared_overlap], dim=2)
        lat_b_kept = torch.cat([shared_overlap, torch.ones(1, 24, 30, 4, 4)], dim=2)
        a = self._entry(1, "a", context=0, created="2026-11-27T09:00:00", video_tensor=lat_a_regen, ending=39)
        b = self._entry(2, "b", context=39, created="2026-11-26T14:30:00", video_tensor=lat_b_kept,
                        carried_from="2026-11-26T14:00:00")
        self.assertIsNone(box_checks.stale_continuation_problem(self.folder, self.parsed, 1, b, {1: a, 2: b}))

    def test_mixed_protection_and_missing_guide_frames_are_flagged_in_status(self):
        z_a = torch.zeros(1, 24, 32, 4, 4)
        z_b = torch.zeros(1, 24, 42, 4, 4)
        # a (fresh, 48fps no _guide.png) -> b (cont, unprotected!) -> c (cont, protected!)
        a = self._entry(1, "a", context=0, created="2026-11-26T10:00:00", video_tensor=z_a, prot=False,
                        video_meta={"file": "seg_0001.mp4", "fps": 48.0, "width": 128, "height": 128, "frames": 214})
        b = self._entry(2, "b", context=39, created="2026-11-26T10:05:00", video_tensor=z_b, prot=False,
                        carried_from="2026-11-26T10:00:00")
        c = self._entry(3, "c", context=39, created="2026-11-26T10:10:00", video_tensor=z_b, prot=True,
                        carried_from="2026-11-26T10:05:00")
        manifest = {"version": 1, "name": "seq", "segments": [a, b, c], "takes": []}
        status = timeline_node._status("seq", self.folder, self.parsed, manifest, lambda i, e: True)
        b_kinds = {w["kind"] for w in status["boxes"][1].get("seam_warnings", [])}
        self.assertIn("mixed_protection", b_kinds)
        self.assertIn("missing_guide_frames", b_kinds)
        self.assertNotIn("seam_warnings", status["boxes"][0])
        self.assertNotIn("seam_warnings", status["boxes"][2])
        self.assertTrue(status.get("seam_warnings"))

    def test_plate_changes_reset_box_is_not_falsely_flagged_as_mixed_protection(self):
        plates = [{"id": "p1", "slot": "image1", "image": {"type": "output", "subfolder": "h3_previews", "filename": "p1.png"}}]
        boxes = [
            box("a", 107),
            box("b", 102),
            box("c", 102, plate_changes=[{"slot": "image1", "frame": 0, "revision": "p1"}]),
            box("d", 102),
            box("e", 102),
        ]
        parsed = rules.parse(json.dumps(document(boxes, plates=plates)))
        z_a = torch.zeros(1, 24, 32, 4, 4)
        z_c = torch.zeros(1, 24, 42, 4, 4)

        def make(idx, bid, ctx, prot):
            tl = {"box": bid, "layout": rules.layout_key(parsed, idx - 1, 39),
                  "settings": rules.box_settings(ctx == 0, "t2va", 64, 64, 39, True, "match")}
            if prot:
                tl["degradation_protection"] = {"method": "tail_anchor", "strength": 0.7}
            entry = {"index": idx, "stem": store.stem(idx), "frames": 141 if ctx else 107,
                     "context_frames": ctx, "latent_width": 64, "latent_height": 64,
                     "created": f"2026-11-26T10:{idx:02d}:00", "timeline": tl}
            store.save_segment(self.folder, entry, z_c if ctx else z_a,
                               torch.zeros(1, 32, 2, timing.ticks_for_frames(entry["frames"])), None)
            return entry

        # a(fresh,none) -> b(prot) -> c(plate_changes, intentionally unprotected) -> d(prot) -> e(unprotected!)
        segs = [make(1, "a", 0, False), make(2, "b", 39, True), make(3, "c", 39, False),
                make(4, "d", 39, True), make(5, "e", 39, False)]
        manifest = {"version": 1, "name": "seq", "segments": segs, "takes": []}
        status = timeline_node._status("seq", self.folder, parsed, manifest, lambda i, e: True)
        self.assertNotIn("seam_warnings", status["boxes"][2], "plate_changes reset box must not warn mixed_protection")
        e_kinds = {w["kind"] for w in status["boxes"][4].get("seam_warnings", [])}
        self.assertIn("mixed_protection", e_kinds, "unprotected continuation after protected d must still warn")

        # Also: if the entire sub-chain after plate_changes is unprotected, d must NOT inherit b's protection.
        segs_unprot_after = [segs[0], segs[1], segs[2], make(4, "d", 39, False), make(5, "e", 39, False)]
        status2 = timeline_node._status("seq", self.folder, parsed,
                                        {"version": 1, "name": "seq", "segments": segs_unprot_after, "takes": []},
                                        lambda i, e: True)
        for i in (2, 3, 4):
            self.assertNotIn("seam_warnings", status2["boxes"][i])


class AudioSeamAlignmentTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="h3c-audio-seam-")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_carried_audio_tick_alignment_eliminates_phase_flanging_across_chain(self):
        rate = 32000
        # 39-frame segments (17 new + 22 carried) so segment count is short while hitting 65 ticks -> tick remainder 2
        # Actually test 90 -> 90 (22 context -> tail_start = round(68*5/3) = 113 != 113.333, 267-sample phase shift)
        sr_total = timing.sample_at_frame(90 + 68 + 68, rate)
        t = torch.arange(sr_total, dtype=torch.float32) / rate
        master = torch.sin(2.0 * torch.pi * 440.0 * t).unsqueeze(0)

        def seg(idx, start_sample, context, created, carried_from=None):
            entry = {
                "index": idx, "stem": store.stem(idx), "frames": 90, "context_frames": context,
                "carried_audio": context > 0, "audio_sample_rate": rate, "created": created,
                "timeline": {"box": f"b{idx}"},
            }
            if carried_from:
                entry["carried_from"] = carried_from
            samples = timing.ticks_for_frames(90) * rate // timing.AUDIO_TICKS_PER_SECOND
            wave = master[:, start_sample:start_sample + samples].clone()
            store.save_segment(self.folder, entry, torch.zeros(1, 1, 1, 1, 1), torch.zeros(1, 1, 1, 1), wave)
            return entry

        # Box 2 copies ticks 113..150 -> sample 113 * 800 = 90400 of Box 1!
        s1 = seg(1, 0, 0, "2026-11-28T10:00:00")
        b2_start = 113 * (rate // timing.AUDIO_TICKS_PER_SECOND)
        s2 = seg(2, b2_start, 22, "2026-11-28T10:05:00", s1["created"])
        # Box 3 starts relative to Box 2 at tick 113 of Box 2.
        b3_start = b2_start + 113 * (rate // timing.AUDIO_TICKS_PER_SECOND)
        s3 = seg(3, b3_start, 22, "2026-11-28T10:10:00", s2["created"])

        parts = [(s1, 0, 90, False), (s2, 0, 68, False), (s3, 0, 68, False)]
        merged, out_rate = nodes._generated_audio(self.folder, parts)
        self.assertEqual(out_rate, rate)
        self.assertEqual(merged.shape[-1], sr_total)

        # Across both crossfade zones (~116800..120000 and ~207467..210667) the sine wave must have ZERO phase comb dip!
        diff = (merged[0] - master[0]).abs()
        self.assertLess(float(diff[115000:122000].max()), 1e-4)
        self.assertLess(float(diff[206000:213000].max()), 1e-4)

    def test_tick_deficit_tail_and_hard_cut_declick(self):
        rate = 32000
        # 56 frames -> ticks_for_frames(56) = 93 -> 74400 samples, 267 shorter than sample_at_frame(56, 32000) = 74667
        w1 = torch.full((1, timing.ticks_for_frames(56) * (rate // timing.AUDIO_TICKS_PER_SECOND)), 0.5)
        w2 = torch.full((1, timing.ticks_for_frames(39) * (rate // timing.AUDIO_TICKS_PER_SECOND)), 0.5)
        e1 = {"index": 1, "stem": "seg_0001", "frames": 56, "context_frames": 0, "audio_sample_rate": rate}
        e2 = {"index": 2, "stem": "seg_0002", "frames": 39, "context_frames": 17, "carried_audio": True,
              "audio_sample_rate": rate}
        local2 = media.carried_local_sample(e1, w1.shape[1], e2, 0, rate)
        merged, _ = media.assemble_audio([(56, 0, w1, rate), (39, 17, w2, rate, local2)])
        # No zero-hole right before frame 56 boundary (74400..74667).
        self.assertGreater(float(merged[:, 71000:80000].min()), 0.499)

        # Standalone 56-frame segment ending in sample_at_frame(56, sr) zero pad tapers cleanly instead of stepping.
        solo, _ = media.assemble_audio([(56, 0, w1, rate)])
        self.assertLess(float((solo[:, 1:] - solo[:, :-1]).abs().max()), 0.05)

        # Hard cut +0.5 -> -0.5 with default crossfade declicks the 1.0 boundary step cleanly.
        cut_a = torch.full((1, timing.sample_at_frame(22, rate)), 0.5)
        cut_b = torch.full((1, timing.sample_at_frame(22, rate)), -0.5)
        declicked, _ = media.assemble_audio([(22, 0, cut_a, rate), (22, 0, cut_b, rate)])
        cut_sample = timing.sample_at_frame(22, rate)
        self.assertLess(float((declicked[:, cut_sample - 10:cut_sample + 10].diff(dim=-1)).abs().max()), 0.05)
        raw_butt, _ = media.assemble_audio([(22, 0, cut_a, rate), (22, 0, cut_b, rate)], crossfade_seconds=0)
        self.assertAlmostEqual(float(raw_butt[0, cut_sample - 1] - raw_butt[0, cut_sample]), 1.0, places=5)


class SeamFlashAndSceneTailTest(unittest.TestCase):
    def test_video_join_flags_seam_contrast_flash(self):
        sharp = (moving_bar_frames(6, size=48, speed=0.0).numpy() * 255.0).astype(np.uint8)
        flashed = sharp[:4].copy()
        flashed[0] = (0.5 * flashed[0] + 0.5 * 85.0).astype(np.uint8)
        res = seam_checks.video_join(sharp, flashed)
        self.assertTrue(res["seam_flash"])
        self.assertLess(res["contrast_drop_ratio"], 0.70)

        normal = seam_checks.video_join(sharp, sharp[:4])
        self.assertFalse(normal["seam_flash"])
        self.assertAlmostEqual(normal["contrast_drop_ratio"], 1.0, places=2)

    def test_scene_tail_memory_skips_outdated_scene_start_frame(self):
        b1 = box("b001", 107, cut=True, new_scene=True, memory="off", prompt="Sitting on floor.")
        b2 = box("b002", 119, cut=False, memory="off", prompt="Standing up.")
        b3_scene = box("b003", 206, cut=True, new_scene=False, memory="scene", prompt="Singing: <d>[English] Hi</d>")
        b3_tail = box("b003", 206, cut=True, new_scene=False, memory="scene_tail", prompt="Singing: <d>[English] Hi</d>")

        parsed_scene = rules.parse(json.dumps(document([b1, b2, b3_scene])))
        parsed_tail = rules.parse(json.dumps(document([b1, b2, b3_tail])))
        self.assertEqual([(src, frame) for src, frame, _ in rules.memory_sources(parsed_scene, 2)], [(0, 0), (1, 114)])
        self.assertEqual([(src, frame) for src, frame, _ in rules.memory_sources(parsed_tail, 2)], [(1, 114)])


if __name__ == "__main__":
    unittest.main()
