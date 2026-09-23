#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CPUPrefixIndex —— CPU Prefix KV Cache 的 block-hash -> cpu_block_id 索引 + LRU。

与 nanoLLM `BlockManager.hash_to_block_id` 同语义 (key=xxh64 chained block hash,
value=cpu block id), 但面向 CPU KV Pool (V2 Block-Major)。

第六步新增: block-level LRU (OrderedDict 实现)。

LRU 顺序约定 (§七/八):
  - 内部用 OrderedDict[block_hash, cpu_block_id]。
  - **LRU 端 = first (iter 头)**: 最久未被 CPU Prefix Lookup HIT 使用的 block。
  - **MRU 端 = last (iter 尾)**: 最近真正被 CPU Prefix Lookup HIT 使用的 block。
  - 新 insert 的 block 追加到 MRU 端 (last) —— 刚写入视为最近活跃 (§十九: Store A B C D
    => A 最老/LRU, D 最新/MRU)。
  - CPU Lookup HIT (match_prefix 命中) => move_to_end (touch, 移到 MRU)。
  - Duplicate Store **不 touch** (§九): insert 已存在 hash 时不改变顺序。
  - victim 选择 = LRU 端 first (pop_lru)。

设计约束:
  - 复用 nanoLLM 现有 `BlockManager.compute_hash` (xxhash 链式), 不另设计 hash。
  - 一个 hash 唯一对应一个 CPU block (shared prefix 只存一份)。
  - duplicate insert 不 silent 覆盖: 返回 (False, 已存在 cpu_id), 调用方须释放新占的 CPU block。
  - lookup O(1), touch O(1), victim 选择 O(1), remove O(1) (OrderedDict 保证)。

Longest Contiguous Prefix Lookup (§十四):
  match_prefix(block_hashes) 顺序扫描, 遇第一个 MISS 立即停止, 不 sparse hit。
  **只有真正命中的 block 才 touch**; MISS 及其后的 block 不 touch (即使后续存在)。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Sequence, Optional


class CPUPrefixIndex:
    """block-hash -> cpu_block_id 索引 + longest contiguous prefix 查找 + block-level LRU。
LRU 端 = OrderedDict first (最旧); MRU 端 = last (最新)。
    """

    def __init__(self):
        # OrderedDict: first=LRU(最久未用), last=MRU(最近 HIT/insert)
        self._table: "OrderedDict[int, int]" = OrderedDict()
        # 第八步 Async Load: CPU block refcount / protection (§六/§八)。
        # _ref[cpu_block_id] = in-flight async load consumer 数。ref>0 的 READY entry
        # 不可被 LRU eviction (protected)。只有 ref==0 的 READY entry 可淘汰。
        # 语义与 LRU touch 分离 (§二十): touch=访问热度, ref_count=in-flight consumer。
        self._ref: dict[int, int] = {}

    # ------------------------------------------------------------------
    # 基本 CRUD
    # ------------------------------------------------------------------
    def insert(self, block_hash: int, cpu_block_id: int):
        """插入 hash->cpu 映射。

        若 hash 已存在: **不覆盖、不 touch** (§九 duplicate store 不改变 LRU 顺序),
          返回 (False, 已存在的 cpu_block_id)。调用方须释放自己刚申请但未用的新 cpu block。
        否则: 插入到 MRU 端 (last), 返回 (True, cpu_block_id)。
        """
        if block_hash in self._table:
            # duplicate: 不 move_to_end (§九)
            return (False, self._table[block_hash])
        self._table[block_hash] = cpu_block_id  # OrderedDict 新 key 追加到 last (MRU)
        return (True, cpu_block_id)

    def lookup(self, block_hash: int) -> int:
        """返回对应 cpu_block_id; 不存在返回 None。不 touch (纯查询, 非 HIT 路径)。"""
        return self._table.get(block_hash)

    def contains(self, block_hash: int) -> bool:
        return block_hash in self._table

    def update(self, block_hash: int, cpu_block_id: int):
        """无条件写映射 (clear 后重建等确定性路径用)。

        已存在则更新 value 但**不 touch**(保持原 LRU 位置); 新 key 追加到 MRU 端。
        """
        if block_hash in self._table:
            self._table[block_hash] = cpu_block_id  # 原地更新, 不改顺序
        else:
            self._table[block_hash] = cpu_block_id  # 新 key -> last


def touch(self, block_hash: int) -> bool:
        """把 hash 移到 MRU 端 (last)。不存在返回 False。供 CPU Lookup HIT 路径调用。"""
        if block_hash not in self._table:
            return False
        self._table.move_to_end(block_hash)  # 移到 last (MRU)
        return True

    def remove(self, block_hash: int):
        """删除一个 hash。存在返回其 cpu_block_id; 不存在返回 None。不 touch。"""
        return self._table.pop(block_hash, None)

    def clear(self):
        """清空索引, 返回全部已索引 cpu_block_id (供 CPUKVPoolV2.free 归还)。

        第八步: 同时清空 ref_count (clear 前调用方应已 flush 全部 pending load,
        保证无 in-flight consumer; 若仍有 ref>0, 视为已无意义, 一并清空)。
        """
        block_ids = list(self._table.values())
        self._table.clear()
        self._ref.clear()
        return block_ids

    def __len__(self):
        return len(self._table)

    def __contains__(self, block_hash):
        return block_hash in self._table

    # ------------------------------------------------------------------
    # LRU victim (§十一/十二)
    # ------------------------------------------------------------------
    def peek_lru(self) -> Optional[int]:
        """返回 LRU 端 (first/最旧) 的 block_hash, 不删除。空则 None。"""
        if not self._table:
            return None
        return next(iter(self._table))  # first key = LRU

    def pop_lru(self) -> Optional[tuple[int, int]]:
        """淘汰 LRU 端 (first): 删除并返回 (block_hash, cpu_block_id)。空则 None。

        调用方须先拿 cpu_block_id 再 cpu_pool.free (§十二: 先删 metadata, 后 free block)。
        本方法只删 metadata; free 由调用方 (PrefixCacheBackend) 做。

        注意: 本方法不检查 ref_count (第六步无 refcount 时的旧路径)。
        Async Load 启用后, eviction 必须用 pop_lru_evictable (跳过 protected entry, §八)。
        """
        if not self._table:
             return None
        victim_hash = next(iter(self._table))
        victim_cpu = self._table.pop(victim_hash)  # 删 first (LRU)
        return (victim_hash, victim_cpu)

    def pop_lru_evictable(self) -> Optional[tuple[int, int]]:
        """淘汰一个 ref_count==0 的 READY entry (§八: 跳过 protected)。

        扫描 LRU 端起, 跳过 ref_count>0 的 protected entry, 删除第一个 ref==0 的,
        返回 (block_hash, cpu_block_id)。无可淘汰 (全 protected 或空) 返回 None。

        Protected entry (in-flight async load 正读) 不得成为 eviction victim (§八)。
        """
        for h in list(self._table.keys()):
            cid = self._table[h]
            if self._ref.get(cid, 0) > 0:
                continue  # protected, 跳过 (§八)
            # 找到 evictable: 删除并返回
            del self._table[h]
            return (h, cid)
        return None

    # ------------------------------------------------------------------
    # CPU Block Refcount / Protection (§六/§八/§九) —— 第八步 Async Load
    # ------------------------------------------------------------------
    def acquire_refs(self, cpu_block_ids) -> None:
        """对给定 CPU blocks 的 ref_count +1 (submit async load 前调用)。

        防止 in-flight async load 期间这些 READY block 被 LRU eviction。
        必须防 ref_count < 0 / double release (§六): 这里只 +1, 由 release_refs 守下界。
        """
        for cid in cpu_block_ids:
            self._ref[cid] = self._ref.get(cid, 0) + 1

    def release_refs(self, cpu_block_ids) -> None:
        """对给定 CPU blocks 的 ref_count -1 (load complete/fail 后调用)。

        必须 ref_count >= 0 (§六): 减到 0 时删除 entry, 不得为负。
        double release 防护: 若 cid 不在 _ref 中 (已归 0), 忽略 (不抛错, 不变负)。
        """
        for cid in cpu_block_ids:
            cur = self._ref.get(cid, 0)
            if cur <= 1:
                # 归 0 (或已不在): 删除 entry, 绝不为负
                self._ref.pop(cid, None)
            else:
                self._ref[cid] = cur - 1

    def ref_count(self, cpu_block_id: int) -> int:
        """返回某 CPU block 的当前 ref_count (诊断/测试用)。"""
        return self._ref.get(cpu_block_id, 0)

    def num_protected(self) -> int:
        """返回 ref_count>0 的 CPU block 数 (诊断/测试用)。"""
        return sum(1 for v in self._ref.values() if v > 0)

    def peak_refcount(self) -> int:
        """返回当前最大 ref_count (诊断/测试用)。"""
        return max(self._ref.values()) if self._ref else 0

    # ------------------------------------------------------------------
    # Longest contiguous prefix lookup (§十四: 只 touch 命中块, MISS 即停)
    # ------------------------------------------------------------------
    def match_prefix(self, block_hashes: Sequence[int]):
        """顺序扫描, 遇第一个 MISS (hash 不在索引) 立即停止。

        每个真正命中的 hash: 加入 matched 并 **touch** (move_to_end → MRU)。
        MISS 后即使后续 hash 存在: 不命中、不 touch (不 sparse hit)。

        返回:
          matched_hashes  : list[int]  命中区块的 hash (顺序)
          matched_cpus    : list[int]  命中区块对应的 cpu_block_id
          matched_blocks  : int        命中 block 数
        """
        matched_hashes: list[int] = []
        matched_cpus: list[int] = []
        for h in block_hashes:
            cid = self._table.get(h)
            if cid is None:
                break  # 第一个 MISS: 停止, 后续不 touch (§十四)
            # HIT: touch (移到 MRU 端)
            self._table.move_to_end(h)
            matched_hashes.append(h)
            matched_cpus.append(cid)
        return matched_hashes, matched_cpus, len(matched_hashes)

    @classmethod
    def split_contiguous_runs(cls, cpu_block_ids: Sequence[int]):
        """把 cpu_block_ids 拆成升序连续段, 返回 [(start_id, run_len), ...]。

        后端 Load 时按连续段逐段 H2D+unpack, host 端零 reformat (§)。
        """
        if not cpu_block_ids:
            return []
        runs = []
        s = cpu_block_ids[0]
        prev = s
        for c in cpu_block_ids[1:]:
            if c == prev + 1:
                prev = c
            else:
                runs.append((s, prev - s + 1))
                s = prev = c
        runs.append((s, prev - s + 1))
        return runs

    # ------------------------------------------------------------------
    def lru_order(self) -> list[int]:
        """诊断用: 返回从 LRU(first) 到 MRU(last) 的 block_hash 顺序。"""
        return list(self._table.keys())

    def __repr__(self):
        return f"CPUPrefixIndex(len={len(self._table)})"