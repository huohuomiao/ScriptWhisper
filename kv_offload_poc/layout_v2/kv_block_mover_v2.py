#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""KVBlockMoverV2 —— Block-Major layout 的 MLU<->CPU KV block 同步搬运器。

解决 V1 的 host strided pool 瓶颈: 把 layout conversion 全部移到 MLU/device 侧,
让 MLU <-> CPU 的 DMA 段直接读写最终 CPU Block-Major Pool (连续), host 端零
额外 reformat。

Layout:
  MLU native (不可改):          (2, L, N, H, T, D)      # (KV/Layer/Block/Head/Tok/Dim)
  V2 contiguous staging (mlu):  (N2, 2, L, H, T, D)     # block 提到最外层
  CPU Block-Major pool:         (B,  2, L, H, T, D)     # 与 staging 完全同秩同形

单个 logical CPU block = cpu_pool.kv[block_id] 是连续 (2, L, H, T, D) ≈ 2.25MB。

---------------------------------------------------------------
STORE (MLU -> CPU, D2H):
  T_pack_device:  MLU native {mlu_ids} -> 一次 copy 到连续 V2 MLU staging
                  pack = mlu_kv[:, :, {ids}, :, :, :].permute(2,0,1,3,4,5).contiguous()
                            (A advanced-index / B index_select / slice 三种 source 变体)
  T_D2H:          staging (N,2,L,H,T,D) --一次 D2H--> CPU Block-Major 连续段
  host 端: 零 reformat, 直接落池。

LOAD (CPU -> MLU, H2D):
  T_H2D:          CPU 连续块 --一次 H2D--> 连续 V2 ML staging
  T_unpack:       staging.permute(1,2,0,3,4,5) -> 写回 MLU native {mlu_ids}
                  (adv_assign / index_copy / slice / contig_run)
  host 端: 零 reformat, 直接从连续池读。

本阶段: 同步。store()/load() 返回时数据已 ready (显式 synchronize transfer_stream)。
不实现 async / pending / refcount。
"""
from __future__ import annotations

from typing import Sequence

import torch

from kv_offload_poc.layout_v2.cpu_kv_pool_v2 import CPUKVPoolV2

# native dims
_KVO, _LYR, _BLK, _HD, _TOK, _DIM = 0, 1, 2, 3, 4, 5


def _is_contiguous_run(ids: Sequence[int]) -> bool:
    """ids 是否为连续序列 (步长 +1 或 -1)。"""
    if len(ids) <= 1:
        return True
    asc = all(ids[i + 1] == ids[i] + 1 for i in range(len(ids) - 1))
    desc = all(ids[i + 1] == ids[i] - 1 for i in range(len(ids) - 1))
    return asc or desc
    def _contig_slice(ids: Sequence[int]):
    """连续 ids -> (start, stop, step)。"""
    if len(ids) == 1:
        return (ids[0], ids[0] + 1, 1)
    if ids[1] > ids[0]:
        return (ids[0], ids[0] + len(ids), 1)
    else:
        return (ids[0], ids[0] - len(ids) - 1, -1)


def _contiguous_runs(ids: Sequence[int]) -> list[tuple[int, int, int]]:
    """升序连续段 -> [(start_idx, run_start_id, run_len), ...]。"""
    runs = []
    run_start_idx = 0
    run_start_id = ids[0]
    run_len = 1
    for i in range(1, len(ids)):
        if ids[i] == ids[i - 1] + 1:
            run_len += 1
        else:
            runs.append((run_start_idx, run_start_id, run_len))
            run_start_idx = i
            run_start_id = ids[i]
            run_len = 1
    runs.append((run_start_idx, run_start_id, run_len))
    return runs


class KVBlockMoverV2:
    """Block-Major MLU <-> CPU KV block 同步搬运器。"""

    def __init__(self, mlu_kv, cpu_pool: CPUKVPoolV2, max_blocks=None, device=None):
        self.mlu_kv = mlu_kv
        self.cpu_pool = cpu_pool
        self.device = device if device is not None else mlu_kv.device

        if mlu_kv.dim() != 6:
            raise ValueError(f"mlu_kv 须为 6D, got shape {tuple(mlu_kv.shape)}")
        for name, m, c, i in [
            ("K/V", mlu_kv.shape[0], cpu_pool.shape[1], 0),
            ("layer", mlu_kv.shape[1], cpu_pool.shape[2], 0),
            ("head", mlu_kv.shape[3], cpu_pool.shape[3], 0),
            ("token", mlu_kv.shape[4], cpu_pool.shape[4], 0),
            ("head_dim", mlu_kv.shape[5], cpu_pool.shape[5], 0),
        ]:
            if m != c:
                raise ValueError(f"{name} 维不匹配: mlu={m} cpu={c}")
        if mlu_kv.dtype != cpu_pool.dtype:
            raise ValueError("dtype 不匹配")

        self.num_blocks_mlu = mlu_kv.shape[2]
        self.transfer_stream = torch.mlu.Stream()
        # 第七步 Async Store: pack 与 D2H 分流。pack 用独立 pack_stream (device 计算),
        # D2H 用 transfer_stream (DMA)。submit_store 中 transfer_stream.wait_event(pack_event)
        # 保证 D2H 在 pack 之后; host 仅 pack_event.synchronize() 等 pack (~2ms), D2H 后台异步。
        # 关键: 若 pack 与 D2H 共用 transfer_stream, Job B 的 pack 会被 Job A 的 D2H(~17ms)
        # 阻塞, 等同同步。分流后 Job B 的 pack (~2ms) 不依赖 Job A 的 D2H, 可与 compute 重叠。
        self.pack_stream = torch.mlu.Stream()
        max_blocks = max_blocks or max(cpu_pool.capacity, 256)
        self.max_blocks_staging = max_blocks
        # 预分配连续 V2 ML staging, benchmark 外一次性分配, 复用
        self._mlu_staging_v2 = torch.empty(
            (max_blocks, 2, mlu_kv.shape[1], mlu_kv.shape[3],
             mlu_kv.shape[4], mlu_kv.shape[5]),
            dtype=mlu_kv.dtype, device=self.device,
        )
        self._ev = [torch.mlu.Event(enable_timing=True) for _ in range(6)]

    def staging_v2(self, n_blocks: int) -> torch.Tensor:
        if n_blocks > self._mlu_staging_v2.shape[0]:
            raise RuntimeError(
                f"staging_v2: 请求 {n_blocks} 超过预分配 {self._mlu_staging_v2.shape[0]}")
        return self._mlu_staging_v2[:n_blocks]

    # ------------------------------------------------------------------
    # 连接 CPU 池的连续切片 (host 端零 reformat 的关键)
    # ------------------------------------------------------------------
    def _cpu_contig_seg(self, cpu_ids: Sequence[int]) -> torch.Tensor:
        if not _is_contiguous_run(cpu_ids):
            raise RuntimeError("主性能路径要求 CPU ids 连续 (allocate 返回连续 [0..n-1])")
        if len(cpu_ids) == 1:
            start, end = cpu_ids[0], cpu_ids[0] + 1
        elif cpu_ids[1] > cpu_ids[0]:
            start, end = cpu_ids[0], cpu_ids[0] + len(cpu_ids)
        else:
            raise RuntimeError("主路径不支持降序 CPU ids")
        return self.cpu_pool.blocks_slice(start, end)

    # ------------------------------------------------------------------
    # device-side pack: MLU native {mlu_ids} -> 连续 V2 staging
    # ------------------------------------------------------------------
    def pack(self, staging: torch.Tensor, mlu_ids: Sequence[int], method: str):
        """把 MLU native 的 {mlu_ids} 填进连续 V2 staging (N,2,L,H,T,D)。

        method:
          "A"  advanced indexing  mlu_kv[:, :, idx, :, :, :] -> permute -> materialize
          "B"  index_select(dim=2) -> permute -> materialize
          "slice"  连续 mlu_ids, strided slice -> permute -> materialize (无 gather)
        """
        if method == "slice":
            ss = _contig_slice(mlu_ids)
            src = self.mlu_kv[:, :, slice(ss[0], ss[1], ss[2]), :, :, :]
            staging.copy_(src.permute(2, 0, 1, 3, 4, 5).contiguous())
        elif method == "A":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            sub = self.mlu_kv[:, :, idx, :, :, :]  # (2,L,n,H,T,D) advanced gather
            staging.copy_(sub.permute(2, 0, 1, 3, 4, 5).contiguous())
        elif method == "B":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            sub = self.mlu_kv.index_select(_BLK, idx)  # (2,L,n,H,T,D)
            staging.copy_(sub.permute(2, 0, 1, 3, 4, 5).contiguous())
        else:
            raise ValueError(f"_pack: 未知 method {method!r}")

 # device-side unpack: 连续 V2 staging -> MLU native {mlu_ids}
    # ------------------------------------------------------------------
    def unpack(self, staging: torch.Tensor, mlu_ids: Sequence[int], method: str):
        tmp = staging.permute(1, 2, 0, 3, 4, 5)  # view (2, L, n, H, T, D)
        if method == "slice":
            if not _is_contiguous_run(mlu_ids):
                raise ValueError("slice unpack 仅支持连续 mlu_ids")
            ss = _contig_slice(mlu_ids)
            self.mlu_kv[:, :, slice(ss[0], ss[1], ss[2]), :, :, :].copy_(tmp)
        elif method == "adv_assign":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            self.mlu_kv[:, :, idx, :, :, :] = tmp
        elif method == "index_copy":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            self.mlu_kv.index_copy_(
                2, idx, tmp.contiguous() if not tmp.is_contiguous() else tmp)
        elif method == "contig_run":
            for start_idx, run_id, run_len in _contiguous_runs(mlu_ids):
                seg = tmp[:, :, start_idx: start_idx + run_len, :, :, :]
                self.mlu_kv[:, :, run_id: run_id + run_len, :, :, :].copy_(seg)
        else:
            raise ValueError(f"unpack: 未知 method {method!r}")

 # STORE: MLU -> CPU (D2H)
    # ------------------------------------------------------------------
    def store(self, mlu_block_ids, cpu_block_ids, pack_method="A", producer_event=None):
        n = len(mlu_block_ids)
        if n != len(cpu_block_ids):
            raise ValueError(f"store: len(mlu)={n} != len(cpu)={len(cpu_block_ids)}")
        if n == 0:
            return
        with torch.mlu.stream(self.transfer_stream):
            if producer_event is not None:
                self.transfer_stream.wait_event(producer_event)
            staging = self._mlu_staging_v2[:n]
            self.pack(staging, mlu_block_ids, pack_method)
            cpu_seg = self._cpu_contig_seg(cpu_block_ids)
            cpu_seg.copy_(staging, non_blocking=True)  # D2H 一次直达最终 CPU 池
        self.transfer_stream.synchronize()

    def store_timed(self, mlu_block_ids, cpu_block_ids, pack_method="A"):
        """返回 (T_pack_device_ms, T_D2H_device_ms, T_store_wall_ms)。"""
        n = len(mlu_block_ids)
        t0 = _now()
        with torch.mlu.stream(self.transfer_stream):
            staging = self._mlu_staging_v2[:n]
            self._ev[0].record()
            self.pack(staging, mlu_block_ids, pack_method)
            self._ev[1].record()
            cpu_seg = self._cpu_contig_seg(cpu_block_ids)
            cpu_seg.copy_(staging, non_blocking=True)
            self._ev[2].record()
        self.transfer_stream.synchronize()
        wall = (_now() - t0) * 1000
        return (self._ev[0].elapsed_time(self._ev[1]),
                self._ev[1].elapsed_time(self._ev[2]), wall)
                # 第七步 Async Store: 同步 pack + 异步 D2H (submit_store / poll)
    # ==================================================================
    def pack_to_staging(self, staging, mlu_block_ids, pack_method="A", producer_event=None):
        """同步 pack: 把 MLU native {mlu_block_ids} pack 进给定 staging (N,2,L,H,T,D)。

        在 pack_stream 上执行, 返回时 pack 已完成 (pack_stream.synchronize),
        保证原 source MLU physical blocks 可安全释放/覆盖 (§八/§十二)。
        staging 必须是调用方独占的 slot tensor (AsyncStoreStagingPool 提供)。

        P0 Stream Dependency Hardening: 若提供 producer_event (KV 生产者流 —— 通常是
        default/compute stream —— 上 record 的 Event), pack_stream.wait_event 保证 pack
        读 source MLU blocks 在生产者写完成之后 (跨流依赖, 不阻塞 host, 不需要 device-wide
        torch.mlu.synchronize())。producer_event 必须记录在最后一次会修改即将 offload 的 KV
        写之后 (§五)。None = 当前行为 (调用方已保证 source ready)。
        """
        with torch.mlu.stream(self.pack_stream):
            if producer_event is not None:
                self.pack_stream.wait_event(producer_event)
            self.pack(staging, mlu_block_ids, pack_method)
        self.pack_stream.synchronize()

    def submit_d2h(self, staging, cpu_block_ids, pack_event=None):
        """在 transfer_stream 上发起 staging -> CPU 最终池 的 non_blocking D2H, 返回 Event。

        若提供 pack_event (pack_stream 上 record 的 Event), transfer_stream.wait_event
        保证 D2H 在 pack 之后执行 (跨流依赖, 不阻塞 host)。返回 record 在 D2H 之后的 Event,
        调用方 poll event.query() 判断 D2H 是否完成 (non-blocking)。
        """
        with torch.mlu.stream(self.transfer_stream):
            if pack_event is not None:
                self.transfer_stream.wait_event(pack_event)
            cpu_seg = self._cpu_contig_seg(cpu_block_ids)
            cpu_seg.copy_(staging, non_blocking=True)  # D2H 直达最终 CPU 池
            ev = torch.mlu.Event(enable_timing=True)
            ev.record()
        return ev
        def pack_to_staging_timed(self, staging, mlu_block_ids, pack_method="A"):
        """同步 pack + 计时, 返回 (pack_device_ms, pack_wall_ms)。"""
        t0 = _now()
        with torch.mlu.stream(self.pack_stream):
            self._ev[0].record()
            self.pack(staging, mlu_block_ids, pack_method)
            self._ev[1].record()
        self.pack_stream.synchronize()
        wall = (_now() - t0) * 1000
        return self._ev[0].elapsed_time(self._ev[1]), wall

    def record_pack_event(self, staging, mlu_block_ids, pack_method="A"):
        """在 pack_stream 上发起 pack 并 record pack_event, 返回 pack_event (不 synchronize)。

        用于需要 pack 与 D2H 在不同 stream 并行提交的场景。调用方需自行保证 pack 完成
        前不释放 source MLU blocks (通常用 pack_event.synchronize() 或 wait_event)。
        """
        with torch.mlu.stream(self.pack_stream):
            self.pack(staging, mlu_block_ids, pack_method)
            pack_event = torch.mlu.Event(enable_timing=True)
            pack_event.record()
        return pack_event

    # ------------------------------------------------------------------
    # LOAD / CPU -> MLU (H2D)
    # ------------------------------------------------------------------
    def load(self, cpu_block_ids, mlu_block_ids, unpack_method="adv_assign"):
        n = len(cpu_block_ids)
        if n != len(mlu_block_ids):
            raise ValueError(f"load: len(cpu)={n} != len(mlu)={len(mlu_block_ids)}")
        if n == 0:
            return
        cpu_seg = self._cpu_contig_seg(cpu_block_ids)
        with torch.mlu.stream(self.transfer_stream):
            staging = self._mlu_staging_v2[:n]
            staging.copy_(cpu_seg, non_blocking=True)      # H2D 一次读连续 CPU 池
            self.unpack(staging, list(mlu_block_ids), unpack_method)
        self.transfer_stream.synchronize()

    def load_timed(self, cpu_block_ids, mlu_block_ids, unpack_method):
        """返回 (T_H2D_device_ms, T_unpack_device_ms, T_wall_ms)。"""
        n = len(cpu_block_ids)
        cpu_seg = self._cpu_contig_seg(cpu_block_ids)
        t0 = _now()
        with torch.mlu.stream(self.transfer_stream):
            staging = self._mlu_staging_v2[:n]
            self._ev[3].record()
            staging.copy_(cpu_seg, non_blocking=True)  # H2D
            self._ev[4].record()
            self.unpack(staging, list(mlu_block_ids), unpack_method)
            self._ev[5].record()
        self.transfer_stream.synchronize()
        wall = (_now() - t0) * 1000
        return self._ev[3].elapsed_time(self._ev[4]), self._ev[4].elapsed_time(self._ev[5]), wall

    # ==================================================================
    # 第八步 Async Load: 异步 H2D + device unpack + Event (submit_load_async)
    # ==================================================================
    def submit_load_async(self, staging, cpu_block_ids, mlu_block_ids,
                          unpack_method="contig_run"):
        """在 transfer_stream 上发起 CPU -> MLU 的 non_blocking H2D + device unpack,
        record Event AFTER unpack 完成, 返回 Event (§十四)。

        关键 (§十四): Event 必须记录在最终 MLU native KV 已写回之后 (unpack 完成),
        而不是仅 H2D 完成后 —— 否则 commit 时 MLU KV 尚未 scatter 到 native layout,
        forward 会读到未初始化数据。
        staging 必须是调用方独占的 load slot tensor (AsyncLoadStagingPool 提供),
        shape (n, 2, L, H, T, D)。cpu_block_ids 必须连续 (load slot 容量内),
        按 split_contiguous_runs 分段 H2D (eviction 后 CPU ids 可能非连续)。

        返回: torch.mlu.Event (record 在 unpack 之后, 调用方 poll event.query())。
        本方法不 synchronize (异步返回); 调用方在 Event complete 前不得 forward 该 seq,
        不得复用 staging slot, 不得 eviction source CPU blocks (由 refcount 保护)。
        """
        with torch.mlu.stream(self.transfer_stream):
            # 按连续 cpu-run 分段 H2D (cpu ids 未必连续), 写入 staging 对应段
            runs = _contiguous_runs(cpu_block_ids)
            for start_idx, run_cpu_id, run_len in runs:
                seg_cpu = list(range(run_cpu_id, run_cpu_id + run_len))
                cpu_seg = self._cpu_contig_seg(seg_cpu)
                staging_seg = staging[start_idx: start_idx + run_len]
                staging_seg.copy_(cpu_seg, non_blocking=True)  # H2D 直读连续 CPU 池
            # device unpack: staging -> MLU native {mlu_block_ids} (同 stream, 顺序依赖 H2D)
            self.unpack(staging, list(mlu_block_ids), unpack_method)
            # Event 必须在 unpack 之后 (§十四)
            ev = torch.mlu.Event(enable_timing=True)
            ev.record()
        return ev

    def __repr__(self) -> str:
        return (
            f"KVBlockMoverV2({tuple(self.mlu_kv.shape)} on {self.device}, "
            f"pool={self.cpu_pool!r}, staging={tuple(self._mlu_staging_v2.shape)})"
        )


def _now():
    import time
    return time.perf_counter()