import torch

from nanovllm.layers import attention_mlu


class FakeMLUOps:
    def __init__(self):
        self.reshape_args = None
        self.flash_args = None
        self.decode_args = None

    def reshape_paged_cache(self, *args):
        self.reshape_args = args

    def flash_attention(self, *args):
        self.flash_args = args
        args[3].copy_(args[0] + 10)

    def single_query_cached_kv_attn(self, *args, **kwargs):
        self.decode_args = (args, kwargs)
        args[3].copy_(args[0] + 20)


def test_mlu_cache_store_uses_vendor_layout_operator(monkeypatch):
    fake = FakeMLUOps()
    monkeypatch.setattr(attention_mlu, "_get_torch_mlu_ops", lambda: fake)
    key = torch.randn(3, 2, 8)
    value = torch.randn(3, 2, 8)
    key_cache = torch.empty(4, 2, 16, 8)
    value_cache = torch.empty_like(key_cache)
    slots = torch.tensor([0, 17, 35], dtype=torch.int32)

    attention_mlu.store_kvcache(key, value, key_cache, value_cache, slots)

    assert fake.reshape_args is not None
    assert fake.reshape_args[2].shape == (4, 2, 16, 8)
    assert torch.equal(fake.reshape_args[4], slots)


def test_mlu_prefill_passes_paged_cache_metadata(monkeypatch):
    fake = FakeMLUOps()
    monkeypatch.setattr(attention_mlu, "_get_torch_mlu_ops", lambda: fake)
    query = torch.randn(3, 4, 8)
    key_cache = torch.empty(4, 2, 16, 8)
    value_cache = torch.empty_like(key_cache)
    cu_seqlens = torch.tensor([0, 3], dtype=torch.int32)
    block_tables = torch.tensor([[1, 2]], dtype=torch.int32)

    output = attention_mlu.prefill_attention(
        query,
        key_cache,
        value_cache,
        cu_seqlens_q=cu_seqlens,
        cu_seqlens_k=cu_seqlens,
        max_seqlen_q=3,
        max_seqlen_k=3,
        scale=0.125,
        block_tables=block_tables,
    )

    assert torch.equal(output, query + 10)
    assert fake.flash_args[16] is block_tables
    assert fake.flash_args[21] == query.dtype


def test_mlu_decode_uses_cached_kv_operator(monkeypatch):
    fake = FakeMLUOps()
    monkeypatch.setattr(attention_mlu, "_get_torch_mlu_ops", lambda: fake)
    query = torch.randn(2, 4, 8)
    key_cache = torch.empty(4, 2, 16, 8)
    value_cache = torch.empty_like(key_cache)
    context_lens = torch.tensor([9, 17], dtype=torch.int32)
    block_tables = torch.tensor([[0, -1], [1, 2]], dtype=torch.int32)

    output = attention_mlu.decode_attention(
        query,
        key_cache,
        value_cache,
        context_lens=context_lens,
        block_tables=block_tables,
        max_seqlen_k=17,
        scale=0.125,
    )

    assert torch.equal(output, query + 20)
    args, kwargs = fake.decode_args
    assert args[0].shape == (2, 1, 4, 8)
    assert args[4] is block_tables
    assert args[9] == 17
    assert kwargs["compute_dtype"] == torch.float32
