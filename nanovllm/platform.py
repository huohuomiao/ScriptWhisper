from __future__ import annotations

from contextlib import AbstractContextManager
from importlib import import_module
from typing import Literal

import torch


DeviceType = Literal["cuda", "mlu"]
SUPPORTED_DEVICE_TYPES = ("cuda", "mlu")


def kv_cache_shape(
    device_type: str,
    num_layers: int,
    num_blocks: int,
    block_size: int,
    num_kv_heads: int,
    head_dim: int,
) -> tuple[int, ...]:
    """Return the paged-cache layout required by the selected kernel backend."""
    common = (2, num_layers, num_blocks)
    if normalize_device_type(device_type) == "mlu":
        return common + (num_kv_heads, block_size, head_dim)
    return common + (block_size, num_kv_heads, head_dim)


def normalize_device_type(device: str) -> DeviceType:
    """Normalize a user-facing device string without initializing hardware."""
    device_type = device.lower().split(":", 1)[0]
    if device_type not in SUPPORTED_DEVICE_TYPES:
        choices = ", ".join(("auto", *SUPPORTED_DEVICE_TYPES))
        raise ValueError(f"Unsupported device {device!r}; expected one of: {choices}")
    return device_type  # type: ignore[return-value]


def _load_mlu_extension() -> object:
    try:
        extension = import_module("torch_mlu")
    except ImportError as exc:
        raise RuntimeError(
            "MLU execution requires the Cambricon torch-mlu package. "
            "Install Nano-vLLM inside a Cambricon PyTorch container and "
            "install the 'mlu' optional dependencies."
        ) from exc
    if not hasattr(torch, "mlu"):
        raise RuntimeError("torch-mlu was imported, but torch.mlu is unavailable")
    return extension


def _mlu_is_available() -> bool:
    try:
        _load_mlu_extension()
    except RuntimeError:
        return False
    return bool(torch.mlu.is_available())  # type: ignore[attr-defined]


def resolve_device_type(device: str) -> DeviceType:
    """Resolve ``auto`` while keeping CUDA as the backwards-compatible default."""
    if device.lower() != "auto":
        return normalize_device_type(device)
    if torch.cuda.is_available():
        return "cuda"
    if _mlu_is_available():
        return "mlu"
    raise RuntimeError(
        "No supported accelerator is available. Nano-vLLM requires CUDA or MLU; "
        "pass device='cuda' or device='mlu' to select one explicitly."
    )


def device_count(device_type: str) -> int:
    resolved = normalize_device_type(device_type)
    if resolved == "mlu":
        _load_mlu_extension()
        return int(torch.mlu.device_count())  # type: ignore[attr-defined]
    return int(torch.cuda.device_count())


class DevicePlatform:
    """Small CUDA/MLU compatibility layer used by the model runner."""

    def __init__(self, device_type: str, index: int):
        self.type = resolve_device_type(device_type)
        self.index = index
        if self.type == "mlu":
            _load_mlu_extension()
            self.accelerator = torch.mlu  # type: ignore[attr-defined]
            self.dist_backend = "cncl"
        else:
            self.accelerator = torch.cuda
            self.dist_backend = "nccl"

        if not self.accelerator.is_available():
            raise RuntimeError(f"Requested {self.type.upper()} device is unavailable")
        device_count = self.accelerator.device_count()
        if index < 0 or index >= device_count:
            raise RuntimeError(
                f"Requested {self.type}:{index}, but only {device_count} device(s) are visible"
            )
        self.device = torch.device(f"{self.type}:{index}")

    def set_device(self) -> None:
        self.accelerator.set_device(self.device)

    def empty_cache(self) -> None:
        self.accelerator.empty_cache()

    def reset_peak_memory_stats(self) -> None:
        self.accelerator.reset_peak_memory_stats()

    def mem_get_info(self) -> tuple[int, int]:
        return self.accelerator.mem_get_info()

    def memory_stats(self) -> dict[str, int]:
        return self.accelerator.memory_stats()

    def synchronize(self) -> None:
        self.accelerator.synchronize()

    def make_graph(self):
        graph_class = (
            self.accelerator.MLUGraph if self.type == "mlu" else self.accelerator.CUDAGraph
        )
        return graph_class()

    def graph_context(self, graph, pool=None) -> AbstractContextManager:
        return self.accelerator.graph(graph, pool=pool)

    @staticmethod
    def graph_pool(graph):
        return graph.pool() if hasattr(graph, "pool") else None

    def tensor(self, data, *, dtype: torch.dtype) -> torch.Tensor:
        """Stage small metadata tensors in pinned host memory before H2D copy."""
        try:
            host_tensor = torch.tensor(
                data,
                dtype=dtype,
                device="cpu",
                pin_memory=True,
            )
        except RuntimeError:
            host_tensor = torch.tensor(data, dtype=dtype, device="cpu")
        return host_tensor.to(self.device, non_blocking=True)
