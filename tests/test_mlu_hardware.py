import os

import pytest
import torch

from nanovllm.layers import attention_mlu
from nanovllm.layers.sampler import Sampler


if os.environ.get("RUN_MLU_TESTS") != "1":
    pytest.skip("set RUN_MLU_TESTS=1 to run MLU hardware tests", allow_module_level=True)

pytest.importorskip("torch_mlu")
pytest.importorskip("torch_mlu_ops")
if not torch.mlu.is_available():
    pytest.skip("no MLU device is available", allow_module_level=True)


pytestmark = pytest.mark.mlu


def _reference_attention(query, key, value, scale, causal):
    repeats = query.shape[1] // key.shape[1]
    key = key.repeat_interleave(repeats, dim=1).float()
    value = value.repeat_interleave(repeats, dim=1).float()
    scores = torch.einsum("thd,shd->hts", query.float(), key) * scale
    if causal:
        mask = torch.triu(
            torch.ones(
                query.shape[0],
                key.shape[0],
                dtype=torch.bool,
                device=query.device,
            ),
            diagonal=1,
        )
        scores.masked_fill_(mask.unsqueeze(0), float("-inf"))
    probabilities = torch.softmax(scores, dim=-1)
    return torch.einsum("hts,shd->thd", probabilities, value)


def test_mlu_prefill_matches_pytorch_reference():
    torch.manual_seed(0)
    device = torch.device("mlu:0")
    dtype = torch.bfloat16
    query = torch.randn(4, 2, 32, dtype=dtype, device=device)
    key = torch.randn(4, 1, 32, dtype=dtype, device=device)
    value = torch.randn(4, 1, 32, dtype=dtype, device=device)
    cu_seqlens = torch.tensor([0, 4], dtype=torch.int32, device=device)
    scale = 32**-0.5

    actual = attention_mlu.prefill_attention(
        query,
        key,
        value,
        cu_seqlens_q=cu_seqlens,
        cu_seqlens_k=cu_seqlens,
        max_seqlen_q=4,
        max_seqlen_k=4,
        scale=scale,
        block_tables=None,
    )
    expected = _reference_attention(query, key, value, scale, causal=True)

    torch.testing.assert_close(
        actual.float().cpu(),
        expected.float().cpu(),
        atol=5e-2,
        rtol=5e-2,
    )


def test_mlu_paged_cache_decode_matches_pytorch_reference():
    torch.manual_seed(1)
    device = torch.device("mlu:0")
    dtype = torch.bfloat16
    key = torch.randn(4, 1, 32, dtype=dtype, device=device)
    value = torch.randn(4, 1, 32, dtype=dtype, device=device)
    key_cache = torch.zeros(1, 1, 16, 32, dtype=dtype, device=device)
    value_cache = torch.zeros_like(key_cache)
    slots = torch.arange(4, dtype=torch.int32, device=device)
    attention_mlu.store_kvcache(key, value, key_cache, value_cache, slots)

    query = torch.randn(1, 2, 32, dtype=dtype, device=device)
    context_lens = torch.tensor([4], dtype=torch.int32, device=device)
    block_tables = torch.tensor([[0]], dtype=torch.int32, device=device)
    scale = 32**-0.5
    actual = attention_mlu.decode_attention(
        query,
        key_cache,
        value_cache,
        context_lens=context_lens,
        block_tables=block_tables,
        max_seqlen_k=4,
        scale=scale,
    )
    expected = _reference_attention(query, key, value, scale, causal=False)

    torch.testing.assert_close(
        actual.float().cpu(),
        expected.float().cpu(),
        atol=5e-2,
        rtol=5e-2,
    )


def test_mlu_random_sampler_contract():
    logits = torch.randn(3, 128, dtype=torch.bfloat16, device="mlu:0")
    temperatures = torch.tensor([0.6, 0.8, 1.0], device="mlu:0")

    sampled = Sampler()(logits, temperatures)

    assert sampled.shape == (3,)
    assert sampled.dtype in (torch.int32, torch.int64)
    assert bool(((sampled >= 0) & (sampled < logits.shape[1])).all())
