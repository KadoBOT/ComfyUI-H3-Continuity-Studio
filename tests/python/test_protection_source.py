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

    def test_in_chain_plate_change_suppresses_until_next_fresh_box(self):
        doc = parsed()
        doc.boxes[1].plate_changes = [dict(frame=17)]
        self.assertEqual(self.info(doc, 1)['status'], 'skip')
        self.assertEqual(self.info(doc, 2)['status'], 'skip')
        doc.boxes[1].plate_changes = []
        doc.boxes[1].new_scene = True
        self.assertEqual(self.info(doc, 2)['status'], 'skip')
        doc.boxes[2].cut = True
        self.assertEqual(self.info(doc, 2)['status'], 'skip')

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

    def test_cut_memory_traces_clean_scene_root_and_skips_new_scene_flashbacks(self):
        # a (kitchen, fresh) -> b (cont) -> c (cut, same scene) -> d (cont of c) -> e (new_scene flashback, mem off)
        # -> f (new_scene + selected -> c) -> g (cut, same scene as f)
        boxes = [
            dict(id='a', frames=90, prompt='Kitchen', seed=1),
            dict(id='b', frames=85, prompt='Continue', seed=2),
            dict(id='c', frames=90, prompt='Cut kitchen', seed=3, cut=True, memory='scene'),
            dict(id='d', frames=85, prompt='Continue cut', seed=4),
            dict(id='e', frames=90, prompt='Hospital flashback', seed=5, cut=True, new_scene=True, memory='off'),
            dict(id='f', frames=90, prompt='Back to kitchen', seed=6, cut=True, new_scene=True,
                 memory='selected', memories=[dict(box='c', frame=20)]),
            dict(id='g', frames=90, prompt='Low angle kitchen', seed=7, cut=True, memory='scene'),
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
        inf_f = self.info(doc, 5, entries)
        self.assertEqual((inf_f['mode'], inf_f['source']['timeline']['box']), ('cut_memory', 'a'))
        inf_g = self.info(doc, 6, entries)
        self.assertEqual((inf_g['mode'], inf_g['source']['timeline']['box']), ('cut_memory', 'a'))

        doc_cast = parsed([
            dict(id='a', frames=90, prompt='Kitchen', seed=1),
            dict(id='e', frames=90, prompt='Hospital', seed=2, cut=True, new_scene=True, memory='off'),
            dict(id='h', frames=90, prompt='Back', seed=3, cut=True, new_scene=True, memory='cast'),
        ])
        entries_cast = {1: entry(1, 'a'), 2: entry(2, 'e'), 3: entry(3, 'h')}
        with mock.patch.object(protection.timeline, 'memory_sources', return_value=[(1, 0, 'prev'), (0, 20, 'cast')]):
            inf_h = self.info(doc_cast, 2, entries_cast)
        self.assertEqual((inf_h['mode'], inf_h['source']['timeline']['box']), ('cut_memory', 'a'))

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


if __name__ == '__main__':
    unittest.main()
