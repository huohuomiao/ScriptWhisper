from functools import lru_cache

import torch
from torch import nn

from nanovllm.utils.context import get_context


@lru_cache(maxsize=2)
def _get_attention_ops(device_type: str):
    if device_type == "cuda":
        from nanovllm.layers import attention_cuda

        return attention_cuda
    if device_type == "mlu":
        from nanovllm.layers import attention_mlu

        return attention_mlu
    raise RuntimeError(f"No Nano-vLLM attention backend for device type {device_type!r}")


class Attention(nn.Module):

    def __init__(
        self,
        num_heads: int,
        head_dim: int,
        scale: float,
        num_kv_heads: int,
    ):
        super().__init__()
        self.num_heads = num_heads
        self.head_dim = head_dim
        self.scale = scale
        self.num_kv_heads = num_kv_heads
        self.k_cache = self.v_cache = torch.tensor([])

    def forward(self, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor):
        context = get_context()
        ops = _get_attention_ops(q.device.type)
        k_cache, v_cache = self.k_cache, self.v_cache
        if k_cache.numel() and v_cache.numel():
            ops.store_kvcache(k, v, k_cache, v_cache, context.slot_mapping)

        if context.is_prefill:
            if context.block_tables is not None:  # prefix cache
                k, v = k_cache, v_cache
            return ops.prefill_attention(
                q,
                k,
                v,
                cu_seqlens_q=context.cu_seqlens_q,
                cu_seqlens_k=context.cu_seqlens_k,
                max_seqlen_q=context.max_seqlen_q,
                max_seqlen_k=context.max_seqlen_k,
                scale=self.scale,
                block_tables=context.block_tables,
            )

        return ops.decode_attention(
            q,
            k_cache,
            v_cache,
            context_lens=context.context_lens,
            block_tables=context.block_tables,
            max_seqlen_k=context.max_seqlen_k,
            scale=self.scale,
        )
