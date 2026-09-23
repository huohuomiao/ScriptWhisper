"""CPUKVPoolV2 —— Block-Major CPU pinned KV block 池。

解决 V1 瓶颈的核心:
  V1 layout: (2, num_layers, B, num_kv_heads, block_size, head_dim)
     block 维 (index 2) 在 layer 维 (index 1) 之内 => 单个 logical CPU block
     是 strided 的 (跨 layer), is_contiguous()==False。V1 host 端访问这种
     block-dim-in-middle 的池, 读或写 ~0.7~1.2 GB/s, 是真正瓶颈
     (不是 DMA, D2H=31GB/s, H2D=22GB/s)。

  V2 layout: (B, 2, num_layers, num_kv_heads, block_size, head_dim)
     block 维 (index 0) 提到最外层。此时:
        cpu_pool.kv[block_id]  = (2, L, H, T, D)  一整块连续 logical KV block
        is_contiguous() == True, 约 2.25MB 连续。
     于是:
        STORE: MLU device-side pack -> 一次 D2H 直接落入最终 CPU block (无 host reformat)
        LOAD : CPU 连续 block -> 一次 H2D -> MLU device-side unpack (无 host reformat)
     彻底消除 host 端 block-dim-in-middle 的 strided pool 访问。

约束 (本阶段):
  - 简单 allocator (free list + used set), 无 LRU / ARC。
  - 不含 Scheduler / BlockManager / Attention 接入。
  - 不改 MLU 原始 KV layout。
"""
from __future__ import annotations

from bisect import insort

import torch


class CPUKVPoolV2:
    """Block-Major CPU 固定内存 KV block 池。

    Args:
        num_layers:    模型层数 (Qwen3-8B = 36)
        num_kv_heads:  KV head 数 (TP=1 时 = 8)
        head_dim:      每 head 维度 (= 128)
        block_size:    每 block token 数 (MLU 默认 = 16)
        num_blocks:    预分配 CPU block 数 (capacity)
        dtype:         KV dtype (默认 bfloat16)
    """

    def __init__(
        self,
        num_layers: int,
        num_kv_heads: int,
        head_dim: int,
        block_size: int,
        num_blocks: int = 128,
        dtype: torch.dtype = torch.bfloat16,
    ):
    self.num_layers = num_layers
        self.num_kv_heads = num_kv_heads
        self.head_dim = head_dim
        self.block_size = block_size
        self.dtype = dtype
        self.capacity = num_blocks

        # Block-Major layout: (B, 2, L, H, T, D)
        #   block_id 是最外层 -> cpu_pool.kv[block_id] 是一整块连续 logical KV block
        self.shape = (num_blocks, 2, num_layers, num_kv_heads, block_size, head_dim)

        # 一次性预分配 pinned CPU buffer (复用, 不在 store/load 循环里 malloc)
        self.kv = torch.empty(self.shape, dtype=dtype, device="cpu", pin_memory=True)
        if not self.kv.is_pinned():
            raise RuntimeError(
                "CPUKVPoolV2: pin_memory=True requested but tensor.is_pinned()==False; "
                "pinned memory 不可用, 无法保证 H2D/D2H 带宽"
            )

        # 单个 logical CPU block 必须真正连续 (~2.25MB)
        self.block_bytes = (
            2 * num_layers * num_kv_heads * block_size * head_dim * dtype.itemsize
        )

        # 简单 free list: 升序 pop(0) 分配连续 id, free 用 bisect 保持升序
        self._free: list[int] = list(range(num_blocks))
        self._used: set[int] = set()

    # ------------------------------------------------------------------
    # 连续性验证 (必须 True, 否则 V2 设计不成立)
    # ------------------------------------------------------------------
    def block_is_contiguous(self, block_id: int = 0) -> bool:
        """单个 logical block 是否真正连续。"""
        return self.kv[block_id].is_contiguous()

    def partition_is_contiguous(self, start: int, end: int) -> bool:
        """一段连续 cpu_ids 的整段 [start:end) 是否连续 (H2D src / D2H dst 整段直达)。"""
        return self.kv[start:end].is_contiguous()
         def logical_block_view(self, block_id: int) -> torch.Tensor:
        """返回 cpu_pool.kv[block_id] 的 view, shape (2,L,H,T,D), 连续。"""
        if not isinstance(block_id, int) or block_id < 0 or block_id >= self.capacity:
            raise RuntimeError(f"logical_block_view: 非法 block id {block_id}")
        return self.kv[block_id]

    def blocks_slice(self, start: int, end: int) -> torch.Tensor:
        """返回连续逻辑 block 的整段 view [start:end), shape (end-start,2,L,H,T,D), 连续。

        用于 V2 一次 H2D/D2H 整段直达 (host 端零额外 reformat)。
        """
        if start < 0 or end <= start or end > self.capacity:
            raise IndexError(f"blocks_slice: 非法范围 [{start}:{end}) (capacity={self.capacity})")
        return self.kv[start:end]

    # ------------------------------------------------------------------
    # 分配 / 释放
    # ------------------------------------------------------------------
    def allocate(self, num_blocks: int) -> list[int]:
        """分配 num_blocks 个 CPU block, 返回连续升序 block id 列表。"""
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
        """释放 block id (支持 int / 可迭代)。double free / 非法 id: 抛 RuntimeError。"""
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
        return self.kv.is_pinned()

    @property
    def mem_bytes(self) -> int:
        return self.kv.numel() * self.kv.element_size()

    def __repr__(self) -> str:
        return (
            f"CPUKVPoolV2(shape={self.shape}, dtype={self.dtype}, "
            f"capacity={self.capacity}, free={len(self._free)}, "
            f"used={len(self._used)}, block={self.block_bytes/1024**2:.3f}MB, "
            f"pinned={self.is_pinned()}, block0_contig={self.block_is_contiguous()})"
        )