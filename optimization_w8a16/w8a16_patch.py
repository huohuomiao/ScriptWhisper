"""W8A16 权重量化 —— 离线量化 + 推理 patch。

本模块实现优化3 的核心: 把 Linear 层的 bf16 权重离线量化成 int8 + group-wise scale,
推理时用 torch_mlu_ops.scaled_matmul 替换 F.linear, 减少权重读取带宽 (bf16 2byte -> int8 1byte)。

设计原则 (与优化1/优化2 一致):
  - 原版 nanovllm/layers/linear.py、utils/loader.py、engine/model_runner.py 一行不动
  - 通过 monkey-patch 在运行时注入, 便于 A/B 对比和随时回退
  - MLU 路径用 scaled_matmul, CUDA 路径 fallback 到原 F.linear
  - 量化在模型加载完成后、内存中完成 (不写磁盘), 一次性开销

量化方案: W8A16 group-wise RTN (Round-To-Nearest)
  - 权重 int8, 激活 bf16 不量化 (a_scale=None, a_quant_bit_size=-1)
  - group_size=128, 沿 K(输入)维分组: scale shape (N, K//128)
  - RTN: x_int8 = round(x / scale).clamp(-127,127), scale = max(|x|)/127  (per group)

为什么 group-128 而非 per-channel:
  MLU590 scaled_matmul group-wise 量化 group_size 只支持 [64,128,256,512,1024],
  per-channel (K=4096) 不支持。group-128 精度足够 (相对误差 0.66%)。

为什么只量化大 GEMM:
  真机实测 (见 memory): 大 GEMM (gate_up/down) 加速 1.4x, 小 GEMM (o_proj) 反而变慢 0.78x
  (量化开销 > 带宽收益)。所以只量化 gate_up_proj / down_proj / qkv_proj, 跳过 o_proj。
"""
import torch
import torch.nn.functional as F
from functools import lru_cache

# 默认量化配置
DEFAULT_GROUP_SIZE = 128
# 只量化大 GEMM (权重元素多、带宽收益大); 小 GEMM (o_proj) 量化反而变慢, 跳过
# 名称匹配: 对 model.layers.*.mlp.gate_up_proj / mlp.down_proj / self_attn.qkv_proj 生效
DEFAULT_QUANT_TARGETS = ("gate_up_proj", "down_proj", "qkv_proj")

@lru_cache(maxsize=1)
def _get_torch_mlu_ops():
    try:
        import torch_mlu_ops
    except ImportError as exc:
        raise RuntimeError(
            "W8A16 权重量化需要 torch_mlu_ops。请在寒武纪 SDK 容器内安装 Nano-vLLM 的 mlu 可选依赖。"
        ) from exc
    return torch_mlu_ops


def _is_mlu(tensor: torch.Tensor) -> bool:
    return tensor is not None and tensor.device.type == "mlu"


# ---------------------------------------------------------------------------
# 第 2 步: 离线量化 (RTN, group-wise)
# ---------------------------------------------------------------------------
def quantize_weight_rtn(weight: torch.Tensor, group_size: int = DEFAULT_GROUP_SIZE):
    """把 bf16/fp32 权重 (N, K) 量化成 int8 (N, K) + scale (N, K//group_size)。

    W8A16 group-wise RTN:
        沿 K 维按 group_size 分组, 每组一个 scale = max(|w_group|) / 127
        w_int8 = round(w / scale).clamp(-127, 127)
        反量化: w ≈ w_int8 * scale

    Args:
        weight: (N, K) bf16 或 fp32 权重, 与 F.linear 的 weight 布局一致 (out, in)
        group_size: 分组大小, 必须 K % group_size == 0, 支持 [64,128,256,512,1024]

    Returns:
        w_int8: (N, K) int8 量化权重
        w_scale: (N, K // group_size) fp32 scale
    """
     assert weight.ndim == 2, f"weight 必须是 2D (N, K), got {weight.shape}"
    N, K = weight.shape
    assert K % group_size == 0, f"K={K} 必须能被 group_size={group_size} 整除"
    group_num = K // group_size

    # 用 fp32 计算 scale (高精度), 输出 int8
    w = weight.float()
    # (N, group_num, group_size)
    w_grouped = w.view(N, group_num, group_size)
    amax = w_grouped.abs().amax(dim=-1, keepdim=True)  # (N, group_num, 1)
    # 防止 amax=0 (全零组) 导致除零
    amax = amax.clamp(min=1e-8)
    scale = amax / 127.0  # (N, group_num, 1)
    w_int8 = torch.round(w_grouped / scale).clamp(-127, 127).to(torch.int8)
    w_int8 = w_int8.view(N, K)
    w_scale = scale.view(N, group_num)
    return w_int8, w_scale


def quantize_weight_rtn_mlu(weight: torch.Tensor, group_size: int = DEFAULT_GROUP_SIZE):
    """在 MLU 上做 RTN 量化 (比 CPU 快, 用于大权重)。

    逻辑与 quantize_weight_rtn 相同, 但在 MLU 设备上执行。
    返回的 int8/scale 留在原设备上。
    """
    assert weight.ndim == 2
    N, K = weight.shape
    assert K % group_size == 0
    group_num = K // group_size
    w = weight.float()
    w_grouped = w.view(N, group_num, group_size)
    amax = w_grouped.abs().amax(dim=-1, keepdim=True).clamp(min=1e-8)
    scale = amax / 127.0
    w_int8 = torch.round(w_grouped / scale).clamp(-127, 127).to(torch.int8).view(N, K)
    w_scale = scale.view(N, group_num)
    return w_int8, w_scale
    # ---------------------------------------------------------------------------
# 第 3 步: 推理时用 scaled_matmul 替换 F.linear
# ---------------------------------------------------------------------------
def scaled_matmul_linear(
    x: torch.Tensor,
    w_int8: torch.Tensor,
    w_scale: torch.Tensor,
    bias: torch.Tensor | None,
    quant_bit_size: int = 8,
) -> torch.Tensor:
    """用 scaled_matmul 执行 y = x @ w_int8.T (反量化在算子内部), 等价 F.linear(x, w_bf16, bias)。

    scaled_matmul(a, b, a_scale, b_scale, output_dtype, ...):
        a = x        (M, K) bf16, 激活不量化
        b = w_int8   (N, K) int8, 与 F.linear 权重布局一致 (无需转置)
        a_scale = None (激活不量化)
        b_scale = w_scale (N, group_num) fp32
        输出 (M, N) bf16

    支持 2D 输入 (M, K)。nanovllm 的所有 Linear 输入都是 2D (prefill/decode 均是)。
    """
    ops = _get_torch_mlu_ops()
    orig_shape = x.shape
    if x.ndim != 2:
        # 兜底: 非 2D 输入 reshape 成 2D (nanovllm 实际不会走到这里)
        x = x.reshape(-1, x.shape[-1])
    out = ops.scaled_matmul(
        x, w_int8, None, w_scale, x.dtype,
        bias=bias,
        quant_bit_size=quant_bit_size,
        a_quant_bit_size=-1,   # 激活 bf16 不量化
        act_mode="none",
    )
    if len(orig_shape) > 2:
        out = out.reshape(*orig_shape[:-1], out.shape[-1])
    return out

# ---------------------------------------------------------------------------
# 把模型里的目标 Linear 权重在内存中替换成 int8 + scale
# ---------------------------------------------------------------------------
def _name_matches_target(full_name: str, targets) -> bool:
    """full_name 是否以 targets 中任一后缀结尾 (如 ...mlp.gate_up_proj)。"""
    for t in targets:
        if full_name.endswith("." + t) or full_name == t:
            return True
    return False


def apply_w8a16_to_model(
    model: torch.nn.Module,
    group_size: int = DEFAULT_GROUP_SIZE,
    targets=DEFAULT_QUANT_TARGETS,
    verbose: bool = True,
):
    """遍历 model, 把匹配 targets 的 Linear 层权重量化成 int8+scale 并替换 forward。

    对每个目标 Linear:
      1. 取出 self.weight (bf16, N×K)
      2. RTN 量化成 w_int8 (int8) + w_scale (fp32)
      3. 把 self.weight 替换成 int8 buffer, 释放 bf16 权重显存
      4. 注册 w_scale 为 buffer
      5. monkey-patch 该 module 的 forward 用 scaled_matmul_linear (实例级)

    非目标 Linear (如 o_proj) 保持原 F.linear 不变。

    必须在 load_model 之后、warmup/capture_graph 之前调用。
    """
    from nanovllm.layers.linear import LinearBase

    quantized, skipped = [], []
    total_params = 0
    for name, module in model.named_modules():
        if not isinstance(module, LinearBase):
            continue
        if not _name_matches_target(name, targets):
            skipped.append(name)
            continue
        weight = module.weight
        if weight is None or weight.ndim != 2:
            skipped.append(name + "(non-2d)")
            continue
            N, K = weight.shape
        # 在权重所在设备上量化 (MLU 上做更快, 但 CPU 也行)
        w_int8, w_scale = quantize_weight_rtn_mlu(weight.data, group_size)

        # 保存原 weight/bias 引用 (CUDA fallback 用), 然后替换
        module._w8a16_weight_bf16 = weight.detach()  # 保留原 bf16 供 fallback
        module._w8a16_bias = module.bias.data.detach() if module.bias is not None else None

        # 用 buffer 替换 weight: 释放 bf16 权重显存, 改存 int8 + scale
        # int8: N*K*1 byte (原 bf16 N*K*2 byte, 省 50%)
        # scale: N*(K//128)*4 byte (很小)
        del module._parameters["weight"]
        module.register_buffer("w_int8", w_int8)
        module.register_buffer("w_scale", w_scale.to(torch.float32))

        # patch forward (实例级, 不污染类)
        module.forward = _make_w8a16_forward(module)

        quantized.append(name)
        total_params += N * K

    if verbose:
        print(f"[W8A16] 量化 {len(quantized)} 个 Linear, 跳过 {len(skipped)} 个")
        print(f"[W8A16] 量化权重参数量: {total_params/1e6:.1f}M "
              f"(int8 {total_params/1024**3:.2f}GB, 原 bf16 {total_params*2/1024**3:.2f}GB, "
              f"省 {total_params/1024**3:.2f}GB)")
        if skipped:
            print(f"[W8A16] 跳过(非目标/小GEMM): {skipped[:6]}{'...' if len(skipped)>6 else ''}")
    return quantized


def _make_w8a16_forward(module):
    """为单个 Linear 实例生成 W8A16 forward (MLU 用 scaled_matmul, CUDA fallback F.linear)。

    保留 RowParallelLinear 的 all_reduce 语义 (tp_size>1 时)。
    """
    bf16_weight = module._w8a16_weight_bf16
    orig_bias = module._w8a16_bias
    tp_size = getattr(module, "tp_size", 1)

def forward(x):
        if _is_mlu(x):
            out = scaled_matmul_linear(x, module.w_int8, module.w_scale, module.bias)
        else:
            # CUDA fallback: 用原 bf16 权重做标准 F.linear
            out = F.linear(x, bf16_weight, orig_bias)
        # RowParallelLinear: tp_size>1 时需要 all_reduce
        if tp_size > 1:
            import torch.distributed as dist
            dist.all_reduce(out)
        return out

    return forward


# ---------------------------------------------------------------------------
# 一键 patch: 在 import nanovllm 之后、构建 LLM 之前调用
# ---------------------------------------------------------------------------
_original_load_model = None


def apply_w8a16_patch(
    group_size: int = DEFAULT_GROUP_SIZE,
    targets=DEFAULT_QUANT_TARGETS,
):
    """注入 W8A16 量化到 nanovllm 的权重加载流程。

    必须在 import nanovllm 之后 (load_model 已加载)、构建 LLM 之前调用。
    之后构建的模型会在 load_model 完成后自动量化目标 Linear 权重。

    原理: monkey-patch nanovllm.utils.loader.load_model, 在原 load_model(model, path)
          之后调用 apply_w8a16_to_model(model, ...)。这样原版 ModelRunner.__init__ 一行不改,
          量化自动发生在 load_model 与 warmup_model 之间 (正是正确的时机)。
    """
    global _original_load_model
    import nanovllm.utils.loader as loader_mod

 # 幂等保护: 避免重复 patch 导致 _original_load_model 指向已 patch 版本 (无限递归)
    if getattr(loader_mod.load_model, "_w8a16_patched", False):
        return loader_mod.load_model

    _original_load_model = loader_mod.load_model

    def _patched_load_model(model, path):
        # 先用原 loader 加载 bf16 权重
        _original_load_model(model, path)
        # 再在内存中量化目标 Linear
        apply_w8a16_to_model(model, group_size=group_size, targets=targets)

    _patched_load_model._w8a16_patched = True  # 标记已 patch
    loader_mod.load_model = _patched_load_model
    # model_runner.py 里是 `from nanovllm.utils.loader import load_model`, 已绑定原函数,
    # 需要同时替换 model_runner 模块里的引用
    import nanovllm.engine.model_runner as runner_mod
    runner_mod.load_model = _patched_load_model
    print("[已注入 W8A16 权重量化 patch]", flush=True)
    return loader_mod.load_model

