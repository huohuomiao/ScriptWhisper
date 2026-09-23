"""MLU RMSNorm 优化补丁 —— 用 torch_mlu_ops.fused_rms_norm 替换手写实现。

使用方式 (见 apply_rmsnorm_patch 的 docstring):
    from optimization_rmsnorm.rmsnorm_patch import apply_rmsnorm_patch
    apply_rmsnorm_patch()   # 在 import nanovllm 之后, 构建 LLM 之前调用
    llm = LLM(...)          # 构建的模型自动用 fused_rms_norm

设计:
  - 不替换整个模块, 而是 monkey-patch nanovllm.layers.layernorm.RMSNorm 的方法
  - 这样保留原版 compile_for_cuda 装饰器结构, 不触发循环 import
  - MLU 路径用 fused_rms_norm, CUDA 路径 fallback 到原方法
  - 原版 layernorm.py 文件完全不动

优化原理:
  手写 RMSNorm 拆成 7 个小 kernel + 2 次 bf16<->fp32 cast, HBM round-trip 多。
  fused_rms_norm 是单个融合 kernel, 内部高精度计算, 无中间 HBM 往返。
"""
import torch
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_torch_mlu_ops():
    try:
        import torch_mlu_ops
    except ImportError as exc:
        raise RuntimeError(
            "MLU fused RMSNorm requires torch_mlu_ops. Install Nano-vLLM with "
            "the 'mlu' optional dependencies inside a Cambricon SDK container."
        ) from exc
    return torch_mlu_ops


def _is_mlu(tensor: torch.Tensor) -> bool:
    return tensor is not None and tensor.device.type == "mlu"


# 保留原方法的引用, 供 CUDA fallback
_original_rms_forward = None
_original_add_rms_forward = None


def _patched_rms_forward(self, x: torch.Tensor) -> torch.Tensor:
    if _is_mlu(x):
        ops = _get_torch_mlu_ops()
        # fused_rms_norm(x, residual=None, gamma=weight, beta=None, bias=None, eps, store_output_before_norm=False)
        return ops.fused_rms_norm(x, None, self.weight, None, None, self.eps, False)
    # CUDA 路径: 调用原方法
    return _original_rms_forward(self, x)
    def _patched_add_rms_forward(
    self, x: torch.Tensor, residual: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    if _is_mlu(x):
        ops = _get_torch_mlu_ops()
        # store_output_before_norm=True: 返回 (normed, new_residual)
        # new_residual = (x + residual) 转回原 dtype, 与手写语义一致 (已验证 max_diff=0.0)
        return ops.fused_rms_norm(x, residual, self.weight, None, None, self.eps, True)
    # CUDA 路径: 调用原方法
    return _original_add_rms_forward(self, x, residual)


def apply_rmsnorm_patch():
    """注入 fused_rms_norm 到 nanovllm 的 RMSNorm。

    必须在 import nanovllm 之后 (RMSNorm 类已加载)、构建 LLM 之前调用。
    之后构建的模型实例会用 patched 的方法, 包括 Graph capture。
    """
    global _original_rms_forward, _original_add_rms_forward

    from nanovllm.layers.layernorm import RMSNorm

    # 保存原方法 (CUDA fallback 用)
    _original_rms_forward = RMSNorm.rms_forward
    _original_add_rms_forward = RMSNorm.add_rms_forward

    # 替换为优化版
    RMSNorm.rms_forward = _patched_rms_forward
    RMSNorm.add_rms_forward = _patched_add_rms_forward

    return RMSNorm

