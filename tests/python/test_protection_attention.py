import types
import unittest
from unittest import mock

import torch
from tests.continuity_support import enable_comfy_cpu

enable_comfy_cpu()
import comfy.ops
from comfy.ldm.minimax.model import MiniMaxH3Model, mask_row_values
from h3_continuity import protection
from tests.python.test_protection_latent import carried
from tests.python.test_protection_sampling import patcher, run


def explicit(q, k, v, anchor, context, balance):
    p = torch.softmax(q @ k.transpose(-1, -2) / q.shape[-1] ** .5, dim=-1)
    a, c = p[..., anchor].sum(-1, keepdim=True), p[..., context].sum(-1, keepdim=True)
    new = (a + c) * balance * a / (balance * a + c)
    p[..., anchor] *= new / a
    p[..., context] *= (a + c - new) / c
    return (p @ v).transpose(1, 2).reshape(1, q.shape[2], -1)


def tiny_model():
    torch.manual_seed(0)
    model = MiniMaxH3Model(hidden_size=256, num_layers=3, token_refiner_num_layers=1, num_attention_heads=2,
                           attention_head_dim=128, ffn_hidden_size=64, text_dim=64, timestep_input_dim=32,
                           time_embed_hidden_size=64, time_embed_dim=32, dtype=torch.float32,
                           operations=comfy.ops.disable_weight_init)
    for parameter in model.parameters():
        torch.nn.init.normal_(parameter, std=.2)
    model.rope.inv_freq.copy_(torch.rand(16))
    return model.requires_grad_(False)


def tiny_forward(model, override=None, frames=6):
    torch.manual_seed(1)
    video, audio, text = torch.randn(1, 24, 7, 4, 6), torch.randn(1, 32, 2, 10), torch.randn(1, 7, 64)
    # The protection layout: clean front, linear carried fade, free frames; a capstone is one more held latent.
    mask = torch.ones(1, 1, 7, 4, 6)
    mask[:, :, 0] = 0
    mask[:, :, 1:4] = torch.linspace(1, 0, 3).view(1, 1, 3, 1, 1)
    mask[:, :, 6] = 0
    options = {'optimized_attention_override': override} if override else {}
    with torch.no_grad():
        return model.forward([video[:, :, :frames], audio], torch.tensor([500.]), text,
                             transformer_options=options, denoise_mask=mask[:, :, :frames])[0], mask[:, :, :frames]


class BalancedAttentionTest(unittest.TestCase):
    def test_blocks_parse_ranges_and_reject_text(self):
        self.assertEqual(protection.parse_blocks(protection.LIGHTING_BLOCKS),
                         frozenset([31, 32, 33, *range(36, 45), 47]))
        self.assertEqual(protection.parse_blocks(' 3 - 1; 9,'), frozenset([1, 2, 3, 9]))
        self.assertEqual(protection.parse_blocks(''), frozenset())
        for bad in ('a', '1-2-3', '-4'):
            with self.assertRaisesRegex(ValueError, 'attention blocks'):
                protection.parse_blocks(bad)

    def test_only_the_shared_share_moves(self):
        torch.manual_seed(0)
        q, k, v = (torch.randn(1, 5, 11, 8, dtype=torch.float64) for _ in range(3))
        anchor, context = torch.tensor([2, 3]), torch.tensor([5, 6, 9])
        plain = torch.nn.functional.scaled_dot_product_attention(q, k, v).transpose(1, 2).reshape(1, 11, -1)
        for balance in (1., .5, 20., 0.):
            out = protection.balanced_attention(q, k, v, anchor, context, balance)
            self.assertTrue(torch.allclose(out, explicit(q, k, v, anchor, context, balance), atol=1e-9), balance)
        self.assertTrue(torch.allclose(protection.balanced_attention(q, k, v, anchor, context, 1.), plain, atol=1e-9))
        self.assertFalse(torch.allclose(protection.balanced_attention(q, k, v, anchor, context, 20.), plain, atol=1e-3))

    def test_native_model_balances_our_rows_on_chosen_blocks_only(self):
        model = tiny_model()
        for frames in (6, 7):
            receipt, deferred = protection.ProtectionReceipt(), []

            def previous(func, q, k, v, heads, **kwargs):
                deferred.append((kwargs['transformer_options'].get('block_index'), q.shape[-2]))
                return func(q, k, v, heads, **kwargs)

            override = protection.attention_override(previous, receipt, 6, [3], 20., frozenset([1]))
            with mock.patch.object(protection, 'balanced_attention', wraps=protection.balanced_attention) as balanced:
                out, mask = tiny_forward(model, override, frames)
            self.assertEqual((receipt.balanced, balanced.call_count), (1, 1))
            anchor, context = balanced.call_args.args[3:5]
            # Core's own per-row mask values: text 7 rows, audio 20 rows, then 6 rows per video latent.
            values = mask_row_values(mask[0, 0], frames, 4, 6)
            start = 7 + 20
            self.assertTrue(bool((values[torch.cat((anchor, context)) - start] == 0).all()))
            self.assertEqual(anchor.tolist(), [*range(start, start + 6), *range(start + 36, start + 6 * frames)])
            self.assertEqual(context.tolist(), list(range(start + 18, start + 24)))
            # The text refiner (7 rows) and the other blocks stay with the previous attention.
            self.assertEqual(deferred, [(None, 7), (0, 27 + 6 * frames), (2, 27 + 6 * frames)])
            self.assertFalse(torch.allclose(out, tiny_forward(model, None, frames)[0], atol=1e-4))

    def test_balance_one_through_the_override_matches_native_attention(self):
        model = tiny_model()
        override = protection.attention_override(None, protection.ProtectionReceipt(), 6, [3], 1., frozenset([0, 1, 2]))
        self.assertTrue(torch.allclose(tiny_forward(model, override)[0], tiny_forward(model)[0], atol=1e-4))

    def test_other_clip_lengths_pass_through(self):
        receipt = protection.ProtectionReceipt()
        override = protection.attention_override(None, receipt, 4, [3], 20., frozenset([1]))
        out, _ = tiny_forward(tiny_model(), override)
        self.assertEqual(receipt.balanced, 0)
        self.assertTrue(torch.equal(out, tiny_forward(tiny_model())[0]))


class ProtectedSamplingAttentionTest(unittest.TestCase):
    def setup_model(self, balance, blocks=frozenset([31])):
        latent, segment, front = carried()
        prepared, originals = protection.prepare_latent(latent, segment, front)
        base, attend = patcher(), {}

        def previous(fn, args):
            if attend:
                attend['call']()
            return fn(args['input'], args['timestep'], **args['c'])

        base.set_model_unet_function_wrapper(previous)
        with mock.patch.object(protection, '_current_source'):
            model, receipt = protection.patch_model(base, prepared, segment, originals, front,
                                                    dict(method=protection.METHOD, source_stamp=[1, 2]), balance, blocks)
        return base, model, prepared, receipt, attend

    def test_balance_is_off_by_default_and_never_touches_the_source_model(self):
        for balance, blocks in ((1., frozenset([31])), (20., frozenset())):
            base, model, prepared, receipt, _ = self.setup_model(balance, blocks)
            self.assertNotIn('optimized_attention_override', model.model_options.get('transformer_options', {}))
            with mock.patch.object(protection, '_current_source'):
                run(model, prepared)
            self.assertIsNone(receipt.descriptor['attention_balance'])
        base, model, *_ = self.setup_model(20.)
        self.assertNotIn('optimized_attention_override', base.model_options.get('transformer_options', {}))
        self.assertEqual(model.model_options['transformer_options']['optimized_attention_override'].h3c_balance, 20.)

    def test_replaced_attention_fails_instead_of_saving_an_unbalanced_clip(self):
        _, model, prepared, receipt, _ = self.setup_model(20.)
        with mock.patch.object(protection, '_current_source'):
            with self.assertRaisesRegex(ValueError, 'attention balance never ran'):
                run(model, prepared)
        self.assertFalse(receipt.complete)

    def test_balanced_run_records_its_settings(self):
        _, model, prepared, receipt, attend = self.setup_model(20.)
        override = model.model_options['transformer_options']['optimized_attention_override']
        # carried(): 37 video latents of 4 rows after 3 text rows.
        layout = types.SimpleNamespace(segments=[(0, 3, 'text'), (3, 151, 'video')], signature=(3, 37, 4, 4, 0), seq_len=151)
        q, k, v = (torch.randn(1, 2, 151, 8) for _ in range(3))
        attend['call'] = lambda: override(None, q, k, v, 2, skip_reshape=True,
                                          transformer_options=dict(block_index=31, minimax_h3_layout=layout))
        with mock.patch.object(protection, '_current_source'):
            run(model, prepared)
        self.assertTrue(receipt.complete)
        self.assertEqual((receipt.descriptor['attention_balance'], receipt.descriptor['attention_blocks']), (20., [31]))
        self.assertEqual(receipt.balanced, 16)


if __name__ == '__main__':
    unittest.main()
