import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()

from h3_continuity import nodes, protection, store, timeline


def parsed(boxes=None, **extra):
    return timeline.parse(json.dumps(dict(version=1, boxes=boxes or [
        dict(id='a', frames=90, prompt='Room', seed=1),
        dict(id='b', frames=85, prompt='Continue', seed=2),
        dict(id='c', frames=85, prompt='Continue', seed=3)], **extra)))


def entry(index, box):
    return dict(index=index, stem=f'seg_{index:04}', created='take1', frames=90, context_frames=0,
                latent_width=64, latent_height=64, timeline=dict(box=box, layout='layout1'))


class ProtectionSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = self.temp.name
        self.entries = {1: entry(1, 'a'), 2: entry(2, 'b')}
        self.video = torch.arange(1*24*27*4*4, dtype=torch.float32).reshape(1, 24, 27, 4, 4)
        store.save_segment(self.folder, self.entries[1], self.video, torch.zeros(1, 32, 2, 150), None)
        store.write_manifest(self.folder, dict(version=1, name='test', segments=list(self.entries.values())))

    def info(self, document=None, index=1, entries=None, guides=(), ending=0):
        return protection.source_info(document or parsed(), index, self.entries if entries is None else entries,
                                      lambda i, e: True, guides, ending)

    def segment(self, info):
        sequence = nodes.SequenceRef('test', self.folder, 2, self.entries[1], None, None)
        return nodes.SegmentPlan(sequence, 39, 0, 124, (4, 4), torch.zeros(1, 24, 12, 4, 4), None,
                                 protection_source=info)

    def test_tracks_choose_the_playback_chain_not_array_or_manifest_one(self):
        boxes = [dict(id='b', track='v1', start=90, frames=85, exact=True, prompt='b'),
                 dict(id='other', track='v2', start=0, frames=90, exact=True, prompt='other'),
                 dict(id='a', track='v1', start=0, frames=90, exact=True, prompt='a')]
        doc = parsed(boxes, requires=['timeline-tracks-1'], tracks=[
            dict(id='v1', type='video', name='One'), dict(id='v2', type='video', name='Two')])
        entries = {2: entry(2, 'other'), 3: entry(3, 'a')}
        info = self.info(doc, 0, entries)
        self.assertEqual(info['status'], 'ready')
        self.assertEqual(info['source']['timeline']['box'], 'a')
        entries[3]['timeline']['layout'] = 'changed'
        self.assertEqual(info['source']['timeline']['layout'], 'layout1')

    def test_cut_or_gap_resets_anchor(self):
        doc = parsed()
        doc.boxes[1].cut = True
        self.assertEqual(self.info(doc, 1)['status'], 'skip')
        self.assertEqual(self.info(doc, 2)['source']['timeline']['box'], 'b')
        boxes = [dict(id='a', track='v1', start=0, frames=90, exact=True, prompt='a'),
                 dict(id='b', track='v1', start=120, frames=85, exact=True, prompt='b')]
        doc = parsed(boxes, requires=['timeline-tracks-1'], tracks=[dict(id='v1', type='video', name='One')])
        self.assertEqual(self.info(doc, 1)['status'], 'skip')

    def test_in_chain_plate_change_resets_root_for_subsequent_continuations(self):
        doc = parsed()
        doc.boxes[1].plate_changes = [dict(frame=17)]
        # The plate-change box itself skips so it is not pulled toward pre-change lighting/appearance.
        self.assertEqual(self.info(doc, 1)['status'], 'skip')
        # Subsequent continuations reset their clean root to the plate-change box (same_shot=True).
        inf_c = self.info(doc, 2)
        self.assertEqual(inf_c['status'], 'ready')
        self.assertEqual((inf_c['mode'], inf_c['same_shot'], inf_c['source']['timeline']['box']),
                         ('continuation', True, 'b'))
        # Same for in-chain new_scene without cut: resets root to box 1 for subsequent continuations.
        doc.boxes[1].plate_changes = []
        doc.boxes[1].new_scene = True
        self.assertEqual(self.info(doc, 1)['status'], 'skip')
        inf_c2 = self.info(doc, 2)
        self.assertEqual((inf_c2['status'], inf_c2['same_shot'], inf_c2['source']['timeline']['box']),
                         ('ready', True, 'b'))
        # A cut with memory='off' still skips.
        doc.boxes[2].cut = True
        self.assertEqual(self.info(doc, 2)['status'], 'skip')
        # A same-scene cut with memory='scene' after in-chain appearance reset anchors to the reset box.
        doc.boxes[2].memory = 'scene'
        inf_c3 = self.info(doc, 2)
        self.assertEqual((inf_c3['status'], inf_c3['mode'], inf_c3['source']['timeline']['box']),
                         ('ready', 'cut_memory', 'b'))

    def test_legacy_graph_defers_missing_source_failure(self):
        with mock.patch.object(store, 'load_video_window', side_effect=AssertionError('unexpected read')):
            info = self.info(entries={})
            self.assertEqual(info['status'], 'error')
            self.assertEqual(self.info(index=0)['status'], 'skip')
        with self.assertRaisesRegex(ValueError, 'source'):
            protection.load_anchors(self.segment(info))

    def test_loads_only_two_original_slices_and_caps_inside_played_endpoint(self):
        info = self.info()
        with mock.patch.object(store, 'load_video_window', wraps=store.load_video_window) as load:
            front, back, descriptor = protection.load_anchors(self.segment(info))
        self.assertEqual(load.call_count, 2)
        self.assertTrue(torch.equal(front, self.video[:, :, :1]))
        self.assertTrue(torch.equal(back, self.video[:, :, 25:26]))
        self.assertEqual(descriptor['source_box'], 'a')
        self.assertIn('source_digest', descriptor)
        self.entries[1]['played'] = 20
        store.write_manifest(self.folder, dict(version=1, segments=list(self.entries.values())))
        _, back, _ = protection.load_anchors(self.segment(self.info()))
        self.assertTrue(torch.equal(back, self.video[:, :, 5:6]))

    def test_take_change_rejects_prepared_source(self):
        info = self.info()
        self.entries[1]['created'] = 'take2'
        store.write_manifest(self.folder, dict(version=1, segments=list(self.entries.values())))
        with self.assertRaisesRegex(ValueError, 'source.*changed'):
            protection.load_anchors(self.segment(info))

    def test_stale_missing_wrong_geometry_and_bad_source_fail_when_loaded(self):
        doc = parsed()
        info = protection.source_info(doc, 1, self.entries, lambda i,e: False, (), 0)
        with self.assertRaisesRegex(ValueError, 'source'):
            protection.load_anchors(self.segment(info))
        segment = self.segment(self.info())
        segment.latent_size = (8, 8)
        with self.assertRaisesRegex(ValueError, 'resolution'):
            protection.load_anchors(segment)
        Path(self.folder, 'seg_0001.safetensors').unlink()
        with self.assertRaisesRegex(ValueError, 'source'):
            protection.load_anchors(self.segment(self.info()))

    def test_ending_and_authored_guides_suppress_capstone_not_front(self):
        doc = parsed()
        doc.boxes[1].last = 'image1'
        for info in (self.info(ending=39), self.info(guides=[(60, 'guide.png')]), self.info(doc)):
            front, back, descriptor = protection.load_anchors(self.segment(info))
            self.assertIsNotNone(front)
            self.assertIsNone(back)
            self.assertTrue(descriptor['capstone_suppressed'])
        self.assertFalse(self.info()['context_noise'])
        self.assertTrue(self.info(parsed(context_noise=True))['context_noise'])

    def test_cut_memory_traces_clean_scene_root_and_resets_at_new_scene(self):
        # a (pre-dawn kitchen, fresh) -> b (cont) -> c (cut, same scene) -> d (cont of c)
        # -> e (new_scene flashback, mem off)
        # -> f (sunlit morning kitchen: new_scene + selected -> c): MUST start fresh root, NOT anchor to a!
        # -> g (cont of f) -> h (cut, same scene as f)
        boxes = [
            dict(id='a', frames=90, prompt='Pre-dawn kitchen', seed=1),
            dict(id='b', frames=85, prompt='Continue', seed=2),
            dict(id='c', frames=90, prompt='Cut kitchen', seed=3, cut=True, memory='scene'),
            dict(id='d', frames=85, prompt='Continue cut', seed=4),
            dict(id='e', frames=90, prompt='Hospital flashback', seed=5, cut=True, new_scene=True, memory='off'),
            dict(id='f', frames=90, prompt='Sunlit morning kitchen', seed=6, cut=True, new_scene=True,
                 memory='selected', memories=[dict(box='c', frame=20)]),
            dict(id='g', frames=85, prompt='Continue morning kitchen', seed=7),
            dict(id='h', frames=90, prompt='Low angle morning kitchen', seed=8, cut=True, memory='scene'),
        ]
        doc = parsed(boxes)
        entries = {i + 1: entry(i + 1, bx['id']) for i, bx in enumerate(boxes)}
        self.assertEqual(self.info(doc, 0, entries)['status'], 'skip')
        inf_b = self.info(doc, 1, entries)
        self.assertEqual((inf_b['mode'], inf_b['same_shot'], inf_b['source']['timeline']['box']), ('continuation', True, 'a'))
        inf_c = self.info(doc, 2, entries)
        self.assertEqual((inf_c['mode'], inf_c['same_shot'], inf_c['source']['timeline']['box']), ('cut_memory', False, 'a'))
        inf_d = self.info(doc, 3, entries)
        self.assertEqual((inf_d['mode'], inf_d['same_shot'], inf_d['source']['timeline']['box']), ('continuation', False, 'a'))
        self.assertEqual(self.info(doc, 4, entries)['status'], 'skip')
        # new_scene=True with selected memory starts a fresh lighting root instead of poisoning with pre-dawn 'a'.
        self.assertEqual(self.info(doc, 5, entries)['status'], 'skip')
        # Subsequent continuation and same-scene cut anchor to the new morning kitchen root 'f'.
        inf_g = self.info(doc, 6, entries)
        self.assertEqual((inf_g['mode'], inf_g['same_shot'], inf_g['source']['timeline']['box']), ('continuation', True, 'f'))
        inf_h = self.info(doc, 7, entries)
        self.assertEqual((inf_h['mode'], inf_h['same_shot'], inf_h['source']['timeline']['box']), ('cut_memory', False, 'f'))

        # Cross-arc cast memory (e.g. blue-hour rooftop 'a' -> cutaway 'e' -> golden sunrise rooftop 'r' with cast memory):
        # new_scene=True must NEVER inherit blue-hour 'a' via character-first cast memory; subsequent boxes anchor to 'r'.
        doc_cast = parsed([
            dict(id='a', frames=90, prompt='Blue-hour rooftop', seed=1),
            dict(id='e', frames=90, prompt='Indoor cutaway', seed=2, cut=True, new_scene=True, memory='off'),
            dict(id='r', frames=90, prompt='Golden sunrise rooftop', seed=3, cut=True, new_scene=True, memory='cast'),
            dict(id='s', frames=85, prompt='Continue golden rooftop', seed=4),
            dict(id='t', frames=90, prompt='Cut golden rooftop', seed=5, cut=True, memory='scene'),
        ])
        entries_cast = {i + 1: entry(i + 1, bx.id) for i, bx in enumerate(doc_cast.boxes)}
        with mock.patch.object(protection.timeline, 'memory_sources', return_value=[(1, 0, 'prev'), (0, 20, 'showing hero')]):
            self.assertEqual(self.info(doc_cast, 2, entries_cast)['status'], 'skip')
        inf_s = self.info(doc_cast, 3, entries_cast)
        self.assertEqual((inf_s['mode'], inf_s['same_shot'], inf_s['source']['timeline']['box']), ('continuation', True, 'r'))
        inf_t = self.info(doc_cast, 4, entries_cast)
        self.assertEqual((inf_t['mode'], inf_t['same_shot'], inf_t['source']['timeline']['box']), ('cut_memory', False, 'r'))

        # new_scene=True with memory='scene' also starts a fresh lighting root.
        doc_scene_ns = parsed([
            dict(id='a', frames=90, prompt='Night room', seed=1),
            dict(id='b', frames=90, prompt='Bright exterior', seed=2, cut=True, new_scene=True, memory='scene'),
            dict(id='c', frames=85, prompt='Continue bright', seed=3),
        ])
        entries_ns = {i + 1: entry(i + 1, bx.id) for i, bx in enumerate(doc_scene_ns.boxes)}
        self.assertEqual(self.info(doc_scene_ns, 1, entries_ns)['status'], 'skip')
        inf_c_ns = self.info(doc_scene_ns, 2, entries_ns)
        self.assertEqual((inf_c_ns['mode'], inf_c_ns['same_shot'], inf_c_ns['source']['timeline']['box']), ('continuation', True, 'b'))

    def test_load_anchor_clip_uses_exit_tail_only_for_same_shot_continuations(self):
        doc = parsed([
            dict(id='a', frames=90, prompt='Kitchen', seed=1),
            dict(id='b', frames=85, prompt='Cont', seed=2),
            dict(id='c', frames=90, prompt='Cut', seed=3, cut=True, memory='scene'),
            dict(id='d', frames=85, prompt='Post-cut cont', seed=4),
        ])
        entries = {1: entry(1, 'a'), 2: entry(2, 'b'), 3: entry(3, 'c'), 4: entry(4, 'd')}
        inf_b = self.info(doc, 1, entries)
        anc_b, off_b = protection.load_anchor_clip(self.segment(inf_b))
        self.assertEqual(off_b, 27 - protection.TAIL_ANCHOR_TOKENS)
        self.assertTrue(torch.equal(anc_b, self.video[:, :, off_b:]))
        for idx in (2, 3):
            seg = self.segment(self.info(doc, idx, entries))
            anc, off = protection.load_anchor_clip(seg)
            self.assertEqual(off, 0)
            self.assertTrue(torch.equal(anc, self.video))

    def test_load_anchor_clip_tight_token_count_excludes_dropped_trailing_frames(self):
        # Exact box generated 39 frames (12 tokens) but played only 25 frames:
        # frames_for_tokens(7)=22 < 25, frames_for_tokens(8)=26 >= 25 => must load only 8 tokens (not 12).
        short_video = torch.arange(1 * 24 * 12 * 4 * 4, dtype=torch.float32).reshape(1, 24, 12, 4, 4)
        e1 = dict(index=1, stem='seg_0001', created='take1', frames=39, context_frames=0, played=25,
                  latent_width=64, latent_height=64, timeline=dict(box='a', layout='layout1'))
        store.save_segment(self.folder, e1, short_video, torch.zeros(1, 32, 2, 65), None)
        entries = {1: e1, 2: entry(2, 'c')}
        store.write_manifest(self.folder, dict(version=1, name='test', segments=list(entries.values())))
        doc = parsed([
            dict(id='a', frames=25, exact=True, prompt='Exact box', seed=1),
            dict(id='c', frames=90, prompt='Same-scene cut', seed=2, cut=True, memory='scene'),
        ])
        inf_c = self.info(doc, 1, entries)
        anc, off = protection.load_anchor_clip(self.segment(inf_c))
        self.assertEqual(off, 0)
        self.assertEqual(anc.shape[2], 8)
        self.assertTrue(torch.equal(anc, short_video[:, :, :8]))


if __name__ == '__main__':
    unittest.main()
