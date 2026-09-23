from functools import lru_cache

import torch


@lru_cache(maxsize=1)
def _get_torch_mlu_ops():
    try:
        import torch_mlu_ops
    except ImportError as exc:
        raise RuntimeError(
            "MLU attention requires torch_mlu_ops. Install Nano-vLLM with "
            "the 'mlu' optional dependencies inside a Cambricon SDK container."
        ) from exc

    required_ops = (
        "flash_attention",
        "reshape_paged_cache",
        "single_query_cached_kv_attn",
    )
    missing = [name for name in required_ops if not hasattr(torch_mlu_ops, name)]
    if missing:
        raise RuntimeError(
            "torch_mlu_ops is missing required operator(s): " + ", ".join(missing)
        )
    return torch_mlu_ops


def store_kvcache(
    key: torch.Tensor,
    value: torch.Tensor,
    k_cache: torch.Tensor,
    v_cache: torch.Tensor,
    slot_mapping: torch.Tensor,
) -> None:
    ops = _get_torch_mlu_ops()
    ops.reshape_paged_cache(
        key.contiguous(),
        value.contiguous(),
        k_cache,
        v_cache,
        slot_mapping.flatten(),
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
    ops = _get_torch_mlu_ops()
    q = q.contiguous()
    if block_tables is None:
        k = k.contiguous()
        v = v.contiguous()
    output = torch.empty_like(q)
    ops.flash_attention(
        q,
        k,
        v,
        output,
        cu_seqlens_q,
        cu_seqlens_k,
        None,  # alibi slopes
        None,  # attention bias
        max_seqlen_q,
        max_seqlen_k,
        scale,
        True,  # causal
        -1,  # left window
        -1,  # right window
        torch.float32,
        False,  # return LSE
        block_tables,
        None,  # K-cache quantization scale
        None,  # V-cache quantization scale
        None,  # Q quantization scale
        None,  # output quantization scale
        q.dtype,
    )
    return output


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
    ops = _get_torch_mlu_ops()
    batch_size = q.shape[0]
    query = q.contiguous().view(batch_size, 1, q.shape[1], q.shape[2])
    output = torch.empty_like(query)
    ops.single_query_cached_kv_attn(
        query,
        k_cache,
        v_cache,
        output,
        block_tables,
        context_lens,
        None,  # K-cache quantization scale
        None,  # V-cache quantization scale
        None,  # alibi slopes
        max_seqlen_k,
        -1,  # left window
        -1,  # right window
        scale,
        False,  # return LSE
        head_size_v=-1,
        compute_dtype=torch.float32,
    )
    return output.view_as(q)
