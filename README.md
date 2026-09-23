<p align="center">
<img width="300" src="assets/logo.png">
</p>

# Nano-vLLM with Cambricon MLU

这是基于 [GeeeekExplorer/nano-vllm](https://github.com/GeeeekExplorer/nano-vllm)
的 CUDA/MLU 双后端版本。上游 Nano-vLLM 当前只提供 CUDA 路径；本仓库参考
[Cambricon/vllm-mlu](https://github.com/Cambricon/vllm-mlu) `v0.11.2-dev`
的设备和算子接口，为寒武纪 MLU 增加了可独立运行的适配层。

代码基线（获取日期：2026-08-13）：

- Nano-vLLM `main`: `bb823b3e06983d71485a8e1f23715ebd87d98ef8`
- vLLM-MLU `v0.11.2-dev`: `dc984838c63aef3de46bbadedd82d9848a19c5d2`

## 适配范围

| 模块 | CUDA | MLU |
|---|---|---|
| 设备与显存管理 | `torch.cuda` | `torch.mlu` |
| 多卡通信 | NCCL | CNCL |
| KV-cache 写入 | Triton kernel | `torch_mlu_ops.reshape_paged_cache` |
| Prefill attention | FlashAttention | `torch_mlu_ops.flash_attention` |
| Decode attention | FlashAttention KV-cache | `torch_mlu_ops.single_query_cached_kv_attn` |
| 静态图 | CUDA Graph | MLU Graph |
| 随机采样 | PyTorch Gumbel-max | `torch_mlu_ops.random_sample` |

MLU KV-cache 使用 `[blocks, kv_heads, block_size, head_dim]`，与 CUDA
后端的 `[blocks, block_size, kv_heads, head_dim]` 不同；代码会按平台自动分配，
不能在两种后端间直接复用 KV-cache tensor。

当前模型范围与上游保持一致：仅支持 Qwen3 dense 模型，不包含量化、MoE、
多模态或在线服务。Cambricon vLLM-MLU 官方说明仅支持 MLU370 及以上设备，
本适配沿用相同硬件前提。

## 安装

### CUDA

```bash
pip install -e ".[cuda]"
```

### MLU

请在包含 Cambricon SDK 的 Linux 容器中安装。适配所对齐的依赖版本为：

- PyTorch 2.9.1
- torch-mlu 1.29.1 或更高兼容版本
- torch_mlu_ops 1.8.1 或更高兼容版本

```bash
# 先按寒武纪 SDK/容器说明准备 torch、torch-mlu 和 torch_mlu_ops
pip install -e ".[mlu]"

python -c "import torch_mlu, torch_mlu_ops, torch; print(torch.mlu.device_count())"
```

如果这些 wheel 只在 SDK 镜像或寒武纪软件源中提供，请先从对应渠道安装，
再使用 `pip install -e . --no-deps` 安装本项目。

## MLU 快速验证

先使用 eager 模式完成首轮验证：

```bash
MLU_VISIBLE_DEVICES=0 python examples/mlu_example.py /path/to/Qwen3-0.6B
```

确认 eager 模式正确后再验证 MLU Graph：

```bash
MLU_VISIBLE_DEVICES=0 python examples/mlu_example.py /path/to/Qwen3-0.6B --use-graph
```

双卡 Tensor Parallel：

```bash
MLU_VISIBLE_DEVICES=0,1 python examples/mlu_example.py /path/to/Qwen3-8B --tp 2
```

也可以直接使用 Python API：

```python
from nanovllm import LLM, SamplingParams

llm = LLM(
    "/path/to/Qwen3-0.6B",
    device="mlu",
    enforce_eager=True,
    tensor_parallel_size=1,
)
outputs = llm.generate(
    ["Hello, Nano-vLLM on MLU."],
    SamplingParams(temperature=0.6, max_tokens=64),
)
print(outputs[0]["text"])
```

MLU 默认 KV-cache block size 是 16；可选值为 `1/16/32/64`。CUDA 默认值仍为
256，以满足 CUDA FlashAttention 的 paged KV-cache 约束。

## 验证状态

无需 MLU 硬件的接口、布局和算子调用契约测试位于 `tests/`：

```bash
pip install -e ".[test]"
pytest -q
```

当前开发环境没有 MLU 驱动与板卡，因此仓库内验证不能替代 MLU370+ 实机验收。
建议按 [MLU 验收清单](docs/mlu-validation.md) 完成 eager、MLU Graph、单卡、
多卡和长上下文测试后再用于生产负载。

## CUDA 用法

原有接口保持兼容；`device="auto"` 会优先选择可用 CUDA，否则选择 MLU：

```python
from nanovllm import LLM, SamplingParams

llm = LLM("/path/to/Qwen3-0.6B", device="cuda", enforce_eager=True)
outputs = llm.generate(["Hello, Nano-vLLM."], SamplingParams(max_tokens=64))
```

上游 CUDA 基准脚本仍为 `bench.py`。
