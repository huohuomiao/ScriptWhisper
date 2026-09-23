# MLU 实机验收清单

## 1. 环境

```bash
cnmon info
python - <<'PY'
import torch
import torch_mlu
import torch_mlu_ops

print("torch:", torch.__version__)
print("MLU count:", torch.mlu.device_count())
print("MLU name:", torch.mlu.get_device_name(0))
PY
```

目标环境应使用 MLU370 或更新设备，并满足根目录 README 中列出的依赖版本。

## 2. 单元测试

```bash
pip install -e ".[mlu,test]"
pytest -q

# 在 MLU 节点上额外校验 vendor attention/KV-cache 算子数值
RUN_MLU_TESTS=1 pytest -q -m mlu
```

## 3. 单卡 eager

```bash
MLU_VISIBLE_DEVICES=0 python examples/mlu_example.py /path/to/Qwen3-0.6B
```

验收项：模型加载完成、prefill/decode 均无算子错误、生成文本非空、进程退出后
显存释放。

## 4. Prefix cache 与长上下文

使用具有相同长前缀的多条请求运行 `LLM.generate`，覆盖：

- prompt 跨越多个 16-token KV block；
- 部分 block 命中 prefix cache；
- `max_model_len` 附近的 prefill 与 decode；
- batch size 为 1、2、8、16 及非图捕获整档值。

## 5. MLU Graph

```bash
MLU_VISIBLE_DEVICES=0 python examples/mlu_example.py /path/to/Qwen3-0.6B --use-graph
```

对相同 prompt 分别运行 eager 和 graph 模式。固定 PyTorch/MLU 随机种子后，检查
首 token logits、生成 token 范围和终止行为；若 vendor 随机采样实现不保证逐 token
一致，则比较 greedy/top-1 结果或 logits 误差，而不是随机样本本身。

## 6. 多卡 CNCL

```bash
MLU_VISIBLE_DEVICES=0,1 python examples/mlu_example.py /path/to/Qwen3-8B --tp 2
```

验收项：每个 rank 绑定不同 MLU、CNCL 初始化成功、权重分片正确、输出只由 rank 0
汇总，退出时共享内存与进程组均被清理。

## 7. 对照与性能

在同一模型权重和 dtype 下，以 Hugging Face eager 或 Cambricon vLLM-MLU 作为数值
对照。至少记录：

- 首 token logits 最大/平均绝对误差；
- prefill tokens/s、decode tokens/s；
- 峰值显存和可分配 KV block 数；
- 1/2/8/16/32/64 batch 下的稳定性；
- eager 与 MLU Graph 的首次运行、稳态延迟。
