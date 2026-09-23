import os
from dataclasses import dataclass
from transformers import AutoConfig

from nanovllm.platform import normalize_device_type, resolve_device_type


@dataclass(slots=True)
class Config:
    model: str
    max_num_batched_tokens: int = 16384
    max_num_seqs: int = 512
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.9
    tensor_parallel_size: int = 1
    enforce_eager: bool = False
    device: str = "auto"
    hf_config: AutoConfig | None = None
    eos: int = -1
    kvcache_block_size: int = -1
    num_kvcache_blocks: int = -1

    def __post_init__(self):
        if not os.path.isdir(self.model):
            raise ValueError(f"Model path is not a directory: {self.model}")
        self.device = (
            resolve_device_type(self.device)
            if self.device.lower() == "auto"
            else normalize_device_type(self.device)
        )
        if self.kvcache_block_size == -1:
            self.kvcache_block_size = 16 if self.device == "mlu" else 256
        if self.device == "cuda" and self.kvcache_block_size % 256 != 0:
            raise ValueError("CUDA flash-attn requires kvcache_block_size to be a multiple of 256")
        if self.device == "mlu" and self.kvcache_block_size not in (1, 16, 32, 64):
            raise ValueError("MLU supports kvcache_block_size values 1, 16, 32, or 64")
        if not 1 <= self.tensor_parallel_size <= 8:
            raise ValueError("tensor_parallel_size must be between 1 and 8")
        if not 0 < self.gpu_memory_utilization <= 1:
            raise ValueError("gpu_memory_utilization must be in (0, 1]")
        hf_config = AutoConfig.from_pretrained(self.model)
        self.hf_config = hf_config
        self.max_model_len = min(self.max_model_len, hf_config.max_position_embeddings)
