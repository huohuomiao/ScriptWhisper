#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""QuantizedKVBlockMover —— Block-Major 量化 KV (INT8) + Scale (FP32) 同步搬运器。

在 V2 (BF16 KV) 基础上, 把 MLU<->CPU 的搬运对象从单一 BF16 KV 扩展为
**INT8 KV + FP32 Scale 两个张量**, 二者 block ordering 严格一致, 共用同一组
mlu_block_ids / cpu_block_ids。

Layout (Qwen3-8B, block_size=16, L=36, H=8, D=128):
  MLU native KV:     (2, L, N, H, T, D)  int8       # block 维 index 2
  MLU native Scale:  (2, L, N, H, T)     float32    # block 维 index 2
  V3 staging (mlu):  KV    (N, 2, L, H, T, D) int8
                     Scale (N, 2, L, H, T)    float32   # block 提到最外层
  CPU V3 pool:       KV    (B, 2, L, H, T, D) int8
                     Scale (B, 2, L, H, T)    float32   # 与 staging 同秩同形

单个 logical CPU block:
  cpu_kv[id]    = (2, L, H, T, D) int8     连续 ≈ 1.125 MiB
  cpu_scale[id] = (2, L, H, T)    fp32     连续 ≈ 0.0352 MiB
  合计 ≈ 1.1602 MiB (vs V2 BF16 2.25 MiB, 容量 1.9394x)

---------------------------------------------------------------
STORE (MLU -> CPU, D2H):
  pack_kv:    MLU native {mlu_ids} -> 连续 V3 KV staging    (device permute)
  pack_scale: MLU native {mlu_ids} -> 连续 V3 Scale staging (device permute)
  D2H_kv:     KV staging    -> CPU V3 KV 池连续段    (一次直达, host 零 reformat)
  D2H_scale:  Scale staging  -> CPU V3 Scale 池连续段 (一次直达, host 零 reformat)
  KV/Scale block ordering 严格一致 (同一组 ids, 同一 pack 顺序)。

LOAD (CPU -> MLU, H2D):
  H2D_kv:     CPU V3 KV 连续段    -> KV staging
  H2D_scale:  CPU V3 Scale 连续段 -> Scale staging
  unpack_kv:    KV staging    -> MLU native {mlu_ids}
  unpack_scale: Scale staging -> MLU native {mlu_ids}
  同一个 target_mlu_block_id 必须同时接收正确 KV + Scale (§七)。
  本阶段: 同步。store()/load() 返回时数据已 ready (显式 synchronize transfer_stream)。
不实现 async / pending / refcount / coalescing (§二十一禁止)。
"""
from __future__ import annotations

from typing import Sequence

import torch

from kv_offload_poc.quantized_l2.cpu_kv_pool_v3_quantized import CPUKVPoolV3Quantized

# native dims (MLU KV (2,L,N,H,T,D))
_KVO, _LYR, _BLK, _HD, _TOK, _DIM = 0, 1, 2, 3, 4, 5
# native scale dims (MLU scale (2,L,N,H,T))
_SBLK = 2


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


class QuantizedKVBlockMover:
    """Block-Major 量化 MLU <-> CPU (INT8 KV + FP32 Scale) 同步搬运器。"""

    def __init__(self, mlu_kv, mlu_scales, cpu_pool: CPUKVPoolV3Quantized,
                 max_blocks=None, device=None):
        self.mlu_kv = mlu_kv
        self.mlu_scales = mlu_scales
        self.cpu_pool = cpu_pool
        self.device = device if device is not None else mlu_kv.device

        # ---- 维度一致性校验 ----
        if mlu_kv.dim() != 6:
            raise ValueError(f"mlu_kv 须为 6D, got shape {tuple(mlu_kv.shape)}")
        if mlu_scales.dim() != 5:
            raise ValueError(f"mlu_scales 须为 5D, got shape {tuple(mlu_scales.shape)}")
            for name, m, c in [
            ("K/V", mlu_kv.shape[0], cpu_pool.kv_shape[1]),
            ("layer", mlu_kv.shape[1], cpu_pool.kv_shape[2]),
            ("head", mlu_kv.shape[3], cpu_pool.kv_shape[3]),
            ("token", mlu_kv.shape[4], cpu_pool.kv_shape[4]),
            ("head_dim", mlu_kv.shape[5], cpu_pool.kv_shape[5]),
        ]:
            if m != c:
                raise ValueError(f"KV {name} 维不匹配: mlu={m} cpu={c}")
        # Scale: (2,L,N,H,T) vs cpu pool scale (B,2,L,H,T)
        for name, m, c in [
            ("scale K/V", mlu_scales.shape[0], cpu_pool.scale_shape[1]),
            ("scale layer", mlu_scales.shape[1], cpu_pool.scale_shape[2]),
            ("scale head", mlu_scales.shape[3], cpu_pool.scale_shape[3]),
            ("scale token", mlu_scales.shape[4], cpu_pool.scale_shape[4]),
        ]:
            if m != c:
                raise ValueError(f"Scale {name} 维不匹配: mlu={m} cpu={c}")
        # KV 与 Scale 的 block 数必须一致
        if mlu_kv.shape[2] != mlu_scales.shape[2]:
            raise ValueError(
                f"mlu_kv block 数 {mlu_kv.shape[2]} != mlu_scales block 数 {mlu_scales.shape[2]}")
        # dtype 校验
        if mlu_kv.dtype != cpu_pool.kv_dtype:
            raise ValueError(f"KV dtype 不匹配: mlu={mlu_kv.dtype} cpu={cpu_pool.kv_dtype}")
        if mlu_scales.dtype != cpu_pool.scale_dtype:
            raise ValueError(
                f"Scale dtype 不匹配: mlu={mlu_scales.dtype} cpu={cpu_pool.scale_dtype}")

        self.num_blocks_mlu = mlu_kv.shape[2]
        self.transfer_stream = torch.mlu.Stream()
         self.pack_stream = torch.mlu.Stream()
        max_blocks = max_blocks or max(cpu_pool.capacity, 256)
        self.max_blocks_staging = max_blocks

        # 预分配连续 V3 MLU staging (KV + Scale), benchmark 外一次性分配, 复用
        self._mlu_kv_staging = torch.empty(
            (max_blocks, 2, mlu_kv.shape[1], mlu_kv.shape[3],
             mlu_kv.shape[4], mlu_kv.shape[5]),
            dtype=mlu_kv.dtype, device=self.device,
        )
        self._mlu_scale_staging = torch.empty(
            (max_blocks, 2, mlu_scales.shape[1], mlu_scales.shape[3],
             mlu_scales.shape[4]),
            dtype=mlu_scales.dtype, device=self.device,
        )
        self._ev = [torch.mlu.Event(enable_timing=True) for _ in range(10)]

    def kv_staging(self, n_blocks: int) -> torch.Tensor:
        if n_blocks > self._mlu_kv_staging.shape[0]:
            raise RuntimeError(
                f"kv_staging: 请求 {n_blocks} 超过预分配 {self._mlu_kv_staging.shape[0]}")
        return self._mlu_kv_staging[:n_blocks]

    def scale_staging(self, n_blocks: int) -> torch.Tensor:
        if n_blocks > self._mlu_scale_staging.shape[0]:
            raise RuntimeError(
                f"scale_staging: 请求 {n_blocks} 超过预分配 {self._mlu_scale_staging.shape[0]}")
        return self._mlu_scale_staging[:n_blocks]

    # ------------------------------------------------
     # 连接 CPU 池的连续切片 (host 端零 reformat 的关键)
    # ------------------------------------------------------------------
    def _cpu_contig_seg(self, cpu_ids: Sequence[int]) -> tuple[torch.Tensor, torch.Tensor]:
        """返回 (kv_seg, scale_seg), 二者 block ordering 严格一致 (同一连续段)。"""
        if not _is_contiguous_run(cpu_ids):
            raise RuntimeError("主性能路径要求 CPU ids 连续 (allocate 返回连续 [0..n-1])")
        if len(cpu_ids) == 1:
            start, end = cpu_ids[0], cpu_ids[0] + 1
        elif cpu_ids[1] > cpu_ids[0]:
            start, end = cpu_ids[0], cpu_ids[0] + len(cpu_ids)
        else:
            raise RuntimeError("主路径不支持降序 CPU ids")
        return self.cpu_pool.kv_slice(start, end), self.cpu_pool.scale_slice(start, end)

    # ------------------------------------------------------------------
    # device-side pack: MLU native {mlu_ids} -> 连续 V3 staging
    # ------------------------------------------------------------------
    def pack_kv(self, staging: torch.Tensor, mlu_ids: Sequence[int], method: str):
        """MLU native KV {mlu_ids} (2,L,N,H,T,D) -> 连续 V3 KV staging (N,2,L,H,T,D)。"""
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
            raise ValueError(f"pack_kv: 未知 method {method!r}")
            def pack_scale(self, staging: torch.Tensor, mlu_ids: Sequence[int], method: str):
        """MLU native Scale {mlu_ids} (2,L,N,H,T) -> 连续 V3 Scale staging (N,2,L,H,T)。"""
        if method == "slice":
            ss = _contig_slice(mlu_ids)
            src = self.mlu_scales[:, :, slice(ss[0], ss[1], ss[2]), :, :]
            staging.copy_(src.permute(2, 0, 1, 3, 4).contiguous())
        elif method == "A":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            sub = self.mlu_scales[:, :, idx, :, :]  # (2,L,n,H,T) advanced gather
            staging.copy_(sub.permute(2, 0, 1, 3, 4).contiguous())
        elif method == "B":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            sub = self.mlu_scales.index_select(_SBLK, idx)  # (2,L,n,H,T)
            staging.copy_(sub.permute(2, 0, 1, 3, 4).contiguous())
        else:
            raise ValueError(f"pack_scale: 未知 method {method!r}")

    # ------------------------------------------------------------------
    # device-side unpack: 连续 V3 staging -> MLU native {mlu_ids}
    # ------------------------------------------------------------------
    def unpack_kv(self, staging: torch.Tensor, mlu_ids: Sequence[int], method: str):
        """连续 V3 KV staging (N,2,L,H,T,D) -> MLU native KV {mlu_ids} (2,L,N,H,T,D)。"""
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
            raise ValueError(f"unpack_kv: 未知 method {method!r}")

    def unpack_scale(self, staging: torch.Tensor, mlu_ids: Sequence[int], method: str):
        """连续 V3 Scale staging (N,2,L,H,T) -> MLU native Scale {mlu_ids} (2,L,N,H,T)。"""
        tmp = staging.permute(1, 2, 0, 3, 4)  # view (2, L, n, H, T)
        if method == "slice":
            if not _is_contiguous_run(mlu_ids):
                raise ValueError("slice unpack 仅支持连续 mlu_ids")
            ss = _contig_slice(mlu_ids)
            self.mlu_scales[:, :, slice(ss[0], ss[1], ss[2]), :, :].copy_(tmp)
        elif method == "adv_assign":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            self.mlu_scales[:, :, idx, :, :] = tmp
        elif method == "index_copy":
            idx = torch.tensor(mlu_ids, dtype=torch.long, device=self.device)
            self.mlu_scales.index_copy_(
                2, idx, tmp.contiguous() if not tmp.is_contiguous() else tmp)
        elif method == "contig_run":
            for start_idx, run_id, run_len in _contiguous_runs(mlu_ids):
                seg = tmp[:, :, start_idx: start_idx + run_len, :, :]
                self.mlu_scales[:, :, run_id: run_id + run_len, :, :].copy_(seg)
        else:
            raise ValueError(f"unpack_scale: 未知 method {method!r}")

    # ------------------------------------------------------------------
    # STORE: MLU -> CPU (D2H)  —— KV + Scale 一起, 原子逻辑
    # ------------------------------------------------------------------
    def store(self, mlu_block_ids, cpu_block_ids, pack_method="A", producer_event=None):
        """同步 Store: MLU native KV+Scale {mlu_ids} -> CPU V3 {cpu_ids}。

        整个 logical block operation 视为原子: KV 与 Scale 都成功才 READY。
        任一失败抛异常 (本阶段独立 PoC 直接报错, §九)。

        P0 Stream Dependency Hardening: 若提供 producer_event (KV/Scale 生产者流上
        record 的 Event), transfer_stream.wait_event 保证 pack 读 source 在生产者写
        完成之后 (跨流依赖, 不阻塞 host)。None = 当前行为 (调用方已保证 source ready)。
        """
        n = len(mlu_block_ids)
        if n != len(cpu_block_ids):
            raise ValueError(f"store: len(mlu)={n} != len(cpu)={len(cpu_block_ids)}")
        if n == 0:
            return
        with torch.mlu.stream(self.transfer_stream):
            if producer_event is not None:
                self.transfer_stream.wait_event(producer_event)
            kv_stg = self.kv_staging(n)
            sc_stg = self.scale_staging(n)
            self.pack_kv(kv_stg, mlu_block_ids, pack_method)
            self.pack_scale(sc_stg, mlu_block_ids, pack_method)
            kv_seg, sc_seg = self._cpu_contig_seg(cpu_block_ids)
            kv_seg.copy_(kv_stg, non_blocking=True)    # D2H KV
            sc_seg.copy_(sc_stg, non_blocking=True)    # D2H Scale
        self.transfer_stream.synchronize()
        def store_timed(self, mlu_block_ids, cpu_block_ids, pack_method="A"):
        """返回 dict: pack_kv_ms, pack_scale_ms, d2h_kv_ms, d2h_scale_ms, total_store_ms。

        计时用 device Event (跨 stream), wall 用 perf_counter。
        event 顺序: e0 pack_kv start, e1 pack_kv end/pack_scale start,
                   e2 pack_scale end, e3 d2h_kv start, e4 d2h_kv end/d2h_scale start,
                   e5 d2h_scale end。
        """
        n = len(mlu_block_ids)
        t0 = _now()
        with torch.mlu.stream(self.transfer_stream):
            kv_stg = self.kv_staging(n)
            sc_stg = self.scale_staging(n)
            self._ev[0].record()
            self.pack_kv(kv_stg, mlu_block_ids, pack_method)
            self._ev[1].record()
            self.pack_scale(sc_stg, mlu_block_ids, pack_method)
            self._ev[2].record()
            kv_seg, sc_seg = self._cpu_contig_seg(cpu_block_ids)
            kv_seg.copy_(kv_stg, non_blocking=True)
            self._ev[3].record()
            sc_seg.copy_(sc_stg, non_blocking=True)
            self._ev[4].record()
        self.transfer_stream.synchronize()
        wall = (_now() - t0) * 1000
        return {
            "pack_kv_ms": self._ev[0].elapsed_time(self._ev[1]),
            "pack_scale_ms": self._ev[1].elapsed_time(self._ev[2]),
            "d2h_kv_ms": self._ev[2].elapsed_time(self._ev[3]),
            "d2h_scale_ms": self._ev[3].elapsed_time(self._ev[4]),
            "total_store_ms": wall,
        }

def load(self, cpu_block_ids, mlu_block_ids, unpack_method="adv_assign"):
        """同步 Load: CPU V3 {cpu_ids} -> MLU native KV+Scale {mlu_ids}。

        同一个 target_mlu_block_id 必须同时接收正确 KV + Scale (§七)。
        任一失败抛异常 (本阶段独立 PoC 直接报错, §九)。
        """
        n = len(cpu_block_ids)
        if n != len(mlu_block_ids):
            raise ValueError(f"load: len(cpu)={n} != len(mlu)={len(mlu_block_ids)}")
        if n == 0:
            return
        kv_seg, sc_seg = self._cpu_contig_seg(cpu_block_ids)
        with torch.mlu.stream(self.transfer_stream):
            kv_stg = self.kv_staging(n)
            sc_stg = self.scale_staging(n)
            kv_stg.copy_(kv_seg, non_blocking=True)    # H2D KV
            sc_stg.copy_(sc_seg, non_blocking=True)    # H2D Scale
            self.unpack_kv(kv_stg, list(mlu_block_ids), unpack_method)
            self.unpack_scale(sc_stg, list(mlu_block_ids), unpack_method)
        self.transfer_stream.synchronize()

    def load_timed(self, cpu_block_ids, mlu_block_ids, unpack_method):
        """返回 dict: h2d_kv_ms, h2d_scale_ms, unpack_kv_ms, unpack_scale_ms, total_load_ms。"""
        n = len(cpu_block_ids)
        kv_seg, sc_seg = self._cpu_contig_seg(cpu_block_ids)
        t0 = _now()
        with torch.mlu.stream(self.transfer_stream):
            kv_stg = self.kv_staging(n)
            sc_stg = self.scale_staging(n)
            self._ev[5].record()
            kv_stg.copy_(kv_seg, non_blocking=True)    # H2D KV
            self._ev[6].record()
            sc_stg.copy_(sc_seg, non_blocking=True)    # H2D Scale
            self._ev[7].record()
            self.unpack_kv(kv_stg, list(mlu_block_ids), unpack_method)
            self._ev[8].record()
            self.unpack_scale(sc_stg, list(mlu_block_ids), unpack_method)
            self._ev[9].record()
        self.transfer_stream.synchronize()
        wall = (_now() - t0) * 1000
        return {
            "h2d_kv_ms": self._ev[5].elapsed_time(self._ev[6]),
            "h2d_scale_ms": self._ev[6].elapsed_time(self._ev[7]),
            "unpack_kv_ms": self._ev[7].elapsed_time(self._ev[8]),
            "unpack_scale_ms": self._ev[8].elapsed_time(self._ev[9]),
            "total_load_ms": wall,
        }

    # ==================================================================
    # Async Store: 同步 pack (KV+Scale) + 异步 D2H (KV+Scale) + 单 Event
    # 镜像 KVBlockMoverV2.pack_to_staging / submit_d2h, 但对象是 KV+Scale 两个张量,
    # 二者 block ordering 严格一致 (同一组 mlu_block_ids, 同一 pack 顺序), 共用同一 Event。
    # §十二: KV 与 Scale 的 D2H 在同一 transfer_stream 顺序执行, 末尾单 ev.record() 覆盖两者。
    # ==================================================================
    def pack_to_staging(self, staging_kv, staging_scale, mlu_block_ids,
                        pack_method="A", producer_event=None):
        """同步 pack: 把 MLU native KV+Scale {mlu_block_ids} pack 进给定 staging。

        在 pack_stream 上执行 KV pack + Scale pack, 返回时两者均已完成
        (pack_stream.synchronize), 保证原 source MLU physical blocks 可安全释放/覆盖 (§八/§十二)。
        staging_kv / staging_scale 必须是调用方独占的 slot tensor (AsyncStoreStagingPool bundle)。
        二者 block ordering 严格一致 (同一组 mlu_block_ids, 同一 pack 顺序)。

        P0 Stream Dependency Hardening: 若提供 producer_event (在 KV/Scale 生产者流
        —— 通常是 default/compute stream —— 上 record 的 Event), pack_stream.wait_event
        保证 pack 读 source MLU blocks 在生产者写完成之后 (跨流依赖, 不阻塞 host, 不需要
        device-wide torch.mlu.synchronize())。producer_event 必须记录在最后一次会修改即将
        offload 的 KV/Scale 写之后 (§五)。None = 当前行为 (调用方已保证 source ready)。
        """
        with torch.mlu.stream(self.pack_stream):
            if producer_event is not None:
                self.pack_stream.wait_event(producer_event)
            self.pack_kv(staging_kv, mlu_block_ids, pack_method)
            self.pack_scale(staging_scale, mlu_block_ids, pack_method)
        self.pack_stream.synchronize()

    def submit_d2h(self, staging_kv, staging_scale, cpu_block_ids,
                   pack_event=None):
        """在 transfer_stream 上发起 staging(KV+Scale) -> CPU 最终池 的 non_blocking D2H, 返回 Event。

        §十二: KV 与 Scale 的 D2H 在同一 transfer_stream 顺序执行, 末尾单 ev.record() 覆盖两者
        (同 stream 顺序执行, 一个 Event 足够; flush 等 Event = KV+Scale D2H 都完成)。
        若提供 pack_event (pack_stream 上 record 的 Event), transfer_stream.wait_event
        保证 D2H 在 pack 之后 (跨流依赖, 不阻塞 host)。
        返回 record 在两次 D2H 之后的 Event, 调用方 poll event.query() 判断完成 (non-blocking)。
        """
        with torch.mlu.stream(self.transfer_stream):
            if pack_event is not None:
                self.transfer_stream.wait_event(pack_event)
            kv_seg, sc_seg = self._cpu_contig_seg(cpu_block_ids)
            kv_seg.copy_(staging_kv, non_blocking=True)    # D2H KV
            sc_seg.copy_(staging_scale, non_blocking=True)  # D2H Scale
            ev = torch.mlu.Event(enable_timing=True)
            ev.record()
        return ev

def submit_load_async(self, staging_kv, staging_scale, cpu_block_ids,
                          mlu_block_ids, unpack_method="contig_run"):
        """在 transfer_stream 上发起 CPU -> MLU 的 non_blocking H2D(KV+Scale) + device unpack(KV+Scale),
        record Event AFTER Scale unpack 完成, 返回 Event (§十四)。

        关键 (§七/§十四): 同一 target_mlu_block_id 必须同时接收正确 KV + Scale。
        Event 必须记录在最终 Scale unpack 之后 (而非仅 H2D 后或 unpack_kv 后) —— 否则 commit 时
        MLU KV/Scale 尚未 scatter 到 native layout, forward 会读到未初始化数据。

        staging_kv / staging_scale 必须是调用方独占的 load slot bundle tensor,
        shape (n, 2, L, H, T, D) / (n, 2, L, H, T)。cpu_block_ids 按 split_contiguous_runs
        分段 H2D (eviction 后 CPU ids 可能非连续); 同一段内 KV 与 Scale 用同一 cpu-run。

        返回: torch.mlu.Event (record 在 Scale unpack 之后, 调用方 poll event.query())。
        本方法不 synchronize (异步返回); 调用方在 Event complete 前不得 forward 该 seq,
        不得复用 staging bundle slot, 不得 eviction source CPU blocks (由 refcount 保护)。
        """
        with torch.mlu.stream(self.transfer_stream):
            # 按连续 cpu-run 分段 H2D (cpu ids 未必连续), KV 与 Scale 用同一 run
            runs = _contiguous_runs(cpu_block_ids)
            for start_idx, run_cpu_id, run_len in runs:
                seg_cpu = list(range(run_cpu_id, run_cpu_id + run_len))
                kv_seg, sc_seg = self._cpu_contig_seg(seg_cpu)
                staging_kv[start_idx: start_idx + run_len].copy_(kv_seg, non_blocking=True)
                staging_scale[start_idx: start_idx + run_len].copy_(sc_seg, non_blocking=True)
            # device unpack: staging -> MLU native {mlu_block_ids} (同 stream, 顺序依赖 H2D)
            self.unpack_kv(staging_kv, list(mlu_block_ids), unpack_method)
            self.unpack_scale(staging_scale, list(mlu_block_ids), unpack_method)
            # Event 必须在 Scale unpack 之后 (§十四)
            ev = torch.mlu.Event(enable_timing=True)
            ev.record()
        return ev

    def __repr__(self) -> str:
        return (
            f"QuantizedKVBlockMover(kv={tuple(self.mlu_kv.shape)} "
            f"scale={tuple(self.mlu_scales.shape)} on {self.device}, "
            f"pool={self.cpu_pool!r}, "
            f"kv_staging={tuple(self._mlu_kv_staging.shape)}, "
            f"scale_staging={tuple(self._mlu_scale_staging.shape)})"
        )


def _now():
    import time
    return time.perf_counter()

