"""KV cache int8 量化 —— 推理 patch。

本模块实现优化4: 把 KV cache 从 bf16 量化成 int8 + per-token scale,
减少 KV cache 显存占用 (bf16 2byte -> int8 1byte, 省 50%)。

设计原则 (与优化1/2/3 一致):
  - 原版 nanovllm/layers/attention.py、attention_mlu.py、engine/model_runner.py 一行不动
  - 通过 monkey-patch 在运行时注入, 便于 A/B 对比和随时回退
  - MLU 路径用 int8 KV cache, CUDA 路径 fallback 到原 bf16

量化方案: KV cache int8 per-token 量化 (动态, 每写一个 token 量化一次)
  - 写入: ops.quant_to_paged_cache(k, v, k_cache, v_cache, k_scale, v_scale, slot_mapping)
          算子内部自动算 per-token scale = max(|k|)/127, 存 int8 + scale
  - 读取(decode): ops.single_query_cached_kv_attn(..., k_scale, v_scale, kv_cache_quant_bit_size=8)
          算子内部用 scale 反量化
  - 读取(prefill prefix-cache): flash_attention 不支持读 int8 cache, 需先反量化成 bf16

为什么 KV cache 量化 (对比权重量化):
  - 权重量化(优化3): 作用于占 68% 的 GEMM -> 直接降 TPOT (降延迟)
  - KV cache 量化(优化4): 作用于占 ~5% 的 attention -> 对 TPOT 影响小,
    主要价值是省 KV 显存 -> 能开更大 batch / 更长上下文 (升吞吐)
  - 两者作用在不同地方, 不矛盾, 可叠加

关键约束:
  - flash_attention 的 prefix-cache 路径不支持读 int8 cache (要求 q/k dtype 一致),
    需先反量化成 bf16 再传入 (见 prefill_attention 的 block_tables 分支)
  - 普通 prefill (block_tables=None) 用新算出的 bf16 k/v, 不读 cache, 不受影响
  - decode 用 single_query_cached_kv_attn 读 int8 cache, 是主要受益路径
"""
import torch
import numpy as np
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_torch_mlu_ops():
    try:
        import torch_mlu_ops
    except ImportError as exc:
        raise RuntimeError(
            "KV cache 量化需要 torch_mlu_ops。请在寒武纪 SDK 容器内安装 Nano-vLLM 的 mlu 可选依赖。"
        ) from exc
    return torch_mlu_ops


def _is_mlu(tensor: torch.Tensor) -> bool:
    return tensor is not None and tensor.device.type == "mlu"


# ---------------------------------------------------------------------------
# 量化后的 store_kvcache: reshape_paged_cache(bf16) -> quant_to_paged_cache(int8)
# ---------------------------------------------------------------------------
def _patched_store_kvcache(key, value, k_cache, v_cache, slot_mapping,
                           k_scale=None, v_scale=None):
    """把新算出的 k/v 量化成 int8 写入 paged cache, 同时存 per-token scale。

    替换原 ops.reshape_paged_cache(bf16 直写) 为 ops.quant_to_paged_cache(int8 + scale)。
    k_scale/v_scale 由 Attention 层持有 (model_runner 分配), 传入这里。
    """
    ops = _get_torch_mlu_ops()
    if k_cache.dtype == torch.int8 and k_scale is not None:
        ops.quant_to_paged_cache(
            key.contiguous(),
            value.contiguous(),
            k_cache,
            v_cache,
            k_scale,
            v_scale,
            slot_mapping.flatten(),
        )
    else:
        # fallback: bf16 cache (CUDA 或未量化)
        ops.reshape_paged_cache(
            key.contiguous(),
            value.contiguous(),
            k_cache,
            v_cache,
            slot_mapping.flatten(),
        )


# ---------------------------------------------------------------------------
# 量化后的 decode_attention: 传 k_scale/v_scale + kv_cache_quant_bit_size=8
# ---------------------------------------------------------------------------
def _patched_decode_attention(q, k_cache, v_cache, *,
                              context_lens, block_tables, max_seqlen_k, scale,
                              k_scale=None, v_scale=None):
    """decode 从 int8 cache 读取 attention, 传 scale + quant_bit_size=8。"""
    ops = _get_torch_mlu_ops()
    batch_size = q.shape[0]
    query = q.contiguous().view(batch_size, 1, q.shape[1], q.shape[2])
    output = torch.empty_like(query)
    if k_cache.dtype == torch.int8 and k_scale is not None:
        ops.single_query_cached_kv_attn(
            query, k_cache, v_cache, output,
            block_tables, context_lens,
            k_scale, v_scale,        # K/V cache 量化 scale
            None,                    # alibi slopes
            max_seqlen_k, -1, -1, scale, False,
            kv_cache_quant_bit_size=8,
            head_size_v=-1, compute_dtype=torch.float32,
        )
    else:
        # fallback: bf16 cache
        ops.single_query_cached_kv_attn(
            query, k_cache, v_cache, output,
            block_tables, context_lens,
            None, None, None,
            max_seqlen_k, -1, -1, scale, False,
            head_size_v=-1, compute_dtype=torch.float32,
        )
    return output.view_as(q)


# ---------------------------------------------------------------------------
# 量化后的 prefill_attention: 普通 prefill 不读 cache; prefix-cache 需反量化
# ---------------------------------------------------------------------------
def _dequant_int8_cache(int8_cache, scale):
    """int8 paged cache (blocks, kv, bs, hd) 反量化成 bf16, 供 flash_attention 用。

    cache_layout: (num_blocks, num_kv_heads, block_size, head_dim)
    scale:        (num_blocks, num_kv_heads, block_size) -> unsqueeze(-1)
    """
    return (int8_cache.to(torch.float32) * scale.unsqueeze(-1)).to(torch.bfloat16)

# ---------------------------------------------------------------------------
# block_tables -> (used_ids, new_block_tables) 映射, 一次 forward 只算一次
# ---------------------------------------------------------------------------
# 修复 TTFT 劣化: 原版每层 prefill 都调 _dequant_used_blocks, 里面用 MLU 的
# unique + searchsorted (各 ~0.3ms launch 开销), 36 层 × 2(k/v) = 72 次 ≈ 52ms,
# 在 batch>=2 时 prefill 计算量增大、launch 开销串行化, 导致 TTFT +52ms。
# 修复: (1) unique/searchsorted 移到 CPU (numpy), 比 MLU 小算子快 4.4x;
#       (2) 一次 forward 的 block_tables 对所有层相同, 只算一次并缓存, 72 次 -> 1 次。
#
# 生命周期修正 (本阶段):
#   旧实现用模块级全局 dict + (data_ptr, shape) 做 key, 存在 stale 风险:
#   block_tables 张量可能 data_ptr 不变、shape 不变, 但内容被原地改写,
#   此时旧 key 仍命中 -> 返回基于旧内容的 mapping (stale bug)。
#   新实现把映射结果挂到 context.kv_quant_block_map:
#     - set_context() 每次 forward 创建新 Context -> kv_quant_block_map=None,
#       天然按 forward 失效, 不存在跨 forward / data_ptr 复用的 stale 风险。
#     - 同一 forward 内 36 层 × 2(k/v) = 72 次调用复用同一映射, 只算一次。
#   计数器 block_map_compute_count 用于验证 "每 forward 只算一次"。
block_map_compute_count = 0  # 全局累计: _compute_block_map 真正计算 (非命中) 的次数


def _compute_block_map(block_tables):
    """算 block_tables 的 (used_ids, new_block_tables), CPU 侧 unique+searchsorted。
    返回 MLU tensor: used_ids (num_used,) int32, new_block_tables (batch, max_blocks) int32。
    结果按 forward 级缓存 (context.kv_quant_block_map): 同一次 forward 的所有层
    复用 (72 次 -> 1 次计算); 下一次 forward (新 context) 自动重新计算。

    缓存 key 用 block_tables 的 data_ptr 做一致性校验: 若 context 内 block_tables
    被原地改写 (data_ptr 不变但内容变), 由于 key 仍是同一张量, 仍会命中旧映射 ——
    因此本函数额外用 (data_ptr, shape, 内容 hash) 做校验, 内容变化即失效重算。
    """
    global block_map_compute_count
    from nanovllm.utils.context import get_context
    context = get_context()
    # 内容指纹: data_ptr + shape + 少量采样点。data_ptr/shape 不变但内容变时, 采样点
    # 变化 -> 失效重算, 修复 stale bug。采样开销 O(1), 远小于一次 unique/searchsorted。
    bt_cpu = block_tables.cpu().numpy()
    # 内容指纹: 取首尾若干元素 + 非负元素个数 (内容变了指纹几乎必变)
    flat = bt_cpu.ravel()
    n = flat.size
    if n > 0:
        sample = (int(flat[0]), int(flat[-1]), int((flat >= 0).sum()))
    else:
        sample = (0, 0, 0)
    fingerprint = (block_tables.data_ptr(), tuple(block_tables.shape), sample)

    cached = context.kv_quant_block_map
    if cached is not None and cached[0] == fingerprint:
        return cached[1], cached[2]

    # CPU 侧算 unique + searchsorted (避免 MLU 小算子 launch 开销)
    used = np.unique(bt_cpu[bt_cpu >= 0]).astype(np.int32)  # 排序去重
    new_bt_cpu = bt_cpu.copy()
    mask = new_bt_cpu >= 0
    new_bt_cpu[mask] = np.searchsorted(used, new_bt_cpu[mask]).astype(np.int32)
    used_ids_mlu = torch.from_numpy(used).to(block_tables.device)
    new_bt_mlu = torch.from_numpy(new_bt_cpu).to(block_tables.device)
    context.kv_quant_block_map = (fingerprint, used_ids_mlu, new_bt_mlu)
    block_map_compute_count += 1
    return used_ids_mlu, new_bt_mlu

def _dequant_used_blocks(int8_cache, scale, block_tables):
    """只反量化 block_tables 引用到的 block, 组成紧凑 bf16 cache, 并重映射 block_tables。

    避免反量化整个 int8 cache (45GB -> 90GB 会 OOM)。prefix-cache prefill 是罕见路径,
    只需反量化实际用到的 block (通常几十个)。

    优化: used_ids/new_block_tables 用 _compute_block_map 算并缓存 (一次 prefill 只算一次),
          所有层复用, 消除 72 次 unique/searchsorted 的 MLU launch 开销。

    Args:
        int8_cache: (num_blocks, num_kv_heads, block_size, head_dim) int8
        scale:      (num_blocks, num_kv_heads, block_size) fp32
        block_tables: (batch, max_blocks) int32, 值为原 block id (-1 为 padding)

    Returns:
        compact_bf16: (num_used, num_kv_heads, block_size, head_dim) bf16
        new_block_tables: (batch, max_blocks) int32, 值重映射到紧凑 cache 的索引
    """
    used_ids, new_block_tables = _compute_block_map(block_tables)
    # 反量化 used block: int8[used] * scale[used].unsqueeze(-1)
    compact = (int8_cache.index_select(0, used_ids).float()
               * scale.index_select(0, used_ids).unsqueeze(-1)).to(torch.bfloat16)
    return compact, new_block_tables


def _patched_prefill_attention(q, k, v, *,
                              cu_seqlens_q, cu_seqlens_k, max_seqlen_q, max_seqlen_k,
                              scale, block_tables,
                              k_scale=None, v_scale=None):
    """prefill attention。
    - block_tables=None (普通 prefill): k/v 是新算出的 bf16, 不读 cache, 走原 flash_attention。
    - block_tables!=None (prefix-cache): k/v 是 int8 paged cache, 只反量化引用到的 block
      成紧凑 bf16 cache, 重映射 block_tables 后传入 flash_attention (避免反量化整个 cache)。
    """
    ops = _get_torch_mlu_ops()
    q = q.contiguous()
    if block_tables is not None and k.dtype == torch.int8 and k_scale is not None:
        # prefix-cache 路径: 只反量化用到的 block, 重映射 block_tables (k 和 v 用同一映射)
        k_compact, new_bt = _dequant_used_blocks(k, k_scale, block_tables)
        v_compact, _ = _dequant_used_blocks(v, v_scale, block_tables)
        k, v, block_tables = k_compact, v_compact, new_bt
    if block_tables is None:
        k = k.contiguous()
        v = v.contiguous()
    output = torch.empty_like(q)
    ops.flash_attention(
        q, k, v, output,
        cu_seqlens_q, cu_seqlens_k,
        None, None,               # alibi, attn_bias
        max_seqlen_q, max_seqlen_k, scale, True, -1, -1,
        torch.float32, False,     # compute_dtype, return_lse
        block_tables,
        None, None, None, None,   # k/v/q/out quant scale (bf16 路径)
        q.dtype,
    )
    return output


# ---------------------------------------------------------------------------
# 量化后的 Attention.forward: 把 k_scale/v_scale 传给 store/decode/prefill
# ---------------------------------------------------------------------------
_original_attention_forward = None


def _patched_attention_forward(self, q, k, v):
    """替换 Attention.forward, 把 self.k_scale/v_scale 传给量化版 attention ops。"""
    from nanovllm.utils.context import get_context
    context = get_context()
    # 选择量化版 ops (MLU) 或原版 ops (CUDA fallback)
    if _is_mlu(q):
         k_cache, v_cache = self.k_cache, self.v_cache
        k_scale, v_scale = getattr(self, "k_scale", None), getattr(self, "v_scale", None)
        if k_cache.numel() and v_cache.numel():
            _patched_store_kvcache(k, v, k_cache, v_cache, context.slot_mapping,
                                   k_scale, v_scale)
        if context.is_prefill:
            if context.block_tables is not None:  # prefix cache
                k, v = k_cache, v_cache
            return _patched_prefill_attention(
                q, k, v,
                cu_seqlens_q=context.cu_seqlens_q,
                cu_seqlens_k=context.cu_seqlens_k,
                max_seqlen_q=context.max_seqlen_q,
                max_seqlen_k=context.max_seqlen_k,
                scale=self.scale,
                block_tables=context.block_tables,
                k_scale=k_scale, v_scale=v_scale,
            )
        return _patched_decode_attention(
            q, k_cache, v_cache,
            context_lens=context.context_lens,
            block_tables=context.block_tables,
            max_seqlen_k=context.max_seqlen_k,
            scale=self.scale,
            k_scale=k_scale, v_scale=v_scale,
        )
    # CUDA 路径: 调用原 Attention.forward
    return _original_attention_forward(self, q, k, v)


# ---------------------------------------------------------------------------
# 量化后的 allocate_kv_cache: 分配 int8 cache + scale, 挂到各 attention 层
# ---------------------------------------------------------------------------
_original_allocate_kv_cache = None
def _patched_allocate_kv_cache(self):
    """替换 ModelRunner.allocate_kv_cache, 分配 int8 KV cache + per-token scale。

    与原版区别:
      - kv_cache dtype: bf16 -> int8 (省 ~50% 显存)
      - 新增 k_scale/v_scale: (num_blocks, num_kv_heads, block_size) fp32
      - 把 k_scale/v_scale 挂到每个 Attention 层 (与 k_cache/v_cache 同层)

    容量预算修正:
      原版只按 int8 KV 本体 (itemsize=1) 算 block_bytes, 漏掉 FP32 scale,
      导致 "容量严格 2.00x" 不严谨 (实际 scale 还要额外占显存)。
      修正: block_bytes = int8_kv_bytes + scale_bytes, scale 纳入预算。
      理论 capacity_ratio = bf16_block / int8_total_block ≈ 1.94x (非 2.00x)。
    """
    config = self.config
    hf_config = config.hf_config
    free, total = self.platform.mem_get_info()
    used = total - free
    memory_stats = self.platform.memory_stats()
    peak = memory_stats.get("allocated_bytes.all.peak", 0)
    current = memory_stats.get("allocated_bytes.all.current", 0)
    num_kv_heads = hf_config.num_key_value_heads // self.world_size
    head_dim = getattr(hf_config, "head_dim", hf_config.hidden_size // hf_config.num_attention_heads)
    num_layers = hf_config.num_hidden_layers
    # int8 KV 本体: itemsize=1 (原 bf16=2)
    int8_kv_bytes = 2 * num_layers * self.block_size * num_kv_heads * head_dim * 1
    # FP32 per-token scale: (2, L, blocks, H, T) -> 每 block 2*L*H*T*4 bytes
    scale_bytes = 2 * num_layers * self.block_size * num_kv_heads * 4
    # 修正: scale 纳入 block_bytes 预算 (不再只按 int8 本体)
    block_bytes = int8_kv_bytes + scale_bytes
    config.num_kvcache_blocks = int(total * config.gpu_memory_utilization - used - peak + current) // block_bytes
    assert config.num_kvcache_blocks > 0
    from nanovllm.platform import kv_cache_shape
    cache_shape = kv_cache_shape(
        self.platform.type,
        num_layers,
        config.num_kvcache_blocks,
        self.block_size,
        num_kv_heads,
        head_dim,
    )
    # int8 KV cache
    self.kv_cache = torch.empty(
        cache_shape,
        dtype=torch.int8,            # ← 关键: bf16 -> int8
        device=self.device,
    )
    # per-token scale: (num_blocks, num_kv_heads, block_size) per layer
    scale_shape = (config.num_kvcache_blocks, num_kv_heads, self.block_size)
    # 为每层分配独立的 scale (与 kv_cache 的 layer 维度对应)
    self.kv_scales = torch.empty(
        (2, num_layers, *scale_shape),
        dtype=torch.float32,
        device=self.device,
    )
    # 容量预算日志 (修正后)
    bf16_block_bytes = 2 * num_layers * self.block_size * num_kv_heads * head_dim * hf_config.dtype.itemsize
    print(f"[KV cache int8 预算] bf16_block={bf16_block_bytes/1024**2:.4f} MiB "
          f"int8_kv={int8_kv_bytes/1024**2:.4f} MiB scale={scale_bytes/1024**2:.4f} MiB "
          f"int8_total_block={block_bytes/1024**2:.4f} MiB "
          f"scale_overhead={scale_bytes/block_bytes:.2%} "
          f"capacity_ratio={bf16_block_bytes/block_bytes:.4f}x",
          flush=True)
    print(f"[KV cache int8 预算] num_blocks={config.num_kvcache_blocks} "
          f"kv_cache={self.kv_cache.numel()*self.kv_cache.element_size()/1024**3:.3f} GB "
          f"scale={self.kv_scales.numel()*self.kv_scales.element_size()/1024**3:.3f} GB "
          f"total={(self.kv_cache.numel()*self.kv_cache.element_size()+self.kv_scales.numel()*self.kv_scales.element_size())/1024**3:.3f} GB "
          f"capacity={config.num_kvcache_blocks*self.block_size} tokens",
          flush=True)
    layer_id = 0
    for module in self.model.modules():
        if hasattr(module, "k_cache") and hasattr(module, "v_cache"):
            module.k_cache = self.kv_cache[0, layer_id]
            module.v_cache = self.kv_cache[1, layer_id]
            module.k_scale = self.kv_scales[0, layer_id]   # ← 挂 scale
            module.v_scale = self.kv_scales[1, layer_id]
            layer_id += 1

def apply_kvcache_quant_patch():
    """注入 KV cache int8 量化到 nanovllm。

    必须在 import nanovllm 之后、构建 LLM 之前调用。
    patch 三个地方:
      1. Attention.forward: 传 k_scale/v_scale 给量化版 ops
      2. ModelRunner.allocate_kv_cache: 分配 int8 cache + scale, 挂到各层
    (store/decode/prefill attention 用本模块的量化版函数, 通过 Attention.forward 调用)

    原版 attention.py / attention_mlu.py / model_runner.py 一行不改。
    """
    global _original_attention_forward, _original_allocate_kv_cache
    from nanovllm.layers.attention import Attention
    from nanovllm.engine.model_runner import ModelRunner

    # 幂等保护: 避免重复 patch (多次调用时 _original_* 会指向已 patch 版本)
    if getattr(Attention.forward, "_kvcache_patched", False):
        return Attention

    _original_attention_forward = Attention.forward
    _original_allocate_kv_cache = ModelRunner.allocate_kv_cache

    _patched_attention_forward._kvcache_patched = True  # 标记已 patch
    Attention.forward = _patched_attention_forward
    ModelRunner.allocate_kv_cache = _patched_allocate_kv_cache
    print("[已注入 KV cache int8 量化 patch]", flush=True)
    return Attention

