import torch
from torch import nn

from nanovllm.utils.compile import compile_for_cuda


class Sampler(nn.Module):

    @compile_for_cuda
    def forward(self, logits: torch.Tensor, temperatures: torch.Tensor):
        logits = logits.float().div_(temperatures.unsqueeze(dim=1))
        probs = torch.softmax(logits, dim=-1)
        if logits.device.type == "mlu":
            try:
                import torch_mlu_ops
            except ImportError as exc:
                raise RuntimeError("MLU sampling requires torch_mlu_ops") from exc
            return torch_mlu_ops.random_sample(probs, True, {}).view(-1)
        sample_tokens = probs.div_(torch.empty_like(probs).exponential_(1).clamp_min_(1e-10)).argmax(dim=-1)
        return sample_tokens
