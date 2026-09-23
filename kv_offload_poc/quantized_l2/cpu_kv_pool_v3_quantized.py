#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CPUKVPoolV3Quantized —— Block-Major 量化 CPU KV block 池 (INT8 KV + FP32 Scale)。

在 V2 (Block-Major BF16 KV) 基础上, 把 CPU L2 从 BF16 KV 改成 **统一量化格式**:
  - KV:    (B, 2, L, H, T, D)  int8     ← 直接存 MLU native int8 KV, 不做 BF16 dequant
  - Scale: (B, 2, L, H, T)     float32  ← 直接存 MLU native per-token scale

核心设计 (§三/§十八): 一个 logical CPU block 必须同时拥有 KV 和 Scale, 二者共用
**同一个 allocator 和同一个 cpu_block_id**。allocate(i) 同时拿到 kv[i] + scale[i];
free(i) 同时释放二者。禁止为 Scale 单独创建第二套 block allocator, 禁止 KV(A)+Scale(B)
错配。

为什么 block-major (沿用 V2 思路):
  MLU native KV/scale 的 block 维 (index 2) 夹在 layer 维 (index 1) 内, 单个 logical
  block 是 strided 的。把 block 维提到最外层后, cpu_kv[id] / cpu_scale[id] 各自连续,
  host 端零 strided reformat, H2D/D2H 直达最终 CPU 池。

容量 (Qwen3-8B, block_size=16, L=36, H=8, D=128):
  int8 KV payload  = 2*36*8*16*128*1 = 1,179,648 bytes
  fp32 scale       = 2*36*8*16*4    =    36,864 bytes
  quantized block  = 1,216,512 bytes ≈ 1.1602 MiB
  vs BF16 block    = 2,359,296 bytes ≈ 2.2500 MiB
  capacity_ratio   = 2.2500 / 1.1602 ≈ 1.9394x

约束 (本阶段 PoC):
  - 简单 allocator (free list + used set), 无 LRU / ARC。
  - 不含 Scheduler / BlockManager / Attention 接入。
  - 不改 MLU 原始 KV/scale layout。
"""
from __future__ import annotations

from bisect import insort

import torch

class CPUKVPoolV3Quantized:
    """Block-Major 量化 CPU 固定内存池: INT8 KV + FP32 Scale, 共用单一 allocator。

    Args:
        num_layers:    模型层数 (Qwen3-8B = 36)
        num_kv_heads:  KV head 数 (TP=1 时 = 8)
        head_dim:      每 head 维度 (= 128)
        block_size:    每 block token 数 (MLU 默认 = 16)
        num_blocks:    预分配 CPU block 数 (capacity)
        kv_dtype:      KV dtype (默认 int8)
        scale_dtype:   Scale dtype (默认 float32)
    """

    def __init__(
        self,
        num_layers: int,
        num_kv_heads: int,
        head_dim: int,
        block_size: int,
        num_blocks: int = 128,
        kv_dtype: torch.dtype = torch.int8,
        scale_dtype: torch.dtype = torch.float32,
    ):
        self.num_layers = num_layers
        self.num_kv_heads = num_kv_heads
        self.head_dim = head_dim
        self.block_size = block_size
        self.kv_dtype = kv_dtype
        self.scale_dtype = scale_dtype
        self.capacity = num_blocks

        # Block-Major layout: block 维提到最外层
        #   cpu_kv[block_id]    = (2, L, H, T, D) int8     连续 logical KV block
        #   cpu_scale[block_id] = (2, L, H, T)    fp32    连续 logical scale block
        self.kv_shape = (num_blocks, 2, num_layers, num_kv_heads, block_size, head_dim)
        self.scale_shape = (num_blocks, 2, num_layers, num_kv_heads, block_size)

        # 一次性预分配 pinned CPU buffer (复用, 不在 store/load 循环里 malloc)
        self.kv = torch.empty(self.kv_shape, dtype=kv_dtype, device="cpu", pin_memory=True)
        self.scale = torch.empty(self.scale_shape, dtype=scale_dtype, device="cpu", pin_memory=True)
        if not self.kv.is_pinned():
            raise RuntimeError(
                "CPUKVPoolV3Quantized: pin_memory=True requested but kv.is_pinned()==False; "
                "pinned memory 不可用, 无法保证 H2D/D2H 带宽"
            )
        if not self.scale.is_pinned():
            raise RuntimeError(
                "CPUKVPoolV3Quantized: scale pin_memory=True requested but is_pinned()==False"
            )

        # 单个 logical CPU block 的字节数 (KV + Scale)
        self.kv_block_bytes = (
            2 * num_layers * num_kv_heads * block_size * head_dim * kv_dtype.itemsize
        )
        self.scale_block_bytes = (
            2 * num_layers * num_kv_heads * block_size * scale_dtype.itemsize
        )
        self.block_bytes = self.kv_block_bytes + self.scale_block_bytes

        # 单一 allocator: KV 与 Scale 共用同一套 block id (§三/§十八)
        self._free: list[int] = list(range(num_blocks))
        self._used: set[int] = set()

    # ------------------------------------------------------------------
    # 连续性验证 (必须 True, 否则 block-major 设计不成立)
    # ------------------------------------------------------------------
    def block_is_contiguous(self, block_id: int = 0) -> bool:
        """单个 logical block 的 KV 和 Scale 是否都真正连续。"""
        return self.kv[block_id].is_contiguous() and self.scale[block_id].is_contiguous()

    def partition_is_contiguous(self, start: int, end: int) -> bool:
        """一段连续 cpu_ids 的整段 [start:end) KV 和 Scale 是否都连续。"""
        return (self.kv[start:end].is_contiguous()
                and self.scale[start:end].is_contiguous())

    def kv_block_view(self, block_id: int) -> torch.Tensor:
        """返回 cpu_kv[block_id] 的 view, shape (2,L,H,T,D), 连续。"""
        if not isinstance(block_id, int) or block_id < 0 or block_id >= self.capacity:
            raise RuntimeError(f"kv_block_view: 非法 block id {block_id}")
        return self.kv[block_id]

    def scale_block_view(self, block_id: int) -> torch.Tensor:
        """返回 cpu_scale[block_id] 的 view, shape (2,L,H,T), 连续。"""
        if not isinstance(block_id, int) or block_id < 0 or block_id >= self.capacity:
            raise RuntimeError(f"scale_block_view: 非法 block id {block_id}")
        return self.scale[block_id]
        def kv_slice(self, start: int, end: int) -> torch.Tensor:
        """连续逻辑 block 的 KV 整段 view [start:end), shape (end-start,2,L,H,T,D), 连续。"""
        if start < 0 or end <= start or end > self.capacity:
            raise IndexError(f"kv_slice: 非法范围 [{start}:{end}) (capacity={self.capacity})")
        return self.kv[start:end]

    def scale_slice(self, start: int, end: int) -> torch.Tensor:
        """连续逻辑 block 的 Scale 整段 view [start:end), shape (end-start,2,L,H,T), 连续。"""
        if start < 0 or end <= start or end > self.capacity:
            raise IndexError(f"scale_slice: 非法范围 [{start}:{end}) (capacity={self.capacity})")
        return self.scale[start:end]

    # ------------------------------------------------------------------
    # 分配 / 释放 (单一 allocator: KV 与 Scale 一起分配/释放)
    # ------------------------------------------------------------------
    def allocate(self, num_blocks: int) -> list[int]:
        """分配 num_blocks 个 CPU block, 返回连续升序 block id 列表。

        每个 id 同时对应 kv[id] 与 scale[id] —— 一个完整量化 logical block。
        """
        if num_blocks < 0:
            raise ValueError(f"allocate: num_blocks 不能为负, got {num_blocks}")
        if num_blocks > len(self._free):
            raise RuntimeError(
                f"allocate: 请求 {num_blocks} blocks, 仅剩 {len(self._free)} 可用 "
                f"(capacity={self.capacity}, used={len(self._used)})"
            )
        ids = [self._free.pop(0) for _ in range(num_blocks)]
        self._used.update(ids)
        return ids

  def free(self, block_ids):
        """释放 block id (KV 与 Scale 一起失效)。double free / 非法 id: 抛 RuntimeError。"""
        if isinstance(block_ids, int):
            block_ids = [block_ids]
        for bid in block_ids:
            if not isinstance(bid, int) or bid < 0 or bid >= self.capacity:
                raise RuntimeError(f"free: 非法 block id {bid} (capacity={self.capacity})")
            if bid not in self._used:
                raise RuntimeError(
                    f"free: block id {bid} 未分配 (double free 或从未分配)"
                )
            self._used.discard(bid)
            insort(self._free, bid)

    # ------------------------------------------------------------------
    # 查询 / 诊断
    # ------------------------------------------------------------------
    def num_free_blocks(self) -> int:
        return len(self._free)

    def num_used_blocks(self) -> int:
        return len(self._used)

    def is_pinned(self) -> bool:
        return self.kv.is_pinned() and self.scale.is_pinned()

    @property
    def kv_mem_bytes(self) -> int:
        return self.kv.numel() * self.kv.element_size()

    @property
    def scale_mem_bytes(self) -> int:
        return self.scale.numel() * self.scale.element_size()

    @property
    def mem_bytes(self) -> int:
        return self.kv_mem_bytes + self.scale_mem_bytes

    def __repr__(self) -> str:
        return (
            f"CPUKVPoolV3Quantized(kv_shape={self.kv_shape}, scale_shape={self.scale_shape}, "
            f"kv_dtype={self.kv_dtype}, scale_dtype={self.scale_dtype}, "
            f"capacity={self.capacity}, free={len(self._free)}, "
            f"used={len(self._used)}, kv_block={self.kv_block_bytes/1024**2:.4f}MiB, "
            f"scale_block={self.scale_block_bytes/1024**2:.4f}MiB, "
            f"block={self.block_bytes/1024**2:.4f}MiB, pinned={self.is_pinned()}, "
            f"block0_contig={self.block_is_contiguous()})"
        )

