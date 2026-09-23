#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PrefixCacheBackend —— Prefix Hash + CPU Block Mapping + Admission + LRU。

组合:
    CPUPrefixIndex            (block_hash -> cpu_block_id, 含 block-level LRU)
    CPUKVPoolV2               (Block-Major CPU KV pool)
    KVBlockMoverV2            (MLU<->CPU 搬运 + device pack/unpack)

第六步新增:
  - Admission Policy (§三/四): cacheable_tokens < min_tokens 时 skip Store。
  - Prompt-only Store (§五): 只 Store prompt 对应完整 prefix blocks, 不缓存 decode KV。
  - LRU Eviction (§七~§十三): pool 不够时淘汰 LRU victim, 先删 metadata 再 free block。
  - Cache Metrics (§十六): lookup/store/eviction/occupancy 统计。

复用 nanoLLM 现有 hash: `BlockManager.compute_hash(token_ids, prev_hash)` (xxh64 链式)。

Store 顺序 (§六):
  1. 收集完整可缓存 blocks (不含 partial 末块)
  2. prompt_only=True 时截断到 prompt full blocks
  3. 计算 cacheable_tokens = num_cacheable_blocks * block_size
  4. cacheable_tokens < min_tokens -> skip (reason="below_min_tokens")
  5. duplicate filter (已索引的 hash 跳过)
  6. 新增 0 block -> skip data copy (reason="duplicate_only")
  7. free 不够 -> LRU eviction (先删 metadata, 再 free block)
  8. allocate 新 CPU blocks
  9. mover.store (D2H)
  10. Store 成功后 commit index (insert, 新 key 追加 MRU 端)

失败回滚 (§十三): eviction 后 store 失败 -> 新 cpu blocks 归还, index 无半成品,
  无 double free, 无多 hash 指向同一 cpu block。已淘汰 victim 不回滚恢复 (本阶段接受)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import torch

from kv_offload_poc.prefix_index.cpu_prefix_index import CPUPrefixIndex
from kv_offload_poc.layout_v2.cpu_kv_pool_v2 import CPUKVPoolV2
from kv_offload_poc.layout_v2.kv_block_mover_v2 import KVBlockMoverV2
from kv_offload_poc.quantized_l2.cpu_kv_pool_v3_quantized import CPUKVPoolV3Quantized
from kv_offload_poc.quantized_l2.quantized_kv_block_mover import QuantizedKVBlockMover
from nanovllm.engine.block_manager import BlockManager  # 复用现有 hash

# native dims (MLU KV (2,L,N,H,T,D))
_BLK = 2

# AsyncStoreJob state (§六)
STORE_PENDING = "STORE_PENDING"
STORE_DONE = "STORE_DONE"
STORE_FAILED = "STORE_FAILED"

# AsyncLoadJob state (§十三) —— 第八步
LOAD_PENDING = "LOAD_PENDING"
LOAD_DONE = "LOAD_DONE"
LOAD_FAILED = "LOAD_FAILED"
LOAD_CANCELLED = "LOAD_CANCELLED"


def _now_ns() -> int:
    return time.perf_counter_ns()


@dataclass
class AsyncStoreJob:
    """一个异步 Store 任务 (§六)。轻量结构, 不持有大 tensor。"""
    job_id: int
    block_hashes: list  # 本 job 独占的 hash (已去重 READY/PENDING)
    cpu_block_ids: list  # 本 job 独占的 CPU block id (STORE_RESERVED)
    mlu_block_ids: list  # 源 MLU physical block id (pack 来源, 仅记录)
    num_blocks: int
    num_tokens: int
    staging_slot_id: int
    event: object = None  # torch.mlu.Event (D2H 完成信号)
    submit_time_ns: int = 0
    pack_ms: float = 0.0
    state: str = STORE_PENDING
    request_id: Optional[int] = None


@dataclass
class AsyncLoadJob:
    """一个异步 Load 任务 (§十三)。轻量结构, 不持有大 tensor。

    CPU Prefix HIT -> reserve MLU target -> 异步 H2D+unpack -> Event -> LOAD_PENDING。
    Event complete 后由调用方 (Scheduler) commit cached state + release refs/staging。
    """
    job_id: int
    request_id: Optional[int]  # 关联的 seq_id (诊断/abort 用)
    block_hashes: list  # L2 命中块的链式 hash (供 commit 注册 L1)
    cpu_block_ids: list  # 源 CPU block id (H2D 来源, refcount 保护)
    target_mlu_block_ids: list  # 目标 MLU physical block id (unpack 写入, 已 reserve)
    num_blocks: int
    num_tokens: int
    staging_slot_id: int
    event: object = None  # torch.mlu.Event (unpack 完成信号, record 在 unpack 之后)
    submit_time_ns: int = 0
    h2d_submit_ns: int = 0
    state: str = LOAD_PENDING
    l1_hit_blocks: int = 0  # L1 已命中块数 (commit 时 total_cached = l1_hit + l2_hit)
    l2_hit_blocks: int = 0
    # commit 所需元数据 (reserve 时记录, complete 时传给 BlockManager)
    l2_token_blocks: list = field(default_factory=list)
    cancelled: bool = False  # abort 时置位 (§二十三): complete 后不 commit, 直接 free


class AsyncStoreStagingPool:
    """Store Staging Pool (§四/§五)。预分配 max_pending 个 MLU contiguous staging slot。

    每个 slot (§三/§十八: KV+Scale 原子 bundle, 一个 job 同时独占二者, 不能分别分配):
      - kv_staging:    MLU contiguous staging tensor (capacity_blocks, 2, L, H, T, D)
      - scale_staging: MLU contiguous staging tensor (capacity_blocks, 2, L, H, T) [int8 模式]
                       bf16 模式为 None (不分配, 省 MLU 显存)
      - state: FREE / BUSY
      - owner_job_id (BUSY 时独占)
    要求: 初始化时预分配; Store 热路径不 malloc; 一个 pending Job 独占一个 slot (bundle);
          D2H complete 前 slot 不可复用; complete/fail 后释放 slot (同时释放 kv+scale)。
    """

    def __init__(self, mlu_kv, max_pending: int, capacity_blocks: int, device=None,
                 mlu_scale=None, quantized: bool = False):
        self.device = device if device is not None else mlu_kv.device
        self.max_pending = max_pending
        self.capacity_blocks = capacity_blocks
        self.quantized = quantized
        # 每个 slot 独立预分配 (不共享, 防止两个 in-flight Store 覆盖同一 buffer, §五)
        self.slots = []
        for _ in range(max_pending):
            kv_staging = torch.empty(
                (capacity_blocks, 2, mlu_kv.shape[1], mlu_kv.shape[3],
                 mlu_kv.shape[4], mlu_kv.shape[5]),
                dtype=mlu_kv.dtype, device=self.device,
            )
            scale_staging = None
            if quantized:
                if mlu_scale is None:
                    raise ValueError("AsyncStoreStagingPool: quantized=True 需 mlu_scale")
                scale_staging = torch.empty(
                    (capacity_blocks, 2, mlu_scale.shape[1], mlu_scale.shape[3],
                     mlu_scale.shape[4]),
                    dtype=mlu_scale.dtype, device=self.device,
                )
            self.slots.append({"state": "FREE", "owner_job_id": None,
                               "kv_staging": kv_staging,
                               "scale_staging": scale_staging})
        self._busy_count = 0

    def acquire(self, job_id: int, num_blocks: int) -> Optional[int]:
        """获取一个 FREE slot 并标记 BUSY (独占 bundle)。无空闲返回 None。"""
        if num_blocks > self.capacity_blocks:
            return None  # 超单 slot 容量, 调用方 skip (§五)
        for i, s in enumerate(self.slots):
            if s["state"] == "FREE":
                s["state"] = "BUSY"
                s["owner_job_id"] = job_id
                self._busy_count += 1
                return i
        return None  # 全 BUSY -> staging_busy (§二十一)

    def release(self, slot_id: int):
        """释放 slot bundle (complete/fail 后, 同时释放 kv+scale)。"""
        s = self.slots[slot_id]
        s["state"] = "FREE"
        s["owner_job_id"] = None
        if self._busy_count > 0:
            self._busy_count -= 1

    def num_busy(self) -> int:
        return self._busy_count

    def num_free(self) -> int:
        return self.max_pending - self._busy_count

    @property
    def mem_bytes(self) -> int:
        if not self.slots:
            return 0
            s0 = self.slots[0]
        kv_bytes = self.max_pending * s0["kv_staging"].numel() * \
            s0["kv_staging"].element_size()
        sc_bytes = 0
        if s0["scale_staging"] is not None:
            sc_bytes = self.max_pending * s0["scale_staging"].numel() * \
                s0["scale_staging"].element_size()
        return kv_bytes + sc_bytes


class AsyncLoadStagingPool:
    """Load Staging Pool (§十) —— 第八步 Async Load。与 Store staging 分离 (§十)。

    预分配 max_pending 个 MLU contiguous staging slot (bundle: kv_staging + scale_staging),
    layout (capacity_blocks,2,L,H,T,D) / (capacity_blocks,2,L,H,T)。
    H2D 写入 staging, 同 stream 上 device unpack scatter 到 MLU native KV+Scale。
    一个 pending Load Job 独占一个 slot (bundle), unpack 完成前不可复用 (§三十)。
    """

    def __init__(self, mlu_kv, max_pending: int, capacity_blocks: int, device=None,
                 mlu_scale=None, quantized: bool = False):
        self.device = device if device is not None else mlu_kv.device
        self.max_pending = max_pending
        self.capacity_blocks = capacity_blocks
        self.quantized = quantized
        self.slots = []
        for _ in range(max_pending):
            kv_staging = torch.empty(
                (capacity_blocks, 2, mlu_kv.shape[1], mlu_kv.shape[3],
                 mlu_kv.shape[4], mlu_kv.shape[5]),
                dtype=mlu_kv.dtype, device=self.device,
            )
            scale_staging = None
            if quantized:
                if mlu_scale is None:
                    raise ValueError("AsyncLoadStagingPool: quantized=True 需 mlu_scale")
                scale_staging = torch.empty(
                    (capacity_blocks, 2, mlu_scale.shape[1], mlu_scale.shape[3],
                     mlu_scale.shape[4]),
                    dtype=mlu_scale.dtype, device=self.device,
                    s0 = self.slots[0]
        kv_bytes = self.max_pending * s0["kv_staging"].numel() * \
            s0["kv_staging"].element_size()
        sc_bytes = 0
        if s0["scale_staging"] is not None:
            sc_bytes = self.max_pending * s0["scale_staging"].numel() * \
                s0["scale_staging"].element_size()
        return kv_bytes + sc_bytes


class AsyncLoadStagingPool:
    """Load Staging Pool (§十) —— 第八步 Async Load。与 Store staging 分离 (§十)。

    预分配 max_pending 个 MLU contiguous staging slot (bundle: kv_staging + scale_staging),
    layout (capacity_blocks,2,L,H,T,D) / (capacity_blocks,2,L,H,T)。
    H2D 写入 staging, 同 stream 上 device unpack scatter 到 MLU native KV+Scale。
    一个 pending Load Job 独占一个 slot (bundle), unpack 完成前不可复用 (§三十)。
    """

    def __init__(self, mlu_kv, max_pending: int, capacity_blocks: int, device=None,
                 mlu_scale=None, quantized: bool = False):
        self.device = device if device is not None else mlu_kv.device
        self.max_pending = max_pending
        self.capacity_blocks = capacity_blocks
        self.quantized = quantized
        self.slots = []
        for _ in range(max_pending):
            kv_staging = torch.empty(
                (capacity_blocks, 2, mlu_kv.shape[1], mlu_kv.shape[3],
                 mlu_kv.shape[4], mlu_kv.shape[5]),
                dtype=mlu_kv.dtype, device=self.device,
            )
            scale_staging = None
            if quantized:
                if mlu_scale is None:
                    raise ValueError("AsyncLoadStagingPool: quantized=True 需 mlu_scale")
                scale_staging = torch.empty(
                    (capacity_blocks, 2, mlu_scale.shape[1], mlu_scale.shape[3],
                     mlu_scale.shape[4]),
                    dtype=mlu_scale.dtype, device=self.device,
                    )
            self.slots.append({"state": "FREE", "owner_job_id": None,
                               "kv_staging": kv_staging,
                               "scale_staging": scale_staging})
        self._busy_count = 0

    def acquire(self, job_id: int, num_blocks: int) -> Optional[int]:
        if num_blocks > self.capacity_blocks:
            return None  # 超单 slot 容量 -> 调用方 fallback 同步 (§十一)
        for i, s in enumerate(self.slots):
            if s["state"] == "FREE":
                s["state"] = "BUSY"
                s["owner_job_id"] = job_id
                self._busy_count += 1
                return i
        return None  # 全 BUSY (§十二)

    def release(self, slot_id: int):
        s = self.slots[slot_id]
        s["state"] = "FREE"
        s["owner_job_id"] = None
        if self._busy_count > 0:
            self._busy_count -= 1

    def num_busy(self) -> int:
        return self._busy_count

    def num_free(self) -> int:
        return self.max_pending - self._busy_count

    @property
    def mem_bytes(self) -> int:
        if not self.slots:
            return 0
            s0 = self.slots[0]
        kv_bytes = self.max_pending * s0["kv_staging"].numel() * \
            s0["kv_staging"].element_size()
        sc_bytes = 0
        if s0["scale_staging"] is not None:
            sc_bytes = self.max_pending * s0["scale_staging"].numel() * \
                s0["scale_staging"].element_size()
        return kv_bytes + sc_bytes


class CacheMetrics:
    """CPU Prefix Cache 最小统计 (§十六)。所有计数在 backend 内维护。

    第七步新增 async store metrics (§二十五)。
    """

    __slots__ = (
        "cpu_cache_lookups", "cpu_cache_lookup_blocks", "cpu_cache_hit_blocks",
        "cpu_cache_misses",
        "cpu_store_requests", "cpu_store_blocks", "cpu_store_duplicate_blocks",
        "cpu_store_skipped_short", "cpu_store_skipped_empty",
        "cpu_evictions", "cpu_hit_tokens",
        # ---- async store (§二十五) ----
        "cpu_async_store_submitted", "cpu_async_store_completed",
        "cpu_async_store_failed", "cpu_async_store_pending_jobs",
        "cpu_async_store_pending_blocks", "cpu_async_store_duplicate_pending_blocks",
        "cpu_async_store_skipped_busy", "cpu_async_store_skipped_too_large",
        "cpu_async_store_skipped_insufficient", "cpu_async_store_pack_ms_total",
        "cpu_async_store_visible_submit_ms_total", "cpu_async_store_d2h_ms_total",
        "max_pending_jobs_observed",
        # ---- async load (§二十六) ---- 第八步
        "cpu_async_load_submitted", "cpu_async_load_completed",
        "cpu_async_load_failed", "cpu_async_load_cancelled",
        "cpu_async_load_pending_jobs", "cpu_async_load_pending_blocks",
        "cpu_async_load_wait_slot", "cpu_async_load_sync_fallback_busy",
        "cpu_async_load_sync_fallback_too_large",
        "cpu_async_load_protected_blocks", "cpu_async_load_peak_refcount",
        "cpu_async_load_submit_us_total", "cpu_async_load_wait_ms_total",
        "cpu_async_load_h2d_unpack_ms_total",
        "cpu_lru_protected_skips",
        # ---- 第九步: Pending Load Coalescing + Adaptive Policy (§三十八) ----
        "cpu_load_policy_sync_count", "cpu_load_policy_async_count",
        "cpu_load_coalesced_groups", "cpu_load_coalesced_requests",
        "cpu_load_duplicate_h2d_avoided", "cpu_load_waiters_current",
        "cpu_load_waiters_peak", "cpu_h2d_load_jobs", "cpu_h2d_blocks_total",
        "mlu_shared_prefix_blocks", "mlu_duplicate_prefix_blocks_avoided",
        "mlu_prefix_memory_saved_mb", "pending_prefix_groups",
        # ---- P0: Stream Dependency Hardening (§三十八) ----
        # producer_event 记录次数 (KV/Scale 生产者流上 record 的 Event, 供 transfer/pack 流 wait)
        "stream_dependency_events_recorded",
        # transfer/pack 流 wait_event(producer_event) 次数 (跨流依赖建立)
        "stream_dependency_waits",
        # 热路径上 device-wide torch.mlu.synchronize() 调用次数 (P0 目标: 热路径=0)
        "device_wide_sync_hotpath_count",
        # ---- Quantized L2 (§二十二) ----
        "cpu_quantized_mode", "cpu_kv_bytes", "cpu_scale_bytes",
        "store_kv_bytes", "store_scale_bytes",
        "load_kv_bytes", "load_scale_bytes",
        "quantized_traffic_saved_bytes", "quantized_cpu_capacity_ratio",
        "quantized_staging_memory_mb",
    )

    def __init__(self):
        self.cpu_cache_lookups = 0
        self.cpu_cache_lookup_blocks = 0
        self.cpu_cache_hit_blocks = 0
        self.cpu_cache_misses = 0
        self.cpu_store_requests = 0
        self.cpu_store_blocks = 0
        self.cpu_store_duplicate_blocks = 0
        self.cpu_store_skipped_short = 0
        self.cpu_store_skipped_empty = 0
        self.cpu_evictions = 0
        self.cpu_hit_tokens = 0
        # ---- async store ----
        self.cpu_async_store_submitted = 0
        self.cpu_async_store_completed = 0
        self.cpu_async_store_failed = 0
        self.cpu_async_store_pending_jobs = 0
        self.cpu_async_store_pending_blocks = 0
        self.cpu_async_store_duplicate_pending_blocks = 0
        self.cpu_async_store_skipped_busy = 0
        self.cpu_async_store_skipped_too_large = 0
        self.cpu_async_store_skipped_insufficient = 0
        self.cpu_async_store_pack_ms_total = 0.0
        self.cpu_async_store_visible_submit_ms_total = 0.0
        self.cpu_async_store_d2h_ms_total = 0.0
        self.max_pending_jobs_observed = 0
        # ---- async load ----
        self.cpu_async_load_submitted = 0
        self.cpu_async_load_completed = 0
        self.cpu_async_load_failed = 0
        self.cpu_async_load_cancelled = 0
        self.cpu_async_load_pending_jobs = 0
        self.cpu_async_load_pending_blocks = 0
        self.cpu_async_load_wait_slot = 0
        self.cpu_async_load_sync_fallback_busy = 0
        self.cpu_async_load_sync_fallback_too_large = 0
        self.cpu_async_load_protected_blocks = 0
        self.cpu_async_load_peak_refcount = 0
        self.cpu_async_load_submit_us_total = 0.0
        self.cpu_async_load_wait_ms_total = 0.0
        self.cpu_async_load_h2d_unpack_ms_total = 0.0
        self.cpu_lru_protected_skips = 0
        # ---- 第九步: coalescing + adaptive policy ----
        self.cpu_load_policy_sync_count = 0
        self.cpu_load_policy_async_count = 0
        self.cpu_load_coalesced_groups = 0
        self.cpu_load_coalesced_requests = 0
        self.cpu_load_duplicate_h2d_avoided = 0
        self.cpu_load_waiters_current = 0
        self.cpu_load_waiters_peak = 0
        self.cpu_h2d_load_jobs = 0
        self.cpu_h2d_blocks_total = 0
        self.mlu_shared_prefix_blocks = 0
        self.mlu_duplicate_prefix_blocks_avoided = 0
        self.mlu_prefix_memory_saved_mb = 0.0
        self.pending_prefix_groups = 0
        # ---- P0: Stream Dependency Hardening ----
        self.stream_dependency_events_recorded = 0
        self.stream_dependency_waits = 0
        self.device_wide_sync_hotpath_count = 0
        # ---- Quantized L2 (§二十二) ----
        self.cpu_quantized_mode = False
        self.cpu_kv_bytes = 0
        self.cpu_scale_bytes = 0
        self.store_kv_bytes = 0
        self.store_scale_bytes = 0
        self.load_kv_bytes = 0
        self.load_scale_bytes = 0
        self.quantized_traffic_saved_bytes = 0
        self.quantized_cpu_capacity_ratio = 1.0
        self.quantized_staging_memory_mb = 0.0

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def __repr__(self):
        return f"CacheMetrics({self.as_dict()})"


class PrefixCacheBackend:
    """Prefix Hash + CPU block mapping 数据面组合 + Admission + LRU。"""

    def __init__(self, mlu_kv, num_cpu_blocks: int, unpack_method: str = "contig_run",
                 pack_method: str = "B", max_staging_blocks: int | None = None,
                 device=None, min_tokens: int = 0, prompt_only: bool = False,
                 eviction_policy: str = "lru",
                 mlu_scale=None, cache_dtype: str = "bf16"):
        self.mlu_kv = mlu_kv
        self.mlu_scale = mlu_scale  # INT8 模式: ModelRunner.kv_scales (同一全局 tensor); bf16: None
        self.device = device if device is not None else mlu_kv.device
        self.block_size = mlu_kv.shape[4]   # 16
        self.num_layers = mlu_kv.shape[1]
        self.num_kv_heads = mlu_kv.shape[3]
        self.head_dim = mlu_kv.shape[5]
        self.unpack_method = unpack_method
        self.pack_method = pack_method

        # ---- Quantized L2 (§十四): cache_dtype 决定 CPU L2 格式 ----
        #   "bf16": 原始 BF16 V2 路径 (CPUKVPoolV2 + KVBlockMoverV2, 单 KV tensor)
        #   "int8": INT8 KV + FP32 Scale (CPUKVPoolV3Quantized + QuantizedKVBlockMover)
        #           KV 与 Scale 是一个原子逻辑块, 共用同一 cpu_block_id (§三/§十八)。
        #           Mover 持有 ModelRunner 同一全局 kv_cache + kv_scales (§八: 不在 backend
        #           内重新遍历 module 推导 scale)。
        self.cache_dtype = cache_dtype
        self.quantized = (cache_dtype == "int8")
        if self.quantized and mlu_scale is None:
            raise ValueError(
                "PrefixCacheBackend: cache_dtype='int8' 需 mlu_scale (ModelRunner.kv_scales)")

        # Admission / eviction 配置
        self.min_tokens = min_tokens
        self.prompt_only = prompt_only
        if eviction_policy != "lru":
            raise ValueError(
                f"PrefixCacheBackend: eviction_policy 仅支持 'lru', got {eviction_policy!r}")
        self.eviction_policy = eviction_policy

        self.index = CPUPrefixIndex()
        if self.quantized:
            self.cpu_pool = CPUKVPoolV3Quantized(
                self.num_layers, self.num_kv_heads, self.head_dim, self.block_size,
                num_blocks=num_cpu_blocks)
            self.mover = QuantizedKVBlockMover(
                mlu_kv, mlu_scale, self.cpu_pool,
                max_blocks=max_staging_blocks, device=self.device)
        else:
            self.cpu_pool = CPUKVPoolV2(
                self.num_layers, self.num_kv_heads, self.head_dim, self.block_size,
                num_blocks=num_cpu_blocks, dtype=mlu_kv.dtype)
            self.mover = KVBlockMoverV2(mlu_kv, self.cpu_pool,
                                        max_blocks=max_staging_blocks, device=self.device)
        self.metrics = CacheMetrics()
        self.capacity = self.cpu_pool.capacity

        # ---- Quantized metrics 初始化 (§二十二) ----
        self.metrics.cpu_quantized_mode = self.quantized
        if self.quantized:
            self.metrics.cpu_kv_bytes = self.cpu_pool.kv_mem_bytes
            self.metrics.cpu_scale_bytes = self.cpu_pool.scale_mem_bytes
            # bf16 block 字节数 (对照基准)
            bf16_blk = (2 * self.num_layers * self.num_kv_heads
                        * self.block_size * self.head_dim * 2)
            self.metrics.quantized_cpu_capacity_ratio = (
                bf16_blk / self.cpu_pool.block_bytes if self.cpu_pool.block_bytes else 1.0)
        else:
            self.metrics.cpu_kv_bytes = self.cpu_pool.mem_bytes
            self.metrics.cpu_scale_bytes = 0
            self.metrics.quantized_cpu_capacity_ratio = 1.0

        # ---- 第七步 Async Store 状态 ----
        # pending_store_hashes: dict[block_hash, job_id] —— STORE_PENDING hash 的 ownership (§七)
        # pending_jobs: dict[job_id, AsyncStoreJob]
        # staging_pool: AsyncStoreStagingPool (预分配 MLU staging slot)
        # READY index 仍由 self.index (CPUPrefixIndex) 管理; pending hash 不进 ready LRU (§七)。
        self.pending_store_hashes: dict = {}
        self.pending_jobs: dict = {}
        self._next_job_id = 0
        self.staging_pool: Optional[AsyncStoreStagingPool] = None
        self.async_store_enabled = False
        self.async_store_max_blocks = 0  # 单 slot 容量 (§五)
        self.async_store_max_pending = 0

        # ---- 第八步 Async Load 状态 ----
        # pending_load_jobs: dict[job_id, AsyncLoadJob] —— LOAD_PENDING job (§三/§十三)
        # load_staging_pool: AsyncLoadStagingPool (与 Store staging 分离, §十)
        # CPU block refcount 由 self.index.acquire_refs/release_refs 管理 (§六/§八)。
        # LOAD_PENDING seq 的 MLU target reservation 由 BlockManager.reserve_cpu_prefix_load
        # 完成 (block_table 已写, num_cached_tokens=0); commit 在 Event complete 后。
        self.pending_load_jobs: dict = {}
        self.load_staging_pool: Optional[AsyncLoadStagingPool] = None
        self.async_load_enabled = False
        self.async_load_max_blocks = 0  # 单 load slot 容量 (§十一)
        self.async_load_max_pending = 0
        # 第九步: Adaptive sync/async policy (§十四)。由 Scheduler 注入。
        #   "always_sync" / "always_async" / "adaptive"。仅诊断/记录用, 真正决策在 Scheduler。
        self.load_policy = "adaptive"

    def enable_async_store(self, max_pending: int = 2, max_blocks: int = 256):
        """启用 Async Store (§四/§五)。预分配 staging pool, 不在热路径 malloc。

        Args:
            max_pending: 最大并发 pending Store job 数 (slot 数, §二十一)。默认 2。
            max_blocks: 单 slot 容量 (blocks), 默认 256 (4096 tokens, §五)。
        """
        self.staging_pool = AsyncStoreStagingPool(
            self.mlu_kv, max_pending=max_pending, capacity_blocks=max_blocks,
            device=self.device, mlu_scale=self.mlu_scale, quantized=self.quantized)
        self.async_store_enabled = True
        self.async_store_max_blocks = max_blocks
        self.async_store_max_pending = max_pending
        if self.staging_pool is not None:
            self.metrics.quantized_staging_memory_mb = round(
                self.staging_pool.mem_bytes / 1024**2, 2)
        return self

    def disable_async_store(self):
        """禁用 Async Store (先 flush 全部 pending)。"""
        if self.async_store_enabled:
            self.flush_pending_stores()
        self.async_store_enabled = False
        self.staging_pool = None

def enable_async_load(self, max_pending: int = 2, max_blocks: int = 320):
        """启用 Async Load (§十/§十一)。预分配独立 load staging pool。

        Args:
            max_pending: 最大并发 pending Load job 数 (load slot 数, §三十九)。默认 2。
            max_blocks: 单 load slot 容量 (blocks), 默认 320 (5120 tokens, §十一)。
                        超此 fallback 同步 Load (§十一), 不实现 chunked async load。
        """
        self.load_staging_pool = AsyncLoadStagingPool(
            self.mlu_kv, max_pending=max_pending, capacity_blocks=max_blocks,
            device=self.device, mlu_scale=self.mlu_scale, quantized=self.quantized)
        self.async_load_enabled = True
        self.async_load_max_blocks = max_blocks
        self.async_load_max_pending = max_pending
        if self.load_staging_pool is not None:
            self.metrics.quantized_staging_memory_mb = round(
                (self.staging_pool.mem_bytes if self.staging_pool else 0)
                + self.load_staging_pool.mem_bytes, 2)
        return self

    def disable_async_load(self):
        """禁用 Async Load (先 flush 全部 pending)。"""
        if self.async_load_enabled:
            self.flush_pending_loads()
        self.async_load_enabled = False
        self.load_staging_pool = None

    def num_pending_load_jobs(self) -> int:
        return len(self.pending_load_jobs)

    def num_pending_load_blocks(self) -> int:
        return sum(j.num_blocks for j in self.pending_load_jobs.values())

 def record_policy_decision(self, is_async: bool) -> None:
        """Scheduler 决定 sync/async load 时调用 (§十四/§三十八)。"""
        if is_async:
            self.metrics.cpu_load_policy_async_count += 1
        else:
            self.metrics.cpu_load_policy_sync_count += 1

    def record_coalesce_group_created(self, num_blocks: int) -> None:
        """owner 创建一个 PendingLoadGroup (真实 H2D) 时调用。"""
        self.metrics.cpu_load_coalesced_groups += 1
        self.metrics.cpu_h2d_load_jobs += 1
        self.metrics.cpu_h2d_blocks_total += num_blocks
        # pending_prefix_groups 由 Scheduler 在 _join_waiter/_resolve 时维护精确值
        # (len(pending_prefix_loads)), 这里不覆盖。

    def record_coalesce_waiter_joined(self) -> None:
        """一个 waiter 加入已有 group 时调用 (避免一次重复 H2D, §三十八)。"""
        self.metrics.cpu_load_coalesced_requests += 1
        self.metrics.cpu_load_duplicate_h2d_avoided += 1
        cur = self.metrics.cpu_load_coalesced_requests
        if cur > self.metrics.cpu_load_waiters_peak:
            self.metrics.cpu_load_waiters_peak = cur

    def record_coalesce_group_resolved(self, num_waiters: int) -> None:
        """group 完成 (commit 或 fail) 时调用, 释放 waiter 计数。"""
        self.metrics.cpu_load_waiters_current = max(
            0, self.metrics.cpu_load_waiters_current - num_waiters)

    def record_shared_prefix_promote(self, shared_blocks: int,
                                     duplicate_avoided: int) -> None:
        """L1 promotion 完成后记录共享 MLU prefix blocks + 节省的重复块 (§十三/§三十八)。
        shared_blocks = 实际只保留一份的 prefix MLU blocks;
        duplicate_avoided = 因共享而未重复分配的 prefix MLU blocks。
        """
        self.metrics.mlu_shared_prefix_blocks += shared_blocks
        self.metrics.mlu_duplicate_prefix_blocks_avoided += duplicate_avoided
        # 单 block ≈ 2.25MB (2*36*8*16*128*2 bytes)
        self.metrics.mlu_prefix_memory_saved_mb += duplicate_avoided * 2.25
        def acquire_load_refs(self, cpu_block_ids) -> None:
        """submit async load 前 acquire CPU refs (§六/§十五)。ref_count += 1。"""
        self.index.acquire_refs(cpu_block_ids)
        self.metrics.cpu_async_load_protected_blocks = self.index.num_protected()
        if self.index.peak_refcount() > self.metrics.cpu_async_load_peak_refcount:
            self.metrics.cpu_async_load_peak_refcount = self.index.peak_refcount()

    def release_load_refs(self, cpu_block_ids) -> None:
        """load complete/fail 后 release CPU refs (§六/§十五)。ref_count -= 1。"""
        self.index.release_refs(cpu_block_ids)
        self.metrics.cpu_async_load_protected_blocks = self.index.num_protected()

    def submit_load(self, block_hashes, cpu_block_ids, target_mlu_block_ids,
                    l1_hit_blocks: int = 0, l2_token_blocks=None,
                    request_id: Optional[int] = None,
                    unpack_method: str | None = None):
        """异步 Load 提交 (§四/§十四/§十六)。

        前置 (调用方已完成):
          - L2 CPU lookup HIT (cpu_block_ids 已取得)
          - reserve MLU target blocks (target_mlu_block_ids, BlockManager.allocate_prefix
            with set_cached_tokens=False: block_table 已写, num_cached_tokens=0)
          - CPU refs 已 acquire (调用方在 reserve 前 acquire, §十五: refs 从 submit 前
            保持到 Event complete; 本方法不重复 acquire, 只在 fail 时 release)

        本方法只做:
          1. 检查 load slot 容量 (§十一: 超容量 fallback 同步)
          2. acquire load staging slot (§十/§十二)
          3. 异步 H2D + device unpack (transfer_stream, §十四)
          4. record Event AFTER unpack (§十四)
          5. 创建 AsyncLoadJob (LOAD_PENDING)

返回:
            (ok, result)
            ok=True: result = {job_id, num_blocks, reason="submitted", submit_us}
            ok=False: result = {reason, num_blocks}
              reason ∈ {too_large, staging_busy, load_io_failure}
              too_large / staging_busy: 调用方 fallback 同步 Load (§十一/§十二)。
              load_io_failure: 调用方 rollback (release refs + free target blocks)。
        """
        if not self.async_load_enabled:
            raise RuntimeError("submit_load: async load 未启用, 先 enable_async_load()")
        if unpack_method is None:
            unpack_method = self.unpack_method
        n = len(cpu_block_ids)
        self.metrics.cpu_async_load_pending_jobs = len(self.pending_load_jobs)
        t_submit_start = _now_ns()

        if n == 0:
            return (False, {"reason": "empty", "num_blocks": 0})

        if n != len(target_mlu_block_ids):
            raise ValueError(
                f"submit_load: len(cpu)={n} != len(target_mlu)={len(target_mlu_block_ids)}")

        # 1. too_large: 超 load slot 容量 -> fallback 同步 (§十一)
        if n > self.async_load_max_blocks:
            self.metrics.cpu_async_load_sync_fallback_too_large += 1
            return (False, {"reason": "too_large", "num_blocks": n})

        # 2. acquire load staging slot (§十/§十二)
        job_id = self._next_job_id
        self._next_job_id += 1
        slot_id = self.load_staging_pool.acquire(job_id, n)
        if slot_id is None:
            # 全 BUSY -> fallback 同步 (§十二: 本阶段 sync fallback, 记录 busy)
            self.metrics.cpu_async_load_sync_fallback_busy += 1
            return (False, {"reason": "staging_busy", "num_blocks": n})
        slot_obj = self.load_staging_pool.slots[slot_id]
        staging_kv = slot_obj["kv_staging"][:n]
        staging_scale = slot_obj["scale_staging"][:n] if self.quantized else None
        try:
            if self.quantized:
                event = self.mover.submit_load_async(
                    staging_kv, staging_scale, list(cpu_block_ids),
                    list(target_mlu_block_ids), unpack_method=unpack_method)
            else:
                event = self.mover.submit_load_async(
                    staging_kv, list(cpu_block_ids), list(target_mlu_block_ids),
                    unpack_method=unpack_method)
        except Exception as e:
            self.load_staging_pool.release(slot_id)
            self.metrics.cpu_async_load_failed += 1
            return (False, {"reason": "load_io_failure", "num_blocks": n,
                            "error": repr(e)})

        # 4. 创建 AsyncLoadJob (LOAD_PENDING)
        job = AsyncLoadJob(
            job_id=job_id, request_id=request_id,
            block_hashes=list(block_hashes), cpu_block_ids=list(cpu_block_ids),
            target_mlu_block_ids=list(target_mlu_block_ids),
            num_blocks=n, num_tokens=n * self.block_size,
            staging_slot_id=slot_id, event=event,
            submit_time_ns=t_submit_start, h2d_submit_ns=_now_ns(),
            state=LOAD_PENDING, l1_hit_blocks=l1_hit_blocks, l2_hit_blocks=n,
            l2_token_blocks=list(l2_token_blocks) if l2_token_blocks else [],
        )
        self.pending_load_jobs[job_id] = job
        self.metrics.cpu_async_load_submitted += 1
        self.metrics.cpu_async_load_pending_jobs = len(self.pending_load_jobs)
        self.metrics.cpu_async_load_pending_blocks += n
        # Quantized traffic metrics (§二十二): KV + Scale H2D 字节
        if self.quantized:
            kv_bytes = n * self.cpu_pool.kv_block_bytes
            sc_bytes = n * self.cpu_pool.scale_block_bytes
            self.metrics.load_kv_bytes += kv_bytes
            self.metrics.load_scale_bytes += sc_bytes
        submit_us = (_now_ns() - t_submit_start) / 1e3
        self.metrics.cpu_async_load_submit_us_total += submit_us
        return (True, {"job_id": job_id, "num_blocks": n, "reason": "submitted",
                       "submit_us": submit_us, "slot_id": slot_id})

    def poll_load_completions(self) -> int:
        """Event polling (§十八)。非阻塞 event.query(), 完成的 Job 通知调用方 commit。

        由 Scheduler/Engine 每个 step 在 schedule 前调用 (§十八: 完成的 load 可在本 step
        立即恢复调度, 减少额外一轮 latency)。event.query() 必须 non-blocking (§十八)。

        本方法只检测 Event 完成 + 释放 staging slot + release CPU refs + 从 pending 删除;
        **不** commit cached state —— commit (BlockManager.complete_cpu_prefix_load +
        hash_to_block_id 注册) 由 Scheduler 在确认 seq 状态后调用, 因为 commit 需要
        操作 BlockManager/seq (backend 不持有这些)。

        返回: 本次完成的 job_id 列表 (Scheduler 逐个 commit)。
        """
        if not self.pending_load_jobs:
            return 0
        completed = 0
        for job_id in list(self.pending_load_jobs.keys()):
            job = self.pending_load_jobs.get(job_id)
            if job is None:
                continue
            try:
                done = job.event.query()
            except Exception:
                # Event query 异常 -> LOAD_FAILED (§二十二)
                self._fail_load_job(job)
                continue
            if done:
                self._complete_load_job(job)
                completed += 1
        return completed

    def _complete_load_job(self, job: AsyncLoadJob):
        """Load 完成: 释放 staging + CPU refs, 从 pending 删除 (§十九)。

        commit cached state (BlockManager.complete_cpu_prefix_load) 由 Scheduler 调用,
        因 backend 不持有 BlockManager/seq。本方法只做 IO 资源释放 + 状态标记。
        若 job.cancelled (§二十三): 不 commit, 已由 cancel 路径处理 target blocks。
        """
        # 释放 staging slot
        self.load_staging_pool.release(job.staging_slot_id)
        # 释放 CPU refs (§十五: H2D+unpack 全结束后才 release)
        self.release_load_refs(job.cpu_block_ids)
        job.state = LOAD_DONE
        del self.pending_load_jobs[job.job_id]
        self.metrics.cpu_async_load_pending_jobs = len(self.pending_load_jobs)
        self.metrics.cpu_async_load_pending_blocks -= job.num_blocks
        if not job.cancelled:
            self.metrics.cpu_async_load_completed += 1

    def _fail_load_job(self, job: AsyncLoadJob):
        """Load 失败 rollback (§二十一/§二十二)。释放 staging + CPU refs, 不 commit。
        target MLU blocks 的释放由 Scheduler rollback (backend 不持有 BlockManager)。"""
        self.load_staging_pool.release(job.staging_slot_id)
        self.release_load_refs(job.cpu_block_ids)
        job.state = LOAD_FAILED
        del self.pending_load_jobs[job.job_id]
        self.metrics.cpu_async_load_failed += 1
        self.metrics.cpu_async_load_pending_jobs = len(self.pending_load_jobs)
        self.metrics.cpu_async_load_pending_blocks -= job.num_blocks

    def cancel_load_job(self, job: AsyncLoadJob):
        """Request abort/cancel (§二十三): 标记 cancelled, 不立即 free target MLU blocks
        (load stream 可能还在写)。Event 完成后 _complete_load_job 释放 refs/staging,
        Scheduler 检查 cancelled 后 free target blocks, 不 commit, 不重新入队。"""
        job.cancelled = True
        job.state = LOAD_CANCELLED
        def flush_pending_loads(self, timeout_s: float = 30.0) -> int:
        """同步等待全部 pending Load 完成 (§二十四)。用于 shutdown / test teardown /
        CPU cache clear / L1 reset 前。可同步等待 Event; 正常热路径不调用 flush。
        返回完成数 (含失败数)。完成后 staging/refs 归零, 但 commit 仍由 Scheduler 做
        (flush 时不 commit cached state, 调用方负责后续处理)。"""
        if not self.pending_load_jobs:
            return 0
        done = 0
        deadline = _now_ns() + int(timeout_s * 1e9)
        while self.pending_load_jobs:
            for job_id in list(self.pending_load_jobs.keys()):
                job = self.pending_load_jobs.get(job_id)
                if job is None:
                    continue
                try:
                    job.event.synchronize()  # flush 可同步等待 (§二十四)
                    self._complete_load_job(job)
                    done += 1
                except Exception:
                    self._fail_load_job(job)
                    done += 1
            if _now_ns() > deadline and self.pending_load_jobs:
                for job_id in list(self.pending_load_jobs.keys()):
                    self._fail_load_job(self.pending_load_jobs[job_id])
                    done += 1
                break
        return done

    def flush_pending_io(self, timeout_s: float = 30.0) -> int:
        """同时 flush Store + Load pending IO (§二十四)。安全收尾。"""
        return self.flush_pending_stores(timeout_s) + self.flush_pending_loads(timeout_s)

    # ------------------------------------------------------------------
    @staticmethod
    def compute_hash(token_ids: list[int], prefix_hash: int = -1) -> int:
        return BlockManager.compute_hash(token_ids, prefix_hash)

    @staticmethod
    def hash_request(token_blocks) -> list[int]:
        """把 request 的分块 token (list[list[int]]) 转成链式 block hashes 列表。"""
        hashes = []
        h = -1
        for blk in token_blocks:
            h = BlockManager.compute_hash(list(blk), h)
            hashes.append(h)
        return hashes

    # ------------------------------------------------------------------
    # Store (admission + dedup + LRU eviction + commit-after-copy + rollback)
    # ------------------------------------------------------------------
    def store_blocks(self, block_hashes, mlu_block_ids, pack_method=None,
                     prompt_block_limit: int | None = None, producer_event=None):
                      self.metrics.cpu_store_requests += 1
        if pack_method is None:
            pack_method = self.pack_method
        if producer_event is not None:
            self.metrics.stream_dependency_waits += 1
        if not block_hashes:
            self.metrics.cpu_store_skipped_empty += 1
            return (True, {"stored": 0, "cpu_block_ids_new": [], "reason": "empty",
                           "evicted": 0, "cacheable_tokens": 0})

        if len(block_hashes) != len(mlu_block_ids):
            raise ValueError(
                f"store_blocks: len(hashes)={len(block_hashes)} != len(mlu)={len(mlu_block_ids)}")

        # 2. prompt_only 截断 (§五)
        if self.prompt_only and prompt_block_limit is not None:
            limit = max(0, prompt_block_limit)
            if limit < len(block_hashes):
                block_hashes = block_hashes[:limit]
                mlu_block_ids = mlu_block_ids[:limit]

        # 3. cacheable_tokens = num_cacheable_blocks * block_size (§四, 不含 partial)
        cacheable_tokens = len(block_hashes) * self.block_size

        # 4. Admission (§三): cacheable_tokens < min_tokens -> skip
        if self.min_tokens > 0 and cacheable_tokens < self.min_tokens:
            self.metrics.cpu_store_skipped_short += 1
            return (True, {"stored": 0, "cpu_block_ids_new": [],
                           "reason": "below_min_tokens", "evicted": 0,
                           "cacheable_tokens": cacheable_tokens})

# 5. duplicate filter (§八): 已索引(READY) 或 STORE_PENDING 的 hash 跳过 (不重复占 CPU block)
        #    §八升级: 同一 hash 在第一个 Store pending 时, 第二个 Request 不再异步存一份。
        new_idx = [i for i, h in enumerate(block_hashes)
                   if h not in self.index and h not in self.pending_store_hashes]
        if not new_idx:
            # 6. duplicate-only: skip data copy (§六)。区分 READY / PENDING duplicate (§八)
            self.metrics.cpu_store_duplicate_blocks += len(block_hashes)
            dup_pending = sum(1 for h in block_hashes if h in self.pending_store_hashes)
            self.metrics.cpu_async_store_duplicate_pending_blocks += dup_pending
            return (True, {"stored": 0, "cpu_block_ids_new": [], "reason": "all_cached",
                           "evicted": 0, "cacheable_tokens": cacheable_tokens})

        num_new = len(new_idx)

        # 7. free 不够 -> LRU eviction (§十一/十二)
        evicted = 0
        free = self.cpu_pool.num_free_blocks()
        if free < num_new:
            need_evict = num_new - free
            evicted = self._evict_lru(need_evict)
            # eviction 后若仍不够 (理论上 pop_lru 一次释放一块, 足够则停; 不够说明池空且 index 空)
            if self.cpu_pool.num_free_blocks() < num_new:
                # 极端: 池容量 < num_new, 淘汰全部也放不下 -> 整批 fail (不回滚已淘汰, §十三接受)
                return (False, {"stored": 0, "cpu_block_ids_new": [],
                                "reason": "insufficient_cpu_blocks", "evicted": evicted,
                                "cacheable_tokens": cacheable_tokens})

        # 8. allocate 新 CPU blocks (整批, 原子)。allocate 返回连续升序 id (free list 升序),
        #    满足 mover.store 要求 CPU ids 连续 (一次 D2H 直达连续段)。
        try:
            new_cpu = self.cpu_pool.allocate(num_new)
        except RuntimeError:
            return (False, {"stored": 0, "cpu_block_ids_new": [],
                            "reason": "insufficient_cpu_blocks", "evicted": evicted,
                            "cacheable_tokens": cacheable_tokens})

        if len(new_cpu) != num_new:
            self.cpu_pool.free(new_cpu)
            return (False, {"stored": 0, "cpu_block_ids_new": [],
                            "reason": "insufficient_cpu_blocks", "evicted": evicted,
                            "cacheable_tokens": cacheable_tokens})

        new_mlu = [mlu_block_ids[i] for i in new_idx]
        new_hash = [block_hashes[i] for i in new_idx]

        # 9. Store (device D2H)。new_cpu 升序但 eviction 后可能非连续 (free list 有洞),
        #    按连续 cpu-run 分段 store (每段一次 contiguous D2H), host 端零 reformat。
        #    失败 -> 归还新 cpu blocks, index 无半成品 (§十三)。
        try:
            runs = CPUPrefixIndex.split_contiguous_runs(new_cpu)
            run_start = 0
            for run_cpu_id, run_len in runs:
                seg_i = slice(run_start, run_start + run_len)
                seg_cpu = list(range(run_cpu_id, run_cpu_id + run_len))
                seg_mlu = new_mlu[seg_i]
                self.mover.store(seg_mlu, seg_cpu, pack_method=pack_method,
                                 producer_event=producer_event)
                run_start += run_len
        except Exception:
            self.cpu_pool.free(new_cpu)
            return (False, {"stored": 0, "cpu_block_ids_new": [],
                            "reason": "store_io_failure", "evicted": evicted,
                            "cacheable_tokens": cacheable_tokens})

        # 10. Store 成功后 commit hash (insert, 新 key 追加 MRU 端; duplicate 不 touch §九)
        committed_new = []
        for h, c in zip(new_hash, new_cpu):
            applied, existing = self.index.insert(h, c)
            if not applied:
                # 同批内 hash 必不重复 (new_idx 来自未命中去重), 但保守: 释放重复占的
                self.cpu_pool.free([c])
                committed_new.append((h, existing))
            else:
                committed_new.append((h, c))

 self.metrics.cpu_store_blocks += num_new
        # duplicate 计数 (§八): len(block_hashes)-num_new = READY dup + PENDING dup
        self.metrics.cpu_store_duplicate_blocks += (len(block_hashes) - num_new)
        # Quantized traffic metrics (§二十二): sync store 也累计 KV+Scale D2H 字节
        if self.quantized:
            kv_bytes = num_new * self.cpu_pool.kv_block_bytes
            sc_bytes = num_new * self.cpu_pool.scale_block_bytes
            self.metrics.store_kv_bytes += kv_bytes
            self.metrics.store_scale_bytes += sc_bytes
            bf16_blk = (2 * self.num_layers * self.num_kv_heads
                        * self.block_size * self.head_dim * 2)
            self.metrics.quantized_traffic_saved_bytes += max(
                0, num_new * bf16_blk - (kv_bytes + sc_bytes))
        return (True, {"stored": num_new, "cpu_block_ids_new": new_cpu, "reason": "ok",
                       "evicted": evicted, "cacheable_tokens": cacheable_tokens})

    def _evict_lru(self, need: int) -> int:
        """淘汰 need 个 LRU victim (§十一/十二)。

        严格顺序: 先删 index metadata (pop_lru), 再 cpu_pool.free(block)。
        第八步: 若 async load 启用, 用 pop_lru_evictable 跳过 ref_count>0 的 protected
        entry (§八); 否则用原 pop_lru (无 refcount)。
        返回实际淘汰数。
        """
        evicted = 0
        use_evictable = self.async_load_enabled
        for _ in range(need):
            if use_evictable:
                pair = self.index.pop_lru_evictable()
            else:
                pair = self.index.pop_lru()
            if pair is None:
                break  # 无可淘汰 (index 空, 或全 protected)
            victim_hash, victim_cpu = pair
            # §十二: metadata 已删, 再 free block (block 才能被 allocator 复用)
            self.cpu_pool.free([victim_cpu])
            evicted += 1
            self.metrics.cpu_evictions += 1
        return evicted
        def lookup_prefix(self, block_hashes):
        """返回 (matched_hashes, matched_mlu_blocks, matched_block_count)。

        遇第一个 MISS 即停 (见 CPUPrefixIndex.match_prefix)。命中块 touch LRU (§八)。

        STORE_PENDING hash 不在 ready index, 故 lookup 时为 MISS (§七/§十八)。
        本方法只查 ready index, 不查 pending —— pending 不可见, 不等待 (§十八)。
        """
        self.metrics.cpu_cache_lookups += 1
        self.metrics.cpu_cache_lookup_blocks += len(block_hashes)
        hashes, cpus, n = self.index.match_prefix(block_hashes)
        if n > 0:
            self.metrics.cpu_cache_hit_blocks += n
            self.metrics.cpu_hit_tokens += n * self.block_size
        else:
            self.metrics.cpu_cache_misses += 1
        return hashes, cpus, n

    # ------------------------------------------------------------------
    # Load prefix (个连续段直 H2D, 全程 device)
    # ------------------------------------------------------------------
    def load_prefix(self, block_hashes, target_mlu_block_ids):
        """载回命中的 prefix, 写入 target_mlu_block_ids[:n] (bit-exact)。

        matched cpu 未必连续 (可能由多次 store 累积), 这里按 连续 cpu run 逐段
        mover 的 load (每段 contiguous H2D + device unpack), host 端无 strided 访问。
        """
        hashes, cpus, n = self.index.match_prefix(block_hashes)
        if n == 0:
            return 0
        if n > len(target_mlu_block_ids):
            raise ValueError("load_prefix: matched 多于提供的 target MLU blocks")
        tgt = target_mlu_block_ids[:n]
        # 按连续 cpu-run 拆分载回
        runs = CPUPrefixIndex.split_contiguous_runs(cpus)
        run_cpu_start = 0
        for run_cpu_id, run_len in runs:
            seg_i = slice(run_cpu_start, run_cpu_start + run_len)
            seg_cpu = list(range(run_cpu_id, run_cpu_id + run_len))
            seg_tgt = tgt[seg_i]
            self.mover.load(seg_cpu, seg_tgt, unpack_method=self.unpack_method)
            run_cpu_start += run_len
            if self.quantized:
            self.metrics.load_kv_bytes += n * self.cpu_pool.kv_block_bytes
            self.metrics.load_scale_bytes += n * self.cpu_pool.scale_block_bytes
        return n

    # ------------------------------------------------------------------
    # Remove / Clear
    # ------------------------------------------------------------------
    def remove(self, block_hash):
        """从索引删除 hash 并把其 cpu block 归还池。返回 (removed: bool).

        不能 remove 一个 STORE_PENDING hash (其 CPU block 由 pending Job 独占, §九)。
        """
        if block_hash in self.pending_store_hashes:
            return False  # pending 不可被外部 remove
        cpu = self.index.remove(block_hash)
        if cpu is None:
            return False
        self.cpu_pool.free([cpu])
        return True

    def clear(self):
        """清空索引 + 归还全部 CPU blocks。

        若存在 pending Store/Load, 必须先 flush (§二十四: 不能 D2H/H2D 还在读写
        CPU block 时就 reset/free pool)。本方法不自动 flush, 由调用方保证。
        """
        cpus = self.index.clear()
        if cpus:
            self.cpu_pool.free(cpus)
        return len(cpus)

def submit_store(self, block_hashes, mlu_block_ids, request_id=None,
                     pack_method=None, prompt_block_limit=None, producer_event=None):
        """异步 Store 提交 (§十一)。

        流程 (§十一):
          1. Admission + prompt-only 截断
          2. 去重 READY + PENDING (§八)
          3. 检查 staging slot (§五/§二十一)
          4. 无 slot -> skip (staging_busy / too_large / insufficient_evictable)
          5. 必要时 LRU eviction (只淘汰 READY, §十九)
          6. allocate CPU blocks (STORE_RESERVED, §九)
          7. acquire staging slot
          8. MLU 上 pack source KV 到独占 slot
          9. 等 pack 完成 (pack_stream.synchronize) -> source MLU blocks 可安全释放 (§十二)
          10. 注册 pending hash ownership
          11. transfer_stream 发起 staging -> CPU 最终池 non_blocking D2H (§十三)
          12. record Event
          13. 创建 AsyncStoreJob (STORE_PENDING)

        P0 Stream Dependency Hardening (§五): 若提供 producer_event (KV/Scale 生产者流
        —— 通常是 default/compute stream —— 上 record 的 Event), pack_to_staging 的 pack
        (在 pack_stream) 会 wait_event(producer_event), 保证 pack 读 source MLU blocks 在
        生产者写完成之后 (跨流依赖, 不阻塞 host, 不需要 device-wide torch.mlu.synchronize())。
        producer_event 必须记录在最后一次会修改即将 offload 的 KV/Scale 写之后 (§五)。
        None = 调用方已保证 source ready (原行为, 兼容旧测试)。

        返回时:
          - CPU KV 尚未 READY (STORE_PENDING)
          - 原 Request source MLU blocks 已可安全 deallocate (pack 已完成)

        返回:
            (ok, result)
            ok=True: result = {job_id, cpu_block_ids, num_blocks, reason="submitted", pack_ms, visible_submit_ms}
            ok=False (skip): result = {reason, num_blocks}
              reason ∈ {empty, below_min_tokens, all_cached, too_large, staging_busy,
                        insufficient_evictable_blocks, store_io_failure}
        """
        if not self.async_store_enabled:
            raise RuntimeError("submit_store: async store 未启用, 先 enable_async_store()")
        self.metrics.cpu_store_requests += 1
        t_submit_start = _now_ns()

        if pack_method is None:
            pack_method = self.pack_method

        if producer_event is not None:
            self.metrics.stream_dependency_waits += 1

        if not block_hashes:
            self.metrics.cpu_store_skipped_empty += 1
            return (False, {"reason": "empty", "num_blocks": 0})

        if len(block_hashes) != len(mlu_block_ids):
            raise ValueError(
                f"submit_store: len(hashes)={len(block_hashes)} != len(mlu)={len(mlu_block_ids)}")

        # 1. prompt_only 截断 (§五)
        if self.prompt_only and prompt_block_limit is not None:
            limit = max(0, prompt_block_limit)
            if limit < len(block_hashes):
                block_hashes = block_hashes[:limit]
                mlu_block_ids = mlu_block_ids[:limit]

        cacheable_tokens = len(block_hashes) * self.block_size

        # 2. Admission (§三/§二十): cacheable_tokens < min_tokens -> skip
        if self.min_tokens > 0 and cacheable_tokens < self.min_tokens:
            self.metrics.cpu_store_skipped_short += 1
            return (False, {"reason": "below_min_tokens", "num_blocks": len(block_hashes),
                            "cacheable_tokens": cacheable_tokens})

        # 3. duplicate filter READY + PENDING (§八)
        new_idx = [i for i, h in enumerate(block_hashes)
                   if h not in self.index and h not in self.pending_store_hashes]
        if not new_idx:
            self.metrics.cpu_store_duplicate_blocks += len(block_hashes)
            dup_pending = sum(1 for h in block_hashes if h in self.pending_store_hashes)
            self.metrics.cpu_async_store_duplicate_pending_blocks += dup_pending
            return (False, {"reason": "all_cached", "num_blocks": 0,
                            "cacheable_tokens": cacheable_tokens})

        num_new = len(new_idx)
         # 4. too_large: 超单 slot 容量 -> skip (§五, 不实现 chunked)
        if num_new > self.async_store_max_blocks:
            self.metrics.cpu_async_store_skipped_too_large += 1
            return (False, {"reason": "too_large", "num_blocks": num_new,
                            "cacheable_tokens": cacheable_tokens})

        # 5. staging slot 预检查 (§二十一): 全 BUSY -> skip (不等 slot, 不 fallback 同步)
        if self.staging_pool.num_free() == 0:
            self.metrics.cpu_async_store_skipped_busy += 1
            return (False, {"reason": "staging_busy", "num_blocks": num_new,
                            "cacheable_tokens": cacheable_tokens})

        # 6. free + evictable_ready 是否足够 (§十九/§三十): 不能淘汰 pending reserved block
        free = self.cpu_pool.num_free_blocks()
        evictable_ready = len(self.index)  # READY 全部可淘汰
        if free + evictable_ready < num_new:
            self.metrics.cpu_async_store_skipped_insufficient += 1
            return (False, {"reason": "insufficient_evictable_blocks",
                            "num_blocks": num_new, "cacheable_tokens": cacheable_tokens})

        # 7. 必要时 LRU eviction (只淘汰 READY, §十九)
        evicted = 0
        if free < num_new:
            need_evict = num_new - free
            evicted = self._evict_lru(need_evict)
            if self.cpu_pool.num_free_blocks() < num_new:
                # 极端: 淘汰全部 READY 仍不够 (池容量 < num_new)
                self.metrics.cpu_async_store_skipped_insufficient += 1
                return (False, {"reason": "insufficient_evictable_blocks",
                                "num_blocks": num_new, "cacheable_tokens": cacheable_tokens})

        # 8. allocate CPU blocks (STORE_RESERVED, §九): 不在 free-list, 不在 ready LRU,
        #    不可 lookup, 不可 eviction, 由 pending Job 独占。
        try:
            new_cpu = self.cpu_pool.allocate(num_new)
        except RuntimeError:
             self.metrics.cpu_async_store_skipped_insufficient += 1
            return (False, {"reason": "insufficient_evictable_blocks",
                            "num_blocks": num_new, "cacheable_tokens": cacheable_tokens})
        if len(new_cpu) != num_new:
            self.cpu_pool.free(new_cpu)
            self.metrics.cpu_async_store_skipped_insufficient += 1
            return (False, {"reason": "insufficient_evictable_blocks",
                            "num_blocks": num_new, "cacheable_tokens": cacheable_tokens})

        new_mlu = [mlu_block_ids[i] for i in new_idx]
        new_hash = [block_hashes[i] for i in new_idx]

        # 9. acquire staging slot (独占, §五)。allocate CPU 成功后再 acquire, 失败则回滚 CPU。
        job_id = self._next_job_id
        self._next_job_id += 1
        slot_id = self.staging_pool.acquire(job_id, num_new)
        if slot_id is None:
            # 理论不会到这 (前面 num_free 检查), 保守回滚
            self.cpu_pool.free(new_cpu)
            self.metrics.cpu_async_store_skipped_busy += 1
            return (False, {"reason": "staging_busy", "num_blocks": num_new,
                            "cacheable_tokens": cacheable_tokens})
        slot_obj = self.staging_pool.slots[slot_id]
        staging_kv = slot_obj["kv_staging"][:num_new]
        staging_scale = slot_obj["scale_staging"][:num_new] if self.quantized else None

        # 10. 注册 pending hash ownership (在 pack 之前, 防 duplicate, §八)
        for h in new_hash:
            self.pending_store_hashes[h] = job_id

        # 11. 同步 pack source KV(+Scale) -> 独占 staging bundle (§十二)。pack 完成后
        #     source MLU blocks 可安全释放。失败 -> 完整 rollback (§十七)。
        try:
            t_pack0 = _now_ns()
            if self.quantized:
                self.mover.pack_to_staging(staging_kv, staging_scale, new_mlu,
                                           pack_method=pack_method,
                                           producer_event=producer_event)
            else:
                self.mover.pack_to_staging(staging_kv, new_mlu, pack_method=pack_method,
                                           producer_event=producer_event)
            pack_ms = (_now_ns() - t_pack0) / 1e6
        except Exception as e:
            self._rollback_submit(job_id, new_hash, new_cpu, slot_id)
            self.metrics.cpu_async_store_failed += 1
            return (False, {"reason": "store_io_failure", "num_blocks": num_new,
                            "error": repr(e), "cacheable_tokens": cacheable_tokens})

        # 12. 异步 D2H: staging(KV+Scale) -> CPU 最终池 (§十三)。pack 已完成, D2H 只依赖
        #     独立 staging, 不再读 source MLU blocks。KV+Scale 同 transfer_stream, 单 Event (§十二)。
        try:
            if self.quantized:
                event = self.mover.submit_d2h(staging_kv, staging_scale, new_cpu,
                                              pack_event=None)
            else:
                event = self.mover.submit_d2h(staging_kv, new_cpu, pack_event=None)
        except Exception as e:
            self._rollback_submit(job_id, new_hash, new_cpu, slot_id)
            self.metrics.cpu_async_store_failed += 1
            return (False, {"reason": "store_io_failure", "num_blocks": num_new,
                            "error": repr(e), "cacheable_tokens": cacheable_tokens})

        # 13. 创建 AsyncStoreJob (STORE_PENDING)
        job = AsyncStoreJob(
            job_id=job_id, block_hashes=list(new_hash), cpu_block_ids=list(new_cpu),
            mlu_block_ids=list(new_mlu), num_blocks=num_new,
            num_tokens=cacheable_tokens, staging_slot_id=slot_id,
            event=event, submit_time_ns=t_submit_start, pack_ms=pack_ms,
            state=STORE_PENDING, request_id=request_id,
        )
        self.pending_jobs[job_id] = job
        self.metrics.cpu_async_store_submitted += 1
        self.metrics.cpu_async_store_pending_jobs = len(self.pending_jobs)
        self.metrics.cpu_async_store_pending_blocks += num_new
        self.metrics.cpu_async_store_pack_ms_total += pack_ms
        # Quantized traffic metrics (§二十二): KV + Scale D2H 字节
        if self.quantized:
            kv_bytes = num_new * self.cpu_pool.kv_block_bytes
            sc_bytes = num_new * self.cpu_pool.scale_block_bytes
            self.metrics.store_kv_bytes += kv_bytes
            self.metrics.store_scale_bytes += sc_bytes
            # 对照 BF16 基准的流量节省: bf16_block_bytes - (kv+scale)
            bf16_blk = (2 * self.num_layers * self.num_kv_heads
                        * self.block_size * self.head_dim * 2)
            self.metrics.quantized_traffic_saved_bytes += max(
                0, num_new * bf16_blk - (kv_bytes + sc_bytes))
        visible_submit_ms = (_now_ns() - t_submit_start) / 1e6
        self.metrics.cpu_async_store_visible_submit_ms_total += visible_submit_ms
        if len(self.pending_jobs) > self.metrics.max_pending_jobs_observed:
            self.metrics.max_pending_jobs_observed = len(self.pending_jobs)

        self._dbg_submit(job, evicted, visible_submit_ms)
        return (True, {"job_id": job_id, "cpu_block_ids": list(new_cpu),
                       "num_blocks": num_new, "reason": "submitted",
                       "pack_ms": pack_ms, "visible_submit_ms": visible_submit_ms,
                       "evicted": evicted, "cacheable_tokens": cacheable_tokens,
                       "slot_id": slot_id})
                        def _rollback_submit(self, job_id, new_hash, new_cpu, slot_id):
        """submit 过程中异常的完整 rollback (§十七)。"""
        for h in new_hash:
            if self.pending_store_hashes.get(h) == job_id:
                del self.pending_store_hashes[h]
        self.cpu_pool.free(new_cpu)
        self.staging_pool.release(slot_id)

    def _dbg_submit(self, job, evicted, visible_ms):
        if not getattr(self, "_async_debug", 0):
            return
        print(f"[CPU-OFFLOAD] ASYNC-STORE job={job.job_id} blocks={job.num_blocks} "
              f"tokens={job.num_tokens} pack={job.pack_ms:.2f}ms "
              f"visible={visible_ms:.2f}ms evicted={evicted} "
              f"slot={job.staging_slot_id} pending={len(self.pending_jobs)}", flush=True)

    def poll_store_completions(self) -> int:
        """Event polling (§十五/§十六)。非阻塞, 完成的 Job commit READY。

        由 Scheduler/Engine 每个正常 step 调用。event.query() 必须 non-blocking (§十五)。
        返回本次完成的 Job 数。
        """
        if not self.pending_jobs:
            return 0
        completed = 0
        # 遍历快照 (complete_store 会修改 pending_jobs)
        for job_id in list(self.pending_jobs.keys()):
            job = self.pending_jobs.get(job_id)
            if job is None:
                continue
            try:
                done = job.event.query()
            except Exception:
                # Event query 异常 -> 视为失败, rollback (§十七)
                self._fail_job(job)
                continue
            if done:
                self._complete_job(job)
                completed += 1
        return completed
        def _complete_job(self, job: AsyncStoreJob):
        """Store 完成 commit (§十六)。D2H complete -> commit READY, 绝不提前。

        1. Event 已完成
        2. 从 pending_store_hashes 删除 job hashes
        3. hash -> cpu_block_id commit 到 READY index (insert, MRU 端)
        4. staging slot FREE
        5. job state = STORE_DONE
        6. metrics completed += 1, d2h_ms (若 Event 可计时)
        7. 从 pending_jobs 删除
        """
        # D2H 计时 (若 Event 支持 elapsed_time, 需两个 event; 此处单 event 仅记录完成)
        # 释放 pending hash ownership
        for h in job.block_hashes:
            if self.pending_store_hashes.get(h) == job.job_id:
                del self.pending_store_hashes[h]
        # commit READY: hash -> cpu_block_id (insert, 新 key 追加 MRU; duplicate 不 touch §九)
        for h, c in zip(job.block_hashes, job.cpu_block_ids):
            applied, existing = self.index.insert(h, c)
            if not applied:
                # 同 hash 已 READY (理论不应: pending 时已挡 duplicate; 保守: 释放重复占的)
                self.cpu_pool.free([c])
        # 释放 staging slot
        self.staging_pool.release(job.staging_slot_id)
        # metrics
        self.metrics.cpu_async_store_completed += 1
        self.metrics.cpu_async_store_pending_blocks -= job.num_blocks
        self.metrics.cpu_store_blocks += job.num_blocks
        job.state = STORE_DONE
        del self.pending_jobs[job.job_id]
        self.metrics.cpu_async_store_pending_jobs = len(self.pending_jobs)
        if getattr(self, "_async_debug", 0):
            print(f"[CPU-OFFLOAD] ASYNC-STORE-DONE job={job.job_id} "
                  f"blocks={job.num_blocks} pending={len(self.pending_jobs)}", flush=True)

 def _fail_job(self, job: AsyncStoreJob):
        """Store 失败 rollback (§十七)。释放 pending hash / CPU block / staging slot, 不 commit READY。"""
        for h in job.block_hashes:
            if self.pending_store_hashes.get(h) == job.job_id:
                del self.pending_store_hashes[h]
        self.cpu_pool.free(job.cpu_block_ids)
        self.staging_pool.release(job.staging_slot_id)
        self.metrics.cpu_async_store_failed += 1
        self.metrics.cpu_async_store_pending_blocks -= job.num_blocks
        job.state = STORE_FAILED
        del self.pending_jobs[job.job_id]
        self.metrics.cpu_async_store_pending_jobs = len(self.pending_jobs)

    def flush_pending_stores(self, timeout_s: float = 30.0) -> int:
        """同步等待全部 pending Store 完成 (§二十三)。

        用于 engine shutdown / benchmark 等待 / test teardown / CPU cache clear 前。
        可以同步等待 pending Event; 正常请求热路径不调用 flush。
        返回完成数 (含失败数)。
        """
        if not self.pending_jobs:
            return 0
        done = 0
        deadline = _now_ns() + int(timeout_s * 1e9)
        while self.pending_jobs:
            for job_id in list(self.pending_jobs.keys()):
                job = self.pending_jobs.get(job_id)
                if job is None:
                    continue
                try:
                    # flush 可以同步等待 (§二十三)
                    job.event.synchronize()
                    self._complete_job(job)
                    done += 1
                except Exception:
                    self._fail_job(job)
                    done += 1
            if _now_ns() > deadline and self.pending_jobs:
                # 超时: 剩余标失败 (避免 hang)
                for job_id in list(self.pending_jobs.keys()):
                    self._fail_job(self.pending_jobs[job_id])
                    done += 1
                break
        return done
         def num_pending_jobs(self) -> int:
        return len(self.pending_jobs)

    def num_pending_blocks(self) -> int:
        return self.metrics.cpu_async_store_pending_blocks

    # ------------------------------------------------------------------
    # Occupancy / metrics 诊断 (§十七)
    # ------------------------------------------------------------------
    def occupancy(self) -> float:
        used = self.cpu_pool.num_used_blocks()
        return used / self.capacity if self.capacity else 0.0

    def invariant_ok(self) -> bool:
        """容量 Invariant (§十): free + ready + pending == capacity, 且无重叠。

        - free_blocks + ready_blocks + pending_reserved_blocks == capacity
        - ready CPU ids 无重复
        - pending CPU ids 无重复
        - ready/pending CPU ids 不重叠
        - ready hash 不在 pending hash 中
        """
        free = self.cpu_pool.num_free_blocks()
        ready = len(self.index)
        pending_blocks = self.num_pending_blocks()
        if free + ready + pending_blocks != self.capacity:
            return False
        # ready CPU ids 无重复
        ready_cpus = list(self.index._table.values())
        if len(set(ready_cpus)) != len(ready_cpus):
            return False
        # pending CPU ids 无重复 + 与 ready 不重叠
        pending_cpus = []
        for job in self.pending_jobs.values():
            pending_cpus.extend(job.cpu_block_ids)
        if len(set(pending_cpus)) != len(pending_cpus):
            return False
        if set(ready_cpus) & set(pending_cpus):
            return False
        # ready hash 不在 pending hash 中
        ready_hashes = set(self.index._table.keys())
         pending_hashes = set(self.pending_store_hashes.keys())
        if ready_hashes & pending_hashes:
            return False
        # pending hash 数 == pending CPU blocks 数 (一一对应)
        if len(pending_hashes) != pending_blocks:
            return False
        # 第八步: ref_count 全部 >= 0 (CPUPrefixIndex.release_refs 已守下界, 此处复查)
        for cid, rc in self.index._ref.items():
            if rc < 0:
                return False
        return True

    def metrics_dict(self):
        d = self.metrics.as_dict()
        d["cpu_blocks_used"] = self.cpu_pool.num_used_blocks()
        d["cpu_blocks_free"] = self.cpu_pool.num_free_blocks()
        d["cpu_capacity"] = self.capacity
        d["occupancy"] = round(self.occupancy(), 4)
        lb = d["cpu_cache_lookup_blocks"]
        d["block_hit_rate"] = (d["cpu_cache_hit_blocks"] / lb) if lb else 0.0
        d["pending_jobs"] = self.num_pending_jobs()
        d["pending_blocks"] = self.num_pending_blocks()
        if self.staging_pool is not None:
            d["staging_busy"] = self.staging_pool.num_busy()
            d["staging_free"] = self.staging_pool.num_free()
            d["staging_mem_bytes"] = self.staging_pool.mem_bytes
        # 第八步 async load 诊断
        d["pending_load_jobs"] = self.num_pending_load_jobs()
        d["pending_load_blocks"] = self.num_pending_load_blocks()
        d["ready_ref0"] = len(self.index) - self.index.num_protected()
        d["ready_ref_gt0"] = self.index.num_protected()
        if self.load_staging_pool is not None:
            d["load_staging_busy"] = self.load_staging_pool.num_busy()
            d["load_staging_free"] = self.load_staging_pool.num_free()
            d["load_staging_mem_bytes"] = self.load_staging_pool.mem_bytes
        # 第九步: coalescing / adaptive policy 诊断
        d["load_policy"] = self.load_policy
        d["coalesced_groups"] = self.metrics.cpu_load_coalesced_groups
        d["coalesced_requests"] = self.metrics.cpu_load_coalesced_requests
        d["duplicate_h2d_avoided"] = self.metrics.cpu_load_duplicate_h2d_avoided
        d["waiters_current"] = self.metrics.cpu_load_waiters_current
        d["waiters_peak"] = self.metrics.cpu_load_waiters_peak
        d["h2d_load_jobs"] = self.metrics.cpu_h2d_load_jobs
        d["h2d_blocks_total"] = self.metrics.cpu_h2d_blocks_total
        d["shared_prefix_blocks"] = self.metrics.mlu_shared_prefix_blocks
        d["duplicate_prefix_blocks_avoided"] = self.metrics.mlu_duplicate_prefix_blocks_avoided
        d["prefix_memory_saved_mb"] = round(self.metrics.mlu_prefix_memory_saved_mb, 1)
        d["pending_prefix_groups"] = self.metrics.pending_prefix_groups
        # P0: stream dependency hardening 诊断
        d["stream_dependency_events_recorded"] = self.metrics.stream_dependency_events_recorded
        d["stream_dependency_waits"] = self.metrics.stream_dependency_waits
        d["device_wide_sync_hotpath_count"] = self.metrics.device_wide_sync_hotpath_count
        return d

