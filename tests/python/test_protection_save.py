import asyncio
import json
import tempfile
import unittest
from unittest import mock

import torch
from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()
from comfy.nested_tensor import NestedTensor
from h3_continuity import extension, nodes, protection, store
from tests.python.test_protection_latent import carried
from tests.python.test_protection_sampling import patcher, run


class ProtectionSaveTest(unittest.TestCase):
    def prepare(self):
        latent,segment,front=carried()
        segment.timeline={'box':'b','details':{'kept':True}}
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        segment.sequence=nodes.SequenceRef('test',self.temp.name,1,None,None,None)
        descriptor=dict(method=protection.METHOD,source_box='a',source_stamp=[1,2])
        with mock.patch.object(protection,'load_anchors',return_value=(front,front,descriptor)):
            model,prepared,owned,info=protection.H3C_ContinuityProtection.execute(patcher(),latent,segment).args
        return model,prepared,owned,segment,latent

    def test_disabled_and_fresh_node_pass_through_without_source_reads(self):
        latent,segment,front=carried();model=object()
        with mock.patch.object(protection,'load_anchors',side_effect=AssertionError('unexpected read')):
            output=protection.H3C_ContinuityProtection.execute(model,latent,segment,False).args
            self.assertEqual(tuple(id(v) for v in output[:3]),tuple(map(id,(model,latent,segment))))
            segment.carried_video=None
            output=protection.H3C_ContinuityProtection.execute(model,latent,segment).args
            self.assertIs(output[2],segment)
            segment.carried_video=front
            segment.protection_source=dict(status='skip',reason='appearance change')
            output=protection.H3C_ContinuityProtection.execute(model,latent,segment).args
            self.assertIs(output[1],latent)
            self.assertIn('appearance change',output[3])

    def test_bridge_replacement_and_layer_pass_through_without_anchor(self):
        latent,segment,front=carried()
        segment.protection_source=None
        model=object()
        with mock.patch.object(protection,'load_anchors',side_effect=AssertionError('unexpected source read')):
            for kind in ('bridge','replacement','layer'):
                segment.timeline={kind:'b'}
                output=protection.H3C_ContinuityProtection.execute(model,latent,segment).args
                self.assertIs(output[0],model)
                self.assertIs(output[1],latent)
                self.assertIs(output[2],segment)

    def test_save_accepts_normal_or_denoised_receipt_only(self):
        model,prepared,owned,original,latent=self.prepare()
        with mock.patch.object(protection,'_current_source'):
            outputs,_=run(model,prepared)
        self.assertIsNot(owned,original)
        self.assertIsNot(owned.timeline,original.timeline)
        self.assertIsNot(owned.timeline['details'],original.timeline['details'])
        for output in outputs:
            descriptor=protection.validate_save(owned,output)
            self.assertEqual(descriptor['method'],protection.METHOD)
        self.assertNotIn('degradation_protection',original.timeline)
        self.assertIsNone(protection.validate_save(original,latent))
        with self.assertRaisesRegex(ValueError,'segment'):
            protection.validate_save(original,outputs[0])
        stale=dict(outputs[0],samples=outputs[0]['samples']+1)
        with self.assertRaisesRegex(ValueError,'output'):
            protection.validate_save(owned,stale)

    def test_save_rejects_pending_failed_stale_or_plain_cached_output_before_writes(self):
        model,prepared,owned,original,latent=self.prepare()
        with mock.patch.object(protection,'_current_source'):
            outputs,_=run(model,prepared)
        cases=[(owned,prepared),(owned,latent),(original,outputs[0])]
        modified=dict(outputs[0],samples=NestedTensor((outputs[0]['samples'].tensors[0].expand(2,-1,-1,-1,-1),
                                                     outputs[0]['samples'].tensors[1].expand(2,-1,-1,-1))))
        cases.append((owned,modified))
        with mock.patch('h3_continuity.timeline_api.service.authorize_sequence',return_value=None), \
                mock.patch.object(nodes.os,'makedirs',side_effect=AssertionError('write before validation')), \
                mock.patch.object(store,'save_segment',side_effect=AssertionError('write before validation')), \
                mock.patch.object(store,'archive_from',side_effect=AssertionError('take move before validation')):
            for segment,result in cases:
                with self.assertRaisesRegex(ValueError,'Protection|protection'):
                    nodes.H3C_SaveSegment.execute(segment,result,24,False,16)
            with mock.patch.object(protection,'_current_source'):
                with self.assertRaises(RuntimeError):run(model,prepared,fail=True)
            with self.assertRaisesRegex(ValueError,'Protection|protection'):
                nodes.H3C_SaveSegment.execute(owned,outputs[0],24,False,16)

    def test_metadata_contains_only_applied_descriptor(self):
        model,prepared,owned,original,latent=self.prepare()
        with mock.patch.object(protection,'_current_source'):
            outputs,_=run(model,prepared)
        with mock.patch('h3_continuity.timeline_api.service.authorize_sequence',return_value=None):
            nodes.H3C_SaveSegment.execute(owned,outputs[1],24,False,16)
        record=store.load_manifest(self.temp.name)['segments'][0]
        self.assertEqual(record['timeline']['degradation_protection']['method'],protection.METHOD)
        raw=json.dumps(record)
        self.assertNotIn('accepted',raw)
        self.assertNotIn('receipt',raw)
        self.assertNotIn('protection_source',raw)
        self.assertNotIn('degradation_protection',original.timeline)

    def test_node_schema_and_inventory_are_complete(self):
        cls=protection.H3C_ContinuityProtection
        schema=cls.define_schema()
        self.assertEqual(schema.node_id,'H3C_ContinuityProtection')
        self.assertEqual([v.id for v in schema.inputs],['model','latent','segment','enabled'])
        self.assertTrue(schema.inputs[-1].default)
        self.assertEqual([v.io_type for v in schema.outputs],['MODEL','LATENT','H3C_SEGMENT','STRING'])
        self.assertIn(cls,asyncio.run(extension.H3ContinuityExtension().get_node_list()))


if __name__=='__main__':unittest.main()
