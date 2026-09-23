import torch
import triton
import triton.language as tl

from flash_attn import flash_attn_varlen_func, flash_attn_with_kvcache


@triton.jit
def store_kvcache_kernel(
    key_ptr,
    key_stride,
    value_ptr,
    value_stride,
    k_cache_ptr,
    v_cache_ptr,
    slot_mapping_ptr,
    D: tl.constexpr,
):
    idx = tl.program_id(0)
    slot = tl.load(slot_mapping_ptr + idx)
    if slot == -1:
        return
    key_offsets = idx * key_stride + tl.arange(0, D)
    value_offsets = idx * value_stride + tl.arange(0, D)
    key = tl.load(key_ptr + key_offsets)
    value = tl.load(value_ptr + value_offsets)
    cache_offsets = slot * D + tl.arange(0, D)
    tl.store(k_cache_ptr + cache_offsets, key)
    tl.store(v_cache_ptr + cache_offsets, value)


def store_kvcache(
    key: torch.Tensor,
    value: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    slot_mapping: torch.Tensor,
) -> None:
    num_tokens, num_heads, head_dim = key.shape
    hidden_size = num_heads * head_dim
    assert key.stride(-1) == 1 and value.stride(-1) == 1
    assert key.stride(1) == head_dim and value.stride(1) == head_dim
    assert k_cache.stride(1) == hidden_size and v_cache.stride(1) == hidden_size
    assert slot_mapping.numel() == num_tokens
    store_kvcache_kernel[(num_tokens,)](
        key,
        key.stride(0),
        value,
        value.stride(0),
        k_cache,
        v_cache,
        slot_mapping,
        hidden_size,
    )


def prefill_attention(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    *,
    cu_seqlens_q: torch.Tensor,
    cu_seqlens_k: torch.Tensor,
    max_seqlen_q: int,
    max_seqlen_k: int,
    scale: float,
    block_tables: torch.Tensor | None,
) -> torch.Tensor:
    return flash_attn_varlen_func(
        q,
        k,
        v,
        max_seqlen_q=max_seqlen_q,
        cu_seqlens_q=cu_seqlens_q,
        max_seqlen_k=max_seqlen_k,
        cu_seqlens_k=cu_seqlens_k,
        softmax_scale=scale,
        causal=True,
        block_table=block_tables,
    )


def decode_attention(
    q: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    *,
    context_lens: torch.Tensor,
    block_tables: torch.Tensor,
    max_seqlen_k: int,
    scale: float,
) -> torch.Tensor:
    del max_seqlen_k
    return flash_attn_with_kvcache(
        q.unsqueeze(1),
        k_cache,
        v_cache,
        cache_seqlens=context_lens,
        block_table=block_tables,
        softmax_scale=scale,
        causal=True,
    )
