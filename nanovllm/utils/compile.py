from functools import wraps
from typing import Any

import torch


def _find_tensor(value: Any) -> torch.Tensor | None:
    if isinstance(value, torch.Tensor):
        return value
    if isinstance(value, (tuple, list)):
        for item in value:
            tensor = _find_tensor(item)
            if tensor is not None:
                return tensor
    if isinstance(value, dict):
        for item in value.values():
            tensor = _find_tensor(item)
            if tensor is not None:
                return tensor
    return None


def compile_for_cuda(function):
    """Use torch.compile on CUDA while keeping the MLU path in eager mode.

    The Cambricon vLLM plugin disables general model compilation and relies on
    MLUGraph plus vendor kernels. Mirroring that policy avoids tracing MLU-only
    operators while preserving Nano-vLLM's existing CUDA optimization.
    """
    compiled = torch.compile(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        tensor = _find_tensor(args)
        if tensor is None:
            tensor = _find_tensor(kwargs)
        if tensor is not None and tensor.device.type == "mlu":
            return function(*args, **kwargs)
        return compiled(*args, **kwargs)

    return wrapped
