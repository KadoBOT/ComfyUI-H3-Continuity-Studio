import json
import unittest

import torch

from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()

import comfy.nested_tensor  # noqa: E402
from h3_continuity import latents  # noqa: E402


class ContinuationSettingsTest(unittest.TestCase):
    def parse(self, **keys):
        from h3_continuity import timeline
        data = {"version": 1, "boxes": [{"id": "a", "frames": 124, "seed": 1, "prompt": "p"},
                                        {"id": "b", "frames": 124, "seed": 2, "prompt": "q"}], **keys}
        return timeline, timeline.parse(json.dumps(data))

    def test_defaults_leave_layouts_unchanged(self):
        timeline, parsed = self.parse()
        self.assertEqual(parsed.continuation_guide, "auto")
        _, marked = self.parse(continuation_guide="auto")
        self.assertEqual(timeline.layout_key(parsed, 1), timeline.layout_key(marked, 1))

    def test_settings_change_only_continuing_layouts(self):
        timeline, plain = self.parse()
        _, always_on = self.parse(continuation_guide=True)
        _, always_off = self.parse(continuation_guide=False)
        self.assertEqual(timeline.layout_key(plain, 0), timeline.layout_key(always_on, 0))
        self.assertEqual(timeline.layout_key(plain, 0), timeline.layout_key(always_off, 0))
        self.assertNotEqual(timeline.layout_key(plain, 1), timeline.layout_key(always_on, 1))
        self.assertNotEqual(timeline.layout_key(plain, 1), timeline.layout_key(always_off, 1))
        self.assertNotEqual(timeline.layout_key(always_on, 1), timeline.layout_key(always_off, 1))

    def test_invalid_values_fail(self):
        for keys in ({"continuation_guide": "no"}, {"continuation_guide": 0}, {"continuation_guide": 1}):
            with self.assertRaises(ValueError):
                self.parse(**keys)


if __name__ == "__main__":
    unittest.main()
