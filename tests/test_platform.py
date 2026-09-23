from types import SimpleNamespace

import pytest

from nanovllm import config as config_module
from nanovllm.config import Config
from nanovllm.platform import kv_cache_shape, normalize_device_type


@pytest.fixture(autouse=True)
def fake_hf_config(monkeypatch):
    value = SimpleNamespace(max_position_embeddings=8192)
    monkeypatch.setattr(
        config_module.AutoConfig,
        "from_pretrained",
        lambda _path: value,
    )


def test_platform_specific_default_block_size(tmp_path):
    assert Config(str(tmp_path), device="cuda").kvcache_block_size == 256
    assert Config(str(tmp_path), device="mlu").kvcache_block_size == 16


@pytest.mark.parametrize("block_size", [1, 16, 32, 64])
def test_mlu_accepts_vendor_supported_block_sizes(tmp_path, block_size):
    config = Config(str(tmp_path), device="mlu", kvcache_block_size=block_size)
    assert config.kvcache_block_size == block_size


def test_mlu_rejects_cuda_cache_block_size(tmp_path):
    with pytest.raises(ValueError, match="MLU supports"):
        Config(str(tmp_path), device="mlu", kvcache_block_size=256)


def test_kv_cache_layout_matches_each_attention_backend():
    assert kv_cache_shape("cuda", 28, 100, 256, 2, 128) == (
        2,
        28,
        100,
        256,
        2,
        128,
    )
    assert kv_cache_shape("mlu", 28, 100, 16, 2, 128) == (
        2,
        28,
        100,
        2,
        16,
        128,
    )


def test_device_string_normalization():
    assert normalize_device_type("MLU:3") == "mlu"
    assert normalize_device_type("cuda:0") == "cuda"
    with pytest.raises(ValueError, match="Unsupported device"):
        normalize_device_type("cpu")
